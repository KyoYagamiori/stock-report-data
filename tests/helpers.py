from __future__ import annotations

from copy import deepcopy
from typing import Any


def coverage(valid: int, expected: int) -> dict[str, Any]:
    ratio = 1.0 if expected == 0 else valid / expected
    return {"valid": valid, "expected": expected, "ratio": ratio}


def valid_snapshot() -> dict[str, Any]:
    return {
        "schema_version": "1.6.1",
        "snapshot_id": "20260716-1135-noon-full-run123",
        "workflow_run_id": "run123",
        "workflow_attempt": 1,
        "snapshot_type": "noon",
        "snapshot_mode": "full",
        "quality_profile": "trading_noon",
        "quality_grade": "A",
        "quality_reasons": ["all core fields valid"],
        "blocking_reasons": [],
        "degradation_actions": [],
        "report_date": "2026-07-16",
        "report_cycle": "2026-07-16-noon",
        "market_date": "2026-07-16",
        "market_session": "noon_close",
        "planned_at": "2026-07-16T11:35:00+08:00",
        "started_at": "2026-07-16T11:36:00+08:00",
        "published_at": "2026-07-16T11:38:00+08:00",
        "quote_time_min": "2026-07-16T11:30:00+08:00",
        "quote_time_max": "2026-07-16T11:30:05+08:00",
        "realtime_expected": True,
        "realtime_available": True,
        "based_on_snapshot_id": None,
        "suitable_reports": ["noon"],
        "coverage": {
            "indices": coverage(3, 3),
            "core": coverage(10, 10),
            "watch": coverage(14, 14),
            "market_breadth": coverage(5, 5),
            "sectors_top": coverage(5, 5),
            "sectors_bottom": coverage(5, 5),
        },
        "missing_core_fields": [],
        "missing_optional_fields": [],
        "warnings": [],
        "validation": {
            "schema_valid": True,
            "time_valid": True,
            "calendar_valid": True,
            "cross_field_valid": True,
        },
        "source_status": {},
        "market": {"turnover_valid": True, "breadth_valid": True},
        "stocks": [
            {"code": "600584", "name": "长电科技", "pool": "core", "valid_quote": True}
        ],
    }


def valid_manifest(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = deepcopy(snapshot or valid_snapshot())
    snapshot_id = snapshot["snapshot_id"]
    selected_file = f"output/archive/2026/07/16/noon/{snapshot_id}.json"
    pointer = {
        "selected_snapshot_id": snapshot_id,
        "selected_file": selected_file,
        "latest_alias": "output/latest/noon/report_data_compact.json",
        "schema_version": "1.6.1",
        "sha256": "a" * 64,
        "snapshot_type": "noon",
        "quality_profile": "trading_noon",
        "quality_grade": "A",
        "report_cycle": "2026-07-16-noon",
        "market_date": "2026-07-16",
        "quote_time_max": "2026-07-16T11:30:05+08:00",
        "suitable_reports": ["noon"],
    }
    empty_readiness = {
        "status": "not_ready",
        "selected_snapshot_id": None,
        "selected_file": None,
        "sha256": None,
        "quality_profile": None,
        "quality_grade": None,
        "missing_core_fields": [],
        "missing_optional_fields": [],
        "reasons": ["not generated"],
    }
    noon_readiness = {
        **deepcopy(empty_readiness),
        "status": "ready_a",
        "selected_snapshot_id": snapshot_id,
        "selected_file": selected_file,
        "sha256": "a" * 64,
        "quality_profile": "trading_noon",
        "quality_grade": "A",
        "reasons": ["ready"],
    }
    return {
        "schema_version": "1.6.1",
        "generated_at": "2026-07-16T11:38:00+08:00",
        "calendar": {
            "date": "2026-07-16",
            "is_trading_day": True,
            "latest_completed_trading_day": "2026-07-15",
            "next_trading_day": "2026-07-17",
            "source": "test-calendar",
        },
        "snapshots": {"early": None, "noon": pointer, "close": None, "evening": None, "intraday": None},
        "report_readiness": {
            "early": deepcopy(empty_readiness),
            "noon": noon_readiness,
            "evening": deepcopy(empty_readiness),
        },
        "health": {
            "latest_run": "output/health/latest_run.json",
            "last_grade_a_at": "2026-07-16T11:38:00+08:00",
            "last_grade_b_at": None,
        },
    }
