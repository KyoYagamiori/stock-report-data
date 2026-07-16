from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


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
    "40 0 * * *": ScheduleParams("early", "full", "08:40", "primary"),
    "55 0 * * 1-5": ScheduleParams("early", "full", "08:55", "retry-1"),
    "35 1 * * 1-5": ScheduleParams("intraday", "light", "09:35", "rolling"),
    "5 2 * * 1-5": ScheduleParams("intraday", "light", "10:05", "rolling"),
    "35 2 * * 1-5": ScheduleParams("intraday", "light", "10:35", "rolling"),
    "5 3 * * 1-5": ScheduleParams("intraday", "light", "11:05", "rolling"),
    "35 3 * * 1-5": ScheduleParams("noon", "full", "11:35", "primary"),
    "5 4 * * *": ScheduleParams("noon", "full", "12:05", "retry-1"),
    "25 4 * * 1-5": ScheduleParams("noon", "full", "12:25", "retry-2"),
    "5 5 * * 1-5": ScheduleParams("intraday", "light", "13:05", "rolling"),
    "35 5 * * 1-5": ScheduleParams("intraday", "light", "13:35", "rolling"),
    "5 6 * * 1-5": ScheduleParams("intraday", "light", "14:05", "rolling"),
    "35 6 * * 1-5": ScheduleParams("intraday", "light", "14:35", "rolling"),
    "5 7 * * 1-5": ScheduleParams("intraday", "light", "15:05", "rolling"),
    "20 7 * * 1-5": ScheduleParams("close", "full", "15:20", "primary"),
    "35 12 * * *": ScheduleParams("evening", "full", "20:35", "primary"),
    "50 12 * * 1-5": ScheduleParams("evening", "full", "20:50", "retry-1"),
}


def resolve_schedule(
    event_name: str,
    schedule: str = "",
    manual: dict[str, str] | None = None,
) -> ScheduleParams:
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
