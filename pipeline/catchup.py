from __future__ import annotations

import argparse
import json
from datetime import datetime, time
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline import SCHEMA_VERSION
from pipeline.adapters import AdapterResult
from pipeline.calendar import CalendarInfo, resolve_calendar
from pipeline.contracts import ContractError, load_report_pools
from pipeline.publisher import verify_pointer, write_health
from pipeline.quality import evaluate_quality
from pipeline.runner import RunOptions, RunResult, run_pipeline


TIMEZONE = ZoneInfo("Asia/Shanghai")


def _recovery_stocks(root, moment, market_date, mode):
    del root, market_date, mode
    pools = load_report_pools()
    stocks = [dict(entry, pool=group, valid_quote=False, quote_time=None,
                   warnings=[], errors=[])
              for group in ("core", "watch", "supplemental") for entry in pools[group]]
    return AdapterResult(status="partial", source="configured pool; history recovery required",
                         data={"stocks": stocks}, started_at=moment, finished_at=moment,
                         records_expected=len(stocks), records_valid=0), pd.DataFrame()


def _recovery_market(spot, source, moment):
    del spot, source
    return AdapterResult(status="partial", source="history recovery required", data={},
                         started_at=moment, finished_at=moment)


def _run_recovery(options: RunOptions, root: Path) -> RunResult:
    # Do not fetch today's afternoon/full-day values before reconstructing noon.
    return run_pipeline(options, root, stock_collector=_recovery_stocks,
                        market_collector=_recovery_market)


def catch_up_noon(
    root: Path,
    moment: datetime | None = None,
    runner: Callable[[RunOptions, Path], RunResult] = _run_recovery,
    calendar_resolver: Callable[[datetime, Path], CalendarInfo] = resolve_calendar,
) -> RunResult | None:
    now = (moment or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    if now.time().replace(tzinfo=None) < time(11, 35):
        return None
    calendar = calendar_resolver(now, root)
    if not calendar.valid:
        raise ContractError("No verified trading calendar for noon recovery")
    if not calendar.is_trading_day:
        return None
    report_date = now.date().isoformat()
    if _same_day_noon_ready(root, report_date):
        return None
    return runner(
        RunOptions(
            snapshot_type="noon",
            mode="full",
            planned_at="11:35",
            attempt_role="automatic-delayed-catchup",
            report_date=report_date,
            moment=now,
        ),
        root,
    )


def _same_day_noon_ready(root: Path, report_date: str) -> bool:
    path = root / "output" / "latest" / "manifest.json"
    if not path.exists():
        return False
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    pointer = manifest.get("snapshots", {}).get("noon")
    if not isinstance(pointer, dict):
        return False
    if pointer.get("report_cycle") != f"{report_date}-noon":
        return False
    try:
        snapshot = verify_pointer(root, pointer)
        return (snapshot.get("snapshot_type") == "noon"
                and snapshot.get("report_date") == report_date
                and snapshot.get("market_date") == report_date
                and evaluate_quality(snapshot, "trading_noon").grade in {"A", "B"})
    except (ContractError, OSError, KeyError, TypeError, ValueError):
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Catch up a delayed fixed noon snapshot")
    parser.add_argument("--root", default=".")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.root).resolve()
    now = datetime.now(TIMEZONE)
    try:
        result = catch_up_noon(root, now)
    except Exception as exc:
        write_health(root, {"schema_version": SCHEMA_VERSION, "status": "error",
                           "snapshot_type": "noon", "report_date": now.date().isoformat(),
                           "report_cycle": f"{now.date().isoformat()}-noon",
                           "attempt_role": "automatic-delayed-catchup", "quality_grade": "F",
                           "started_at": now.isoformat(timespec="seconds"),
                           "finished_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
                           "published": False, "reason": f"{type(exc).__name__}: {exc}"})
        raise
    if result is None:
        print("No noon catch-up required.")
        return
    print(
        json.dumps(
            {
                "grade": result.grade,
                "published": result.published,
                "reason": result.reason,
                "snapshot_id": result.snapshot_id,
            },
            ensure_ascii=False,
        )
    )
    if result.grade == "F":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
