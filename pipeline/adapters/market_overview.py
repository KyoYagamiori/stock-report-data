from __future__ import annotations

from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.adapters import AdapterResult

try:
    import akshare as ak
except Exception:  # pragma: no cover - dependency failure path
    ak = None


TIMEZONE = ZoneInfo("Asia/Shanghai")
INDEX_CODES = {
    "000001": "上证指数",
    "399001": "深证成指",
    "399006": "创业板指",
}


def collect_market_overview(
    spot_quotes: pd.DataFrame,
    quote_source: str,
    moment: datetime,
    ak_module: Any = ak,
) -> AdapterResult:
    started = moment.astimezone(TIMEZONE)
    errors: list[str] = []
    indices, index_source, index_errors = _fetch_indices(ak_module)
    errors.extend(index_errors)
    sectors_top, sectors_bottom, sector_source, sector_errors = _fetch_sectors(ak_module)
    errors.extend(sector_errors)
    breadth, turnover = _market_from_spot(spot_quotes)

    market = {
        "indices": indices,
        "total_turnover": turnover,
        "turnover_valid": turnover is not None,
        "breadth": breadth,
        "breadth_valid": bool(breadth),
        "sectors_top": sectors_top,
        "sectors_bottom": sectors_bottom,
        "quote_source": quote_source,
        "index_source": index_source,
        "sector_source": sector_source,
    }
    valid_groups = sum(
        [
            len(indices) >= 2,
            turnover is not None,
            bool(breadth),
            len(sectors_top) >= 3,
            len(sectors_bottom) >= 3,
        ]
    )
    if valid_groups == 5:
        status = "success"
    elif valid_groups >= 2:
        status = "partial"
    else:
        status = "source_error"
    return AdapterResult(
        status=status,
        source="; ".join(filter(None, [quote_source, index_source, sector_source])),
        data=market,
        started_at=started,
        finished_at=datetime.now(TIMEZONE),
        records_expected=5,
        records_valid=valid_groups,
        errors=errors,
    )


def _market_from_spot(frame: pd.DataFrame) -> tuple[dict[str, int], float | None]:
    if frame is None or frame.empty:
        return {}, None
    pct_column = _first_column(frame, ("涨跌幅", "涨幅", "change"))
    amount_column = _first_column(frame, ("成交额", "成交额(元)", "amount"))
    code_column = _first_column(frame, ("代码", "code", "symbol"))
    name_column = _first_column(frame, ("名称", "name"))
    pct = pd.to_numeric(frame[pct_column], errors="coerce") if pct_column else pd.Series(dtype=float)
    amount = pd.to_numeric(frame[amount_column], errors="coerce") if amount_column else pd.Series(dtype=float)
    breadth: dict[str, int] = {}
    if not pct.empty and pct.notna().any():
        breadth = {
            "up": int((pct > 0).sum()),
            "down": int((pct < 0).sum()),
            "flat": int((pct == 0).sum()),
            "limit_up": 0,
            "limit_down": 0,
        }
        if code_column:
            for idx, value in pct.items():
                if pd.isna(value):
                    continue
                code = _normalize_code(frame.at[idx, code_column])
                name = str(frame.at[idx, name_column]) if name_column else ""
                limit = _limit_pct(code, name)
                if float(value) >= limit - 0.05:
                    breadth["limit_up"] += 1
                if float(value) <= -(limit - 0.05):
                    breadth["limit_down"] += 1
    turnover = float(amount.dropna().sum()) if not amount.empty and amount.notna().any() else None
    return breadth, turnover


def _fetch_indices(ak_module: Any) -> tuple[list[dict[str, Any]], str, list[str]]:
    if ak_module is None:
        return [], "unavailable", ["AKShare unavailable for indices"]
    attempts: list[tuple[str, Callable[[], pd.DataFrame]]] = [
        ("AKShare stock_zh_index_spot_sina", ak_module.stock_zh_index_spot_sina),
        ("AKShare stock_zh_index_spot_em", ak_module.stock_zh_index_spot_em),
    ]
    errors: list[str] = []
    for source, fetcher in attempts:
        try:
            frame = fetcher()
            normalized = _normalize_indices(frame, source)
            if len(normalized) >= 2:
                return normalized, source, errors
            errors.append(f"{source} returned fewer than two target indices")
        except Exception as exc:
            errors.append(f"{source} failed: {str(exc)[:300]}")
    return [], "unavailable", errors


