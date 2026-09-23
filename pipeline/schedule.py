from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ScheduleParams:
    snapshot_type: str
    mode: str
    planned_at: str
    attempt_role: str
    report_date: str = ""

    def validate(self) -> None:
        if self.snapshot_type not in {"early", "noon", "close", "evening", "intraday"}:
            raise ValueError(f"Invalid snapshot_type: {self.snapshot_type}")
        if self.mode not in {"light", "full"}:
            raise ValueError(f"Invalid mode: {self.mode}")
        datetime.strptime(self.planned_at, "%H:%M")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.attempt_role):
            raise ValueError(f"Invalid attempt_role: {self.attempt_role}")
        if self.report_date:
            datetime.strptime(self.report_date, "%Y-%m-%d")

    def as_outputs(self) -> dict[str, str]:
        self.validate()
        return {
            "snapshot_type": self.snapshot_type,
            "mode": self.mode,
            "planned_at": self.planned_at,
            "attempt_role": self.attempt_role,
            "report_date": self.report_date,
        }


SCHEDULES = {
    "17 0 * * 1-5": ScheduleParams("early", "full", "08:17", "primary"),
    "43 0 * * 1-5": ScheduleParams("early", "full", "08:43", "retry-1"),
    "37 3 * * 1-5": ScheduleParams("noon", "full", "11:37", "primary"),
    "7 4 * * 1-5": ScheduleParams("noon", "full", "12:07", "retry-1"),
    "35 6 * * 1-5": ScheduleParams("intraday", "light", "14:35", "rolling"),
    "20 7 * * 1-5": ScheduleParams("close", "full", "15:20", "primary"),
    "17 12 * * *": ScheduleParams("evening", "full", "20:17", "primary"),
    "41 12 * * *": ScheduleParams("evening", "full", "20:41", "retry-1"),
}


def resolve_schedule(
    event_name: str,
    schedule: str = "",
    manual: dict[str, str] | None = None,
) -> ScheduleParams:
    if event_name == "push":
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        if now.hour >= 15:
            return ScheduleParams("close", "full", "15:00", "config-refresh")
        if (now.hour, now.minute) >= (11, 35):
            return ScheduleParams("noon", "full", "11:35", "config-refresh")
        return ScheduleParams("early", "full", now.strftime("%H:%M"), "config-refresh")
    if event_name == "schedule":
        try:
            return SCHEDULES[schedule]
        except KeyError as exc:
            raise ValueError(f"Unknown GitHub schedule: {schedule}") from exc
    if event_name != "workflow_dispatch":
        raise ValueError(f"Unsupported GitHub event: {event_name}")
    manual = manual or {}
    params = ScheduleParams(
        snapshot_type=manual.get("snapshot_type", "early"),
        mode=manual.get("mode", "full"),
        planned_at=manual.get("planned_at", "08:40"),
        attempt_role=manual.get("attempt_role", "manual"),
        report_date=manual.get("report_date", ""),
    )
    params.validate()
    return params


def write_github_outputs(path: Path, params: ScheduleParams) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for key, value in params.as_outputs().items():
            stream.write(f"{key}={value}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve stock snapshot workflow schedule")
    parser.add_argument("--github-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    params = resolve_schedule(
        os.environ.get("GITHUB_EVENT_NAME", ""),
        os.environ.get("GITHUB_EVENT_SCHEDULE", ""),
        {
            "snapshot_type": os.environ.get("INPUT_SNAPSHOT_TYPE", ""),
            "mode": os.environ.get("INPUT_MODE", ""),
            "planned_at": os.environ.get("INPUT_PLANNED_AT", ""),
            "attempt_role": os.environ.get("INPUT_ATTEMPT_ROLE", ""),
            "report_date": os.environ.get("INPUT_REPORT_DATE", ""),
        },
    )
    write_github_outputs(args.github_output, params)


if __name__ == "__main__":
    main()
