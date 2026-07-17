from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None

from ma5_system.config import load_strategy_config
from ma5_system.data import (
    HISTORY_COLUMNS,
    HistoryStore,
    bootstrap_date_range,
    fetch_all_a_spot,
    fetch_history_for_codes,
    normalize_code,
    normalize_spot_frame,
)
from datetime import datetime
from zoneinfo import ZoneInfo


TIMEZONE = ZoneInfo("Asia/Shanghai")
INDUSTRY_MAP_MIN_COVERAGE = 0.95
INDUSTRY_MAP_MIN_RECORDS = 3_000
THS_REQUEST_ATTEMPTS = 4


def bootstrap_history(root: Path, shard_index: int, shard_count: int, workers: int = 8) -> Path:
    config = load_strategy_config()
    moment = datetime.now(TIMEZONE)
    raw, _, errors = fetch_all_a_spot()
    spot = normalize_spot_frame(raw, moment, config)
    codes = sorted(spot["code"].unique())
    shard_codes = [code for index, code in enumerate(codes) if index % shard_count == shard_index]
    start, end = bootstrap_date_range(moment)
    history, history_errors = fetch_history_for_codes(shard_codes, start, end, workers=workers)
    output = root / "output" / "ma5" / "bootstrap" / f"history-shard-{shard_index:02d}.csv.gz"
    output.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(output, index=False, compression="gzip")
    diagnostic = output.with_suffix(".json")
    diagnostic.write_text(
        json.dumps(
            {
                "shard_index": shard_index,
                "shard_count": shard_count,
                "codes": len(shard_codes),
                "successful_codes": int(history["code"].nunique()) if not history.empty else 0,
                "rows": len(history),
                "errors": [*errors, *history_errors],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return output


def merge_history(
    root: Path,
    pattern: str = "history-shard-*.csv.gz",
    minimum_coverage: float = 0.95,
) -> Path:
    source_dir = root / "output" / "ma5" / "bootstrap"
    frames = [pd.read_csv(path, dtype={"code": str}) for path in sorted(source_dir.glob(pattern))]
    if not frames:
        raise FileNotFoundError(f"No bootstrap shards matched {source_dir / pattern}")
    diagnostics = []
    for path in sorted(source_dir.glob("history-shard-*.json")):
        try:
            diagnostics.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    expected_codes = sum(int(item.get("codes", 0) or 0) for item in diagnostics)
    fetched_codes = {
        normalize_code(value)
        for frame in frames
        for value in frame.get("code", pd.Series(dtype=str)).dropna().unique()
        if re.fullmatch(r"\d{6}", normalize_code(value))
    }
    coverage = min(1.0, len(fetched_codes) / expected_codes) if expected_codes else 0.0
    ready = bool(fetched_codes) and bool(expected_codes) and coverage >= minimum_coverage
    status = {
        "ready": ready,
        "expected_codes": expected_codes,
        "fetched_codes": len(fetched_codes),
        "coverage": round(coverage, 6),
        "minimum_coverage": minimum_coverage,
        "rows": sum(len(frame) for frame in frames),
        "shards": len(frames),
        "diagnostics": len(diagnostics),
    }
    status_path = root / "output" / "ma5" / "state" / "history_bootstrap.status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not ready:
        raise RuntimeError(
            "History bootstrap is not ready: "
            f"{len(fetched_codes)}/{expected_codes} codes ({coverage:.2%}), "
            f"minimum {minimum_coverage:.2%}"
        )
    store = HistoryStore(root / "output" / "ma5" / "state" / "daily_history.csv.gz")
    existing = store.load()
    merged = pd.concat([existing, *frames], ignore_index=True)
    for column in HISTORY_COLUMNS:
        if column not in merged.columns:
            merged[column] = None
    store.save(merged[HISTORY_COLUMNS])
    return store.path


def bootstrap_industry_map(
    root: Path,
    workers: int = 4,
    ak_module: Any = ak,
    *,
    sw_fetcher: Any = None,
    ths_fetcher: Any = None,
    minimum_coverage: float = INDUSTRY_MAP_MIN_COVERAGE,
    minimum_records: int = INDUSTRY_MAP_MIN_RECORDS,
) -> Path:
    if ak_module is None:
        raise RuntimeError("AKShare is unavailable")

    output = root / "output" / "ma5" / "state" / "industry_map.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    expected_codes = _load_expected_codes(root)
    records: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    source_stats: dict[str, Any] = {}

    try:
        em_records, em_errors = _collect_em_industry_records(ak_module, workers)
        records.update(em_records)
        errors.extend(f"eastmoney: {item}" for item in em_errors)
        source_stats["eastmoney"] = {
            "records": len(em_records),
            "errors": len(em_errors),
        }
    except Exception as exc:
        errors.append(f"eastmoney: board list failed: {str(exc)[:240]}")
        source_stats["eastmoney"] = {"records": 0, "errors": 1}

    initial_coverage = _industry_map_coverage(records, expected_codes)
    needs_fallback = (
        not records
        or source_stats["eastmoney"]["errors"] > 0
        or (expected_codes and initial_coverage < minimum_coverage)
        or (not expected_codes and len(records) < minimum_records)
    )

    if needs_fallback:
        try:
            sw_records = (sw_fetcher or _collect_sw_industry_records)()
            for code, record in sw_records.items():
                records.setdefault(code, record)
            source_stats["shenwan"] = {"records": len(sw_records), "errors": 0}
        except Exception as exc:
            errors.append(f"shenwan: official classification failed: {str(exc)[:240]}")
            source_stats["shenwan"] = {"records": 0, "errors": 1}
    else:
        source_stats["shenwan"] = {"records": 0, "errors": 0, "skipped": True}

    after_sw_coverage = _industry_map_coverage(records, expected_codes)
    needs_ths = (
        not records
        or (expected_codes and after_sw_coverage < minimum_coverage)
        or (not expected_codes and len(records) < minimum_records)
    )

    if needs_ths:
        try:
            ths_records, ths_errors = _collect_ths_industry_records(
                ak_module,
                workers,
                ths_fetcher or _fetch_ths_board_members,
            )
            for code, record in ths_records.items():
                records.setdefault(code, record)
            errors.extend(f"ths: {item}" for item in ths_errors)
            source_stats["ths"] = {
                "records": len(ths_records),
                "errors": len(ths_errors),
            }
        except Exception as exc:
            errors.append(f"ths: board list failed: {str(exc)[:240]}")
            source_stats["ths"] = {"records": 0, "errors": 1}
    else:
        source_stats["ths"] = {"records": 0, "errors": 0, "skipped": True}

    coverage = _industry_map_coverage(records, expected_codes)
    ready = bool(records)
    if expected_codes:
        ready = ready and coverage >= minimum_coverage
    else:
        ready = ready and len(records) >= minimum_records

    status = {
        "ready": ready,
        "records": len(records),
        "expected_codes": len(expected_codes),
        "coverage": round(coverage, 6) if expected_codes else None,
        "minimum_coverage": minimum_coverage,
        "minimum_records": minimum_records,
        "sources": source_stats,
        "errors": errors,
    }
    output.with_suffix(".errors.json").write_text(
        json.dumps(errors, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output.with_suffix(".status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if not ready:
        reason = (
            f"coverage {coverage:.2%} is below {minimum_coverage:.2%}"
            if expected_codes
            else f"record count {len(records)} is below {minimum_records}"
        )
        raise RuntimeError(f"Industry map is not ready: {reason}")

    pd.DataFrame(records.values(), columns=["code", "name", "industry"]).sort_values("code").to_csv(output, index=False)
    return output


def _collect_em_industry_records(ak_module: Any, workers: int) -> tuple[dict[str, dict[str, str]], list[str]]:
    board_frame = ak_module.stock_board_industry_name_em()
    board_column = _first_column(board_frame, ("板块名称", "行业名称", "name"))
    if board_column is None:
        raise RuntimeError("Industry board list has no name column")
    boards = sorted(str(value) for value in board_frame[board_column].dropna().unique())
    frames: list[tuple[str, pd.DataFrame]] = []
    errors: list[str] = []

    def fetch(board: str) -> tuple[str, pd.DataFrame]:
        return board, ak_module.stock_board_industry_cons_em(symbol=board)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(fetch, board): board for board in boards}
        for future in as_completed(futures):
            board = futures[future]
            try:
                frames.append(future.result())
            except Exception as exc:
                errors.append(f"{board}: {str(exc)[:160]}")
    return _records_from_industry_frames(frames), errors


def _collect_sw_industry_records(http_get: Any = None) -> dict[str, dict[str, str]]:
    if http_get is None:
        from akshare.stock import stock_industry_sw as sw_runtime

        http_get = sw_runtime.requests.get
    base_url = "https://www.swsresearch.com/swindex/pdf/SwClass2021"
    stock_bytes = _request_sw_file(
        f"{base_url}/StockClassifyUse_stock.xls",
        http_get=http_get,
    )
    mapping_bytes = _request_sw_file(
        f"{base_url}/2014to2021.xlsx",
        http_get=http_get,
    )
    return _parse_sw_industry_files(stock_bytes, mapping_bytes)


def _request_sw_file(url: str, *, http_get: Any) -> bytes:
    last_error: Exception | None = None
    for verify in (True, False):
        try:
            response = http_get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; MA5ResearchBot/1.0)"},
                timeout=60,
                verify=verify,
            )
            status_code = int(getattr(response, "status_code", 200))
            content = bytes(getattr(response, "content", b""))
            if status_code == 200 and len(content) > 10_000 and (content.startswith(b"PK") or content.startswith(b"\xd0\xcf\x11\xe0")):
                return content
            last_error = RuntimeError(f"HTTP {status_code}, body length {len(content)}")
        except Exception as exc:
            last_error = exc
        if verify and last_error and "SSL" not in type(last_error).__name__.upper() and "CERTIFICATE" not in str(last_error).upper():
            break
    raise RuntimeError(f"SWS official file request failed: {last_error}")


def _parse_sw_industry_files(stock_bytes: bytes, mapping_bytes: bytes) -> dict[str, dict[str, str]]:
    assignments = pd.read_excel(
        BytesIO(stock_bytes),
        dtype={"股票代码": str, "行业代码": str},
    )
    required_assignment_columns = {"股票代码", "计入日期", "行业代码", "更新日期"}
    if not required_assignment_columns.issubset(assignments.columns):
        raise RuntimeError("SWS stock classification file has unexpected columns")
    assignments = assignments.rename(
        columns={
            "股票代码": "code",
            "计入日期": "start_date",
            "行业代码": "industry_code",
            "更新日期": "update_time",
        }
    )
    assignments["code"] = assignments["code"].map(normalize_code)
    assignments["industry_code"] = assignments["industry_code"].map(_normalize_industry_code)
    assignments["start_sort"] = pd.to_datetime(assignments["start_date"], errors="coerce")
    assignments["update_sort"] = pd.to_datetime(assignments["update_time"], errors="coerce")
    assignments = (
        assignments.sort_values(["code", "start_sort", "update_sort"])
        .drop_duplicates("code", keep="last")
    )

    comparison = pd.read_excel(BytesIO(mapping_bytes), sheet_name=1, header=1, dtype=str)
    if comparison.shape[1] < 8:
        raise RuntimeError("SWS classification comparison file has unexpected columns")
    current = comparison.iloc[:, 4:8].copy()
    current.columns = ["level1", "level2", "level3", "industry_code"]
    current["industry_code"] = current["industry_code"].map(_normalize_industry_code)
    industry_names: dict[str, str] = {}
    for row in current.itertuples(index=False):
        if not re.fullmatch(r"\d{6}", row.industry_code):
            continue
        for value in (row.level2, row.level1, row.level3):
            if pd.notna(value) and str(value).strip() and str(value).lower() != "nan":
                industry_names[row.industry_code] = str(value).strip()
                break

    records: dict[str, dict[str, str]] = {}
    for row in assignments.itertuples(index=False):
        if not re.fullmatch(r"\d{6}", row.code) or not re.fullmatch(r"\d{6}", row.industry_code):
            continue
        industry = ""
        for candidate in (
            f"{row.industry_code[:4]}00",
            f"{row.industry_code[:2]}0000",
            row.industry_code,
        ):
            industry = industry_names.get(candidate, "")
            if industry:
                break
        if industry:
            records[row.code] = {
                "code": row.code,
                "name": "",
                "industry": industry,
            }
    return records


def _normalize_industry_code(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\.0$", "", text)
    digits = re.sub(r"\D", "", text)
    return digits.zfill(6) if digits else ""


def _collect_ths_industry_records(
    ak_module: Any,
    workers: int,
    fetcher: Any,
) -> tuple[dict[str, dict[str, str]], list[str]]:
    board_frame = ak_module.stock_board_industry_name_ths()
    name_column = _first_column(board_frame, ("name", "板块名称", "行业名称"))
    code_column = _first_column(board_frame, ("code", "板块代码", "行业代码"))
    if name_column is None or code_column is None:
        raise RuntimeError("THS industry board list has no name/code columns")
    boards = sorted(
        (
            str(row[name_column]),
            str(row[code_column]),
        )
        for _, row in board_frame.dropna(subset=[name_column, code_column]).iterrows()
    )
    frames: list[tuple[str, pd.DataFrame]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(fetcher, industry, board_code): (industry, board_code)
            for industry, board_code in boards
        }
        for future in as_completed(futures):
            industry, board_code = futures[future]
            try:
                frames.append((industry, future.result()))
            except Exception as exc:
                errors.append(f"{industry}/{board_code}: {str(exc)[:160]}")
    return _records_from_industry_frames(frames), errors


def _records_from_industry_frames(frames: list[tuple[str, pd.DataFrame]]) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    for industry, frame in sorted(frames, key=lambda item: item[0]):
        code_column = _first_column(frame, ("代码", "code", "股票代码"))
        name_column = _first_column(frame, ("名称", "name", "股票简称"))
        if code_column is None:
            continue
        for _, row in frame.iterrows():
            code = normalize_code(row.get(code_column))
            if not re.fullmatch(r"\d{6}", code):
                continue
            records.setdefault(
                code,
                {
                    "code": code,
                    "name": str(row.get(name_column, "") or "") if name_column else "",
                    "industry": industry,
                },
            )
    return records


def _fetch_ths_board_members(
    industry: str,
    board_code: str,
    *,
    http_get: Any = None,
    token_factory: Any = None,
    sleeper: Any = time.sleep,
) -> pd.DataFrame:
    del industry
    if http_get is None:
        from akshare.stock_feature import stock_board_industry_ths as ths_runtime

        http_get = ths_runtime.requests.get
    if token_factory is None:
        token_factory = _new_ths_token

    first_url = f"https://q.10jqka.com.cn/thshy/detail/code/{board_code}/"
    first_text = _request_ths_text(
        first_url,
        board_code,
        http_get=http_get,
        token_factory=token_factory,
        sleeper=sleeper,
    )
    page_match = re.search(
        r'class=["\']page_info["\'][^>]*>\s*\d+\s*/\s*(\d+)',
        first_text,
        flags=re.IGNORECASE,
    )
    page_count = int(page_match.group(1)) if page_match else 1
    frames = [_extract_ths_member_table(first_text)]
    for page in range(2, page_count + 1):
        page_url = (
            f"https://q.10jqka.com.cn/thshy/detail/code/{board_code}/"
            f"field/199112/order/desc/page/{page}/ajax/1/"
        )
        page_text = _request_ths_text(
            page_url,
            board_code,
            http_get=http_get,
            token_factory=token_factory,
            sleeper=sleeper,
        )
        frames.append(_extract_ths_member_table(page_text))
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["代码"], keep="first")


def _request_ths_text(
    url: str,
    board_code: str,
    *,
    http_get: Any,
    token_factory: Any,
    sleeper: Any,
) -> str:
    last_error: Exception | None = None
    for attempt in range(THS_REQUEST_ATTEMPTS):
        token = token_factory()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
            "Cookie": f"v={token}",
            "hexin-v": token,
            "Referer": f"https://q.10jqka.com.cn/thshy/detail/code/{board_code}/",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "text/html, */*; q=0.01",
        }
        try:
            response = http_get(url, headers=headers, timeout=20)
            status_code = int(getattr(response, "status_code", 200))
            text = str(getattr(response, "text", ""))
            if status_code == 200 and "<table" in text.lower():
                return text
            last_error = RuntimeError(f"HTTP {status_code}, body length {len(text)}")
        except Exception as exc:
            last_error = exc
        if attempt + 1 < THS_REQUEST_ATTEMPTS:
            sleeper(0.4 * (attempt + 1))
    raise RuntimeError(f"THS request failed after {THS_REQUEST_ATTEMPTS} attempts: {last_error}")


def _new_ths_token() -> str:
    from akshare.stock_feature import stock_board_industry_ths as ths_runtime

    runtime = ths_runtime.py_mini_racer.MiniRacer()
    runtime.eval(ths_runtime._get_file_content_ths("ths.js"))
    return str(runtime.call("v"))


def _extract_ths_member_table(html: str) -> pd.DataFrame:
    for frame in pd.read_html(StringIO(html)):
        code_column = _first_column(frame, ("代码", "股票代码", "code"))
        name_column = _first_column(frame, ("名称", "股票简称", "name"))
        if code_column is None:
            continue
        renamed = frame.rename(columns={code_column: "代码"})
        if name_column is not None:
            renamed = renamed.rename(columns={name_column: "名称"})
        elif "名称" not in renamed.columns:
            renamed["名称"] = ""
        return renamed[["代码", "名称"]]
    raise RuntimeError("THS page did not contain a constituent table")


def _load_expected_codes(root: Path) -> set[str]:
    history_path = root / "output" / "ma5" / "state" / "daily_history.csv.gz"
    if not history_path.exists():
        return set()
    try:
        frame = pd.read_csv(history_path, usecols=["code"], dtype={"code": str})
    except (OSError, ValueError):
        return set()
    return {
        normalize_code(value)
        for value in frame["code"].dropna().unique()
        if re.fullmatch(r"\d{6}", normalize_code(value))
    }


def _industry_map_coverage(records: dict[str, dict[str, str]], expected_codes: set[str]) -> float:
    if not expected_codes:
        return 0.0
    return len(expected_codes.intersection(records)) / len(expected_codes)


def _first_column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap MA5 all-A history and industry state")
    parser.add_argument("--mode", required=True, choices=["history", "merge-history", "industry"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--workers", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    if args.mode == "history":
        result = bootstrap_history(root, args.shard_index, args.shard_count, args.workers)
    elif args.mode == "merge-history":
        result = merge_history(root)
    else:
        result = bootstrap_industry_map(root, args.workers)
    print(result)


if __name__ == "__main__":
    main()
