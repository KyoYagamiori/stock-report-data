from __future__ import annotations

import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pipeline.publisher import write_health
from pipeline import SCHEMA_VERSION
from pathlib import Path

from pipeline.runner import RunOptions, run_pipeline


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
    options = RunOptions(
        snapshot_type=args.snapshot_type,
        mode=args.mode,
        planned_at=args.planned_at,
        attempt_role=args.attempt_role,
        report_date=args.report_date,
    )
    root = Path(args.root).resolve()
    try:
        result = run_pipeline(options, root)
    except Exception as exc:
        now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
        write_health(root, {"schema_version": SCHEMA_VERSION, "status": "error",
            "snapshot_type": args.snapshot_type, "snapshot_mode": args.mode,
            "planned_at": args.planned_at, "started_at": now, "finished_at": now,
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
