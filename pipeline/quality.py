from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from pipeline.contracts import ContractError, load_quality_profiles


TIMEZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class QualityResult:
    grade: str
    reasons: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    degradation_actions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "quality_grade": self.grade,
            "quality_reasons": list(self.reasons),
            "blocking_reasons": list(self.blocking_reasons),
            "degradation_actions": list(self.degradation_actions),
        }


def evaluate_quality(snapshot: dict[str, Any], quality_profile: str) -> QualityResult:
    profiles = load_quality_profiles()["profiles"]
    if quality_profile not in profiles:
        raise ContractError(f"Unknown quality profile: {quality_profile}")
    profile = profiles[quality_profile]

    blocking = _blocking_reasons(snapshot, quality_profile, profile)
    if blocking:
        return QualityResult("F", (), tuple(blocking), ())

    if quality_profile == "trading_evening":
        return _evaluate_evening(snapshot)

    if _meets_thresholds(snapshot, profile["grade_a"]):
        return QualityResult("A", tuple(_success_reasons(snapshot, "A")), (), ())

    if _meets_thresholds(snapshot, profile["grade_b"]):
        actions = ["cap capital_consistency_score at 60"]
        if _coverage(snapshot, "core")["valid"] < _coverage(snapshot, "core")["expected"]:
            actions.append("disable precise price levels for missing Core symbols")
        return QualityResult("B", tuple(_success_reasons(snapshot, "B")), (), tuple(actions))

    reasons = [
        "minimum B thresholds not met",
        _coverage_reason(snapshot, "indices"),
        _coverage_reason(snapshot, "core"),
        _coverage_reason(snapshot, "sectors_top"),
        _coverage_reason(snapshot, "sectors_bottom"),
    ]
    return QualityResult("F", (), tuple(reasons), ())


def apply_quality_result(snapshot: dict[str, Any], result: QualityResult) -> dict[str, Any]:
    snapshot.update(result.as_dict())
    return snapshot


def _blocking_reasons(
    snapshot: dict[str, Any], quality_profile: str, profile: dict[str, Any]
) -> list[str]:
    blocking: list[str] = []
    if snapshot.get("quality_profile") != quality_profile:
        blocking.append("snapshot quality_profile does not match requested profile")

    validation = snapshot.get("validation", {})
    for field in ("calendar_valid", "time_valid", "cross_field_valid"):
        if validation.get(field) is not True:
            blocking.append(f"validation.{field} is not true")

    report_date = str(snapshot.get("report_date", ""))
    market_date = str(snapshot.get("market_date", ""))
    rule = profile.get("market_date_rule")
    if rule == "report_date" and market_date != report_date:
        blocking.append("market_date must equal report_date for this profile")
    elif rule == "latest_completed_trading_day":
        latest = str(snapshot.get("market", {}).get("latest_completed_trading_day", ""))
        if not latest or market_date != latest or market_date > report_date:
            blocking.append("market_date is not the latest completed trading day")

    quote_window = profile.get("quote_window")
    if quote_window and not _quote_in_window(snapshot.get("quote_time_max"), quote_window):
        blocking.append("quote_time_max is outside the profile quote window")

    max_age = profile.get("max_quote_age_minutes")
    if max_age is not None and not _quote_is_fresh(snapshot, int(max_age)):
        blocking.append(f"quote_time_max is older than {max_age} minutes")

    if profile.get("realtime_expected") and snapshot.get("realtime_available") is not True:
        blocking.append("realtime data is required but unavailable")
    if not profile.get("realtime_expected") and snapshot.get("realtime_expected") is True:
        blocking.append("snapshot realtime_expected conflicts with quality profile")
    return blocking


def _evaluate_evening(snapshot: dict[str, Any]) -> QualityResult:
    based_on = snapshot.get("based_on_snapshot_id")
    base_grade = snapshot.get("market", {}).get("base_close_grade")
    base_valid = snapshot.get("validation", {}).get("base_snapshot_valid")
    if not based_on or base_valid is not True or base_grade not in {"A", "B"}:
        return QualityResult(
            "F",
            (),
            ("evening snapshot requires a verified same-day close snapshot",),
            (),
        )
    if base_grade == "A":
        return QualityResult("A", ("verified same-day A-grade close snapshot",), (), ())
    return QualityResult(
        "B",
        ("verified same-day B-grade close snapshot",),
        (),
        ("cap capital_consistency_score at 60",),
    )


def _meets_thresholds(snapshot: dict[str, Any], thresholds: dict[str, Any]) -> bool:
    if "base_close_grade" in thresholds:
        return snapshot.get("market", {}).get("base_close_grade") == thresholds["base_close_grade"]

    indices = _coverage(snapshot, "indices")
    core = _coverage(snapshot, "core")
    sectors_top = _coverage(snapshot, "sectors_top")
    sectors_bottom = _coverage(snapshot, "sectors_bottom")
    required_core = math.ceil(core["expected"] * float(thresholds.get("core_ratio", 0)))

    if indices["valid"] < int(thresholds.get("min_indices", 0)):
        return False
    if core["valid"] < required_core:
        return False
    if sectors_top["valid"] < int(thresholds.get("sector_top", 0)):
        return False
    if sectors_bottom["valid"] < int(thresholds.get("sector_bottom", 0)):
        return False

    turnover_valid = _market_flag(snapshot, "turnover_valid", "total_turnover")
    breadth_valid = _market_flag(snapshot, "breadth_valid", "breadth")
    if thresholds.get("require_turnover") and not turnover_valid:
        return False
    if thresholds.get("require_breadth") and not breadth_valid:
        return False
    if thresholds.get("require_turnover_or_breadth") and not (turnover_valid or breadth_valid):
        return False
    return True


def _market_flag(snapshot: dict[str, Any], flag: str, value_field: str) -> bool:
    market = snapshot.get("market", {})
    if market.get(flag) is True:
        return True
    value = market.get(value_field)
    return value is not None and value != {} and value != []


def _coverage(snapshot: dict[str, Any], key: str) -> dict[str, int | float]:
    value = snapshot.get("coverage", {}).get(key, {})
    return {
        "valid": int(value.get("valid", 0)),
        "expected": int(value.get("expected", 0)),
        "ratio": float(value.get("ratio", 0)),
    }


def _coverage_reason(snapshot: dict[str, Any], key: str) -> str:
    value = _coverage(snapshot, key)
    return f"{key} coverage {value['valid']}/{value['expected']}"


def _success_reasons(snapshot: dict[str, Any], grade: str) -> list[str]:
    reasons = [f"quality profile thresholds met for grade {grade}"]
    reasons.append(_coverage_reason(snapshot, "indices"))
    reasons.append(_coverage_reason(snapshot, "core"))
    return reasons


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(TIMEZONE)


def _quote_in_window(value: Any, window: dict[str, str]) -> bool:
    parsed = _parse_iso(value)
    if parsed is None:
        return False
    start = time.fromisoformat(window["start"])
    end = time.fromisoformat(window["end"])
    return start <= parsed.time().replace(tzinfo=None) <= end


def _quote_is_fresh(snapshot: dict[str, Any], max_age_minutes: int) -> bool:
    quote = _parse_iso(snapshot.get("quote_time_max"))
    started = _parse_iso(snapshot.get("started_at"))
    if quote is None or started is None:
        return False
    age_minutes = (started - quote).total_seconds() / 60
    return 0 <= age_minutes <= max_age_minutes
