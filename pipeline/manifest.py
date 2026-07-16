from __future__ import annotations

from copy import deepcopy
from typing import Any

from pipeline import SCHEMA_VERSION


SNAPSHOT_TYPES = ("early", "noon", "close", "evening", "intraday")
REPORT_TYPES = ("early", "noon", "evening")


def empty_readiness(reason: str = "not generated") -> dict[str, Any]:
    return {
        "status": "not_ready",
        "selected_snapshot_id": None,
        "selected_file": None,
        "sha256": None,
        "quality_profile": None,
        "quality_grade": None,
        "missing_core_fields": [],
        "missing_optional_fields": [],
        "reasons": [reason],
    }


def new_manifest(calendar: dict[str, Any], generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "calendar": deepcopy(calendar),
        "snapshots": {snapshot_type: None for snapshot_type in SNAPSHOT_TYPES},
        "report_readiness": {report_type: empty_readiness() for report_type in REPORT_TYPES},
        "health": {
            "latest_run": "output/health/latest_run.json",
            "last_grade_a_at": None,
            "last_grade_b_at": None,
        },
    }


def build_pointer(snapshot: dict[str, Any], selected_file: str, sha256: str) -> dict[str, Any]:
    snapshot_type = snapshot["snapshot_type"]
    return {
        "selected_snapshot_id": snapshot["snapshot_id"],
        "selected_file": selected_file,
        "latest_alias": f"output/latest/{snapshot_type}/report_data_compact.json",
        "schema_version": SCHEMA_VERSION,
        "sha256": sha256,
        "snapshot_type": snapshot_type,
        "quality_profile": snapshot["quality_profile"],
        "quality_grade": snapshot["quality_grade"],
        "report_cycle": snapshot["report_cycle"],
        "market_date": snapshot["market_date"],
        "quote_time_max": snapshot.get("quote_time_max"),
        "suitable_reports": list(snapshot["suitable_reports"]),
        "published_at": snapshot["published_at"],
        "core_effective_count": snapshot["coverage"]["core"]["valid"],
        "effective_field_count": _effective_field_count(snapshot),
    }


def update_report_readiness(manifest: dict[str, Any]) -> None:
    for report_type in REPORT_TYPES:
        pointer = manifest["snapshots"].get(report_type)
        if pointer is None:
            manifest["report_readiness"][report_type] = empty_readiness()
            continue
        if pointer["quality_profile"] == "non_trading":
            status = "not_applicable"
        elif pointer["quality_grade"] == "A":
            status = "ready_a"
        elif pointer["quality_grade"] == "B":
            status = "ready_b"
        else:
            status = "invalid"
        manifest["report_readiness"][report_type] = {
            "status": status,
            "selected_snapshot_id": pointer["selected_snapshot_id"],
            "selected_file": pointer["selected_file"],
            "sha256": pointer["sha256"],
            "quality_profile": pointer["quality_profile"],
            "quality_grade": pointer["quality_grade"],
            "missing_core_fields": list(pointer.get("missing_core_fields", [])),
            "missing_optional_fields": list(pointer.get("missing_optional_fields", [])),
            "reasons": list(pointer.get("quality_reasons", [status])),
        }


def apply_pointer(manifest: dict[str, Any], pointer: dict[str, Any], snapshot: dict[str, Any]) -> None:
    pointer = deepcopy(pointer)
    pointer["missing_core_fields"] = list(snapshot.get("missing_core_fields", []))
    pointer["missing_optional_fields"] = list(snapshot.get("missing_optional_fields", []))
    pointer["quality_reasons"] = list(snapshot.get("quality_reasons", []))
    manifest["snapshots"][pointer["snapshot_type"]] = pointer
    manifest["generated_at"] = snapshot["published_at"]
    grade = snapshot["quality_grade"]
    if grade == "A":
        manifest["health"]["last_grade_a_at"] = snapshot["published_at"]
    elif grade == "B":
        manifest["health"]["last_grade_b_at"] = snapshot["published_at"]
    update_report_readiness(manifest)


def _effective_field_count(snapshot: dict[str, Any]) -> int:
    count = 0
    for item in snapshot.get("coverage", {}).values():
        if isinstance(item, dict):
            count += int(item.get("valid", 0))
    return count
