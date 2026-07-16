from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


ADAPTER_STATUSES = {
    "success",
    "partial",
    "timeout",
    "source_error",
    "parse_error",
    "validation_error",
    "skipped",
    "not_applicable",
}


@dataclass
class AdapterResult:
    status: str
    source: str
    data: Any
    started_at: datetime
    finished_at: datetime
    records_expected: int = 0
    records_valid: int = 0
    errors: list[str] = field(default_factory=list)
    retry_count: int = 0

    def __post_init__(self) -> None:
        if self.status not in ADAPTER_STATUSES:
            raise ValueError(f"Unsupported adapter status: {self.status}")

    def as_status(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "finished_at": self.finished_at.isoformat(timespec="seconds"),
            "records_expected": self.records_expected,
            "records_valid": self.records_valid,
            "errors": list(self.errors),
            "retry_count": self.retry_count,
        }
