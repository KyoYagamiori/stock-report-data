from __future__ import annotations

import argparse
import json
from pathlib import Path

from ma5_system.runner import RunOptions, run_scan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MA5 concentrated trading system")
    parser.add_argument("--phase", required=True, choices=["preclose", "close"])
    parser.add_argument("--planned-at", required=True, help="Planned China time in HH:MM")
    parser.add_argument("--report-date", help="Optional report date in YYYY-MM-DD")
    parser.add_argument("--root", default=".")
    parser.add_argument("--archive-report", action="store_true", help="Write a private local MA5 scan draft; never overwrites the final ChatGPT action report")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_scan(
        RunOptions(
            phase=args.phase,
            planned_at=args.planned_at,
            report_date=args.report_date,
            archive_report=args.archive_report,
        ),
        Path(args.root).resolve(),
    )
    print(
        json.dumps(
            {
                "scan_id": result.screen["scan_id"],
                "grade": result.screen["quality"]["grade"],
                "actionable": result.screen["quality"]["actionable"],
                "primary_candidate": (result.screen.get("primary_candidate") or {}).get("code"),
                "manifest": str(result.publication.manifest_file),
                "selected": result.publication.selected,
                "selection_reason": result.publication.reason,
                "report": str(result.report_path) if result.report_path else None,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