def _normalize_indices(frame: pd.DataFrame, source: str) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    code_column = _first_column(frame, ("代码", "symbol", "代码名称"))
    name_column = _first_column(frame, ("名称", "name"))
    price_column = _first_column(frame, ("最新价", "最新", "trade", "current"))
    pct_column = _first_column(frame, ("涨跌幅", "change", "change_pct"))
    time_column = _first_column(frame, ("时间戳", "更新时间", "ticktime", "时间"))
    if code_column is None or price_column is None or pct_column is None:
        return []
    results = []
    for _, row in frame.iterrows():
        code = _normalize_index_code(row.get(code_column))
        if code not in INDEX_CODES:
            continue
        price = _safe_number(row.get(price_column))
        pct = _safe_number(row.get(pct_column))
        if price is None or pct is None:
            continue
        results.append(
            {
                "code": code,
                "name": str(row.get(name_column) or INDEX_CODES[code]) if name_column else INDEX_CODES[code],
                "latest": price,
                "pct_change": pct,
                "quote_time": str(row.get(time_column) or "") if time_column else "",
                "source": source,
            }
        )
    return results


def _fetch_sectors(ak_module: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, list[str]]:
    if ak_module is None:
        return [], [], "unavailable", ["AKShare unavailable for sectors"]
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    sources = []
    fetcher_groups = [
        (
            "industry",
            [
                ("AKShare stock_board_industry_name_em", ak_module.stock_board_industry_name_em),
                ("AKShare stock_board_industry_summary_ths", ak_module.stock_board_industry_summary_ths),
            ],
        ),
        (
            "concept",
            [("AKShare stock_board_concept_name_em", ak_module.stock_board_concept_name_em)],
        ),
    ]
    for category, fetchers in fetcher_groups:
        for source, fetcher in fetchers:
            try:
                frame = fetcher()
                normalized = _normalize_sectors(frame, category, source)
                if not normalized:
                    errors.append(f"{source} returned no ranked sector records")
                    continue
                records.extend(normalized)
                sources.append(source)
                break
            except Exception as exc:
                errors.append(f"{source} failed: {str(exc)[:300]}")
    records.sort(key=lambda item: item["pct_change"], reverse=True)
    top = records[:5]
    bottom = sorted(records, key=lambda item: item["pct_change"])[:5]
    return top, bottom, "; ".join(sources) or "unavailable", errors


def _normalize_sectors(frame: pd.DataFrame, category: str, source: str) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    name_column = _first_column(frame, ("板块名称", "板块", "名称", "name"))
    pct_column = _first_column(frame, ("涨跌幅", "涨幅", "change"))
    if name_column is None or pct_column is None:
        return []
    records = []
    for _, row in frame.iterrows():
        pct = _safe_number(row.get(pct_column))
        name = str(row.get(name_column) or "").strip()
        if pct is None or not name:
            continue
        records.append({"name": name, "category": category, "pct_change": pct, "source": source})
    return records


def _first_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return None


def _safe_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _normalize_code(value: Any) -> str:
    digits = "".join(char for char in str(value) if char.isdigit())
    return digits[-6:].zfill(6) if digits else ""


def _normalize_index_code(value: Any) -> str:
    code = _normalize_code(value)
    if code == "000001" and str(value).lower().startswith("sz"):
        return "399001"
    return code


def _limit_pct(code: str, name: str) -> float:
    if "ST" in name.upper():
        return 5.0
    if code.startswith(("300", "301", "688")):
        return 20.0
    if code.startswith(("4", "8", "9")):
        return 30.0
    return 10.0
