from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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
            {"shard_index": shard_index, "shard_count": shard_count, "codes": len(shard_codes), "rows": len(history), "errors": [*errors, *history_errors]},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return output


def merge_history(root: Path, pattern: str = "history-shard-*.csv.gz") -> Path:
    source_dir = root / "output" / "ma5" / "bootstrap"
    frames = [pd.read_csv(path, dtype={"code": str}) for path in sorted(source_dir.glob(pattern))]
    if not frames:
        raise FileNotFoundError(f"No bootstrap shards matched {source_dir / pattern}")
    store = HistoryStore(root / "output" / "ma5" / "state" / "daily_history.csv.gz")
    existing = store.load()
    merged = pd.concat([existing, *frames], ignore_index=True)
    for column in HISTORY_COLUMNS:
        if column not in merged.columns:
            merged[column] = None
    store.save(merged[HISTORY_COLUMNS])
    return store.path


def bootstrap_industry_map(root: Path, workers: int = 4, ak_module: Any = ak) -> Path:
    if ak_module is None:
        raise RuntimeError("AKShare is unavailable")
    board_frame = ak_module.stock_board_industry_name_em()
    board_column = _first_column(board_frame, ("板块名称", "行业名称", "name"))
    if board_column is None:
        raise RuntimeError("Industry board list has no name column")
    boards = [str(value) for value in board_frame[board_column].dropna().unique()]
    records: dict[str, dict[str, str]] = {}
    errors: list[str] = []

    def fetch(board: str) -> tuple[str, pd.DataFrame]:
        return board, ak_module.stock_board_industry_cons_em(symbol=board)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(fetch, board): board for board in boards}
        for future in as_completed(futures):
            board = futures[future]
            try:
                industry, frame = future.result()
                code_column = _first_column(frame, ("代码", "code"))
                name_column = _first_column(frame, ("名称", "name"))
                if code_column is None:
                    errors.append(f"{industry}: missing code column")
                    continue
                for _, row in frame.iterrows():
                    code = normalize_code(row.get(code_column))
                    records[code] = {"code": code, "name": str(row.get(name_column, "") or "") if name_column else "", "industry": industry}
            except Exception as exc:
                errors.append(f"{board}: {str(exc)[:160]}")
    output = root / "output" / "ma5" / "state" / "industry_map.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records.values(), columns=["code", "name", "industry"]).sort_values("code").to_csv(output, index=False)
    output.with_suffix(".errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


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

