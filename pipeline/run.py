from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from pipeline.publisher import write_health
from pipeline import SCHEMA_VERSION
from pathlib import Path

from pipeline.runner import RunOptions, run_pipeline
from pipeline.schedule import resolve_schedule, current_phase


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run stock report snapshot pipeline v1.6.1")
    parser.add_argument("--snapshot-type", required=True, choices=["early", "noon", "close", "evening", "intraday"])
    parser.add_argument("--mode", required=True, choices=["light", "full"])
    parser.add_argument("--planned-at", required=True, help="Planned China time in HH:MM")
    parser.add_argument("--attempt-role", default="primary")
    parser.add_argument("--report-date", help="Optional report date in YYYY-MM-DD")
    parser.add_argument("--root", default=".")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0)
    options = RunOptions(
        snapshot_type=args.snapshot_type,
        mode=args.mode,
        planned_at=args.planned_at,
        attempt_role=args.attempt_role,
        report_date=args.report_date,
        moment=started,
    )
    # Setup, dependency installation and CI can cross midnight after the
    # workflow's parameter step. Re-resolve automatic runs at collection start.
    # Explicit workflow_dispatch requests retain the requested date/type.
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if event in {"push", "schedule"}:
        cron = os.environ.get("GITHUB_EVENT_SCHEDULE", "")
        # Already queued workflows may use the older step-only cron env.
        params = (current_phase(started, "delayed-current-phase") if event == "schedule" and not cron
                  else resolve_schedule(event, cron, moment=started))
        options = RunOptions(params.snapshot_type, params.mode, params.planned_at,
                             params.attempt_role, params.report_date, started)
    root = Path(args.root).resolve()
    try:
        result = run_pipeline(options, root)
    except Exception as exc:
        now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
        report_date = options.report_date or started.date().isoformat()
        write_health(root, {"schema_version": SCHEMA_VERSION, "status": "error",
            "snapshot_type": options.snapshot_type, "snapshot_mode": options.mode,
            "report_date": report_date, "report_cycle": f"{report_date}-{options.snapshot_type}",
            "attempt_role": options.attempt_role,
            "planned_at": f"{report_date}T{options.planned_at}:00+08:00",
            "started_at": started.isoformat(timespec="seconds"), "finished_at": now,
            "quality_grade": "F", "published": False, "reason": f"{type(exc).__name__}: {exc}"})
        raise
    print(
        json.dumps(
            {
                "grade": result.grade,
                "published": result.published,
                "reason": result.reason,
                "snapshot_id": result.snapshot_id,
                "health_path": str(result.health_path),
            },
            ensure_ascii=False,
        )
    )

    if result.grade == "F":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
