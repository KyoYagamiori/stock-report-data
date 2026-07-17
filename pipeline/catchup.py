from __future__ import annotations

import argparse
import json
from datetime import datetime, time
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from pipeline.runner import RunOptions, RunResult, run_pipeline


TIMEZONE = ZoneInfo("Asia/Shanghai")


def catch_up_noon(
    root: Path,
    moment: datetime | None = None,
    runner: Callable[[RunOptions, Path], RunResult] = run_pipeline,
) -> RunResult | None:
    now = (moment or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    if now.time().replace(tzinfo=None) < time(11, 35):
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
    return (
        pointer.get("report_cycle") == f"{report_date}-noon"
        and pointer.get("quality_grade") in {"A", "B"}
        and bool(pointer.get("selected_file"))
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Catch up a delayed fixed noon snapshot")
    parser.add_argument("--root", default=".")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = catch_up_noon(Path(args.root).resolve())
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


if __name__ == "__main__":
    main()
