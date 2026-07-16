from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


TIMEZONE = ZoneInfo("Asia/Shanghai")


def record_simulation_day(screen: dict[str, Any], root: Path) -> Path:
    """Record a private, signal-only day for the 20-trading-day paper audit."""
    path = root / "reviews" / "MA5模拟盘" / "simulation_days.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    primary = screen.get("primary_candidate") or {}
    quality = screen.get("quality", {})
    payload: dict[str, Any] = {
        "recorded_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        "report_date": screen["report_date"],
        "phase": screen["phase"],
        "scan_id": screen["scan_id"],
        "completed_at": screen.get("completed_at"),
        "quality_grade": quality.get("grade"),
        "actionable": bool(quality.get("actionable")),
        "universe_coverage": quality.get("universe_coverage"),
        "history_coverage": quality.get("history_coverage"),
        "industry_coverage": quality.get("industry_coverage"),
        "on_time_before_1452": _on_time(screen.get("completed_at")) if screen["phase"] == "preclose" else None,
        "market_score": screen["market_environment"]["score"],
        "market_cap_pct": screen["market_environment"]["maximum_position_pct"],
        "candidate_code": primary.get("code"),
        "candidate_score": primary.get("score"),
        "buy_zone": [primary.get("buy_zone_low"), primary.get("buy_zone_high")],
        "hard_invalidation": primary.get("hard_invalidation"),
        "box_top": primary.get("box_top"),
        "ma5": primary.get("ma5"),
        "top10_codes": [card.get("code") for card in screen.get("top10", [])],
    }
    existing = _read_records(path)
    if any(item.get("scan_id") == screen["scan_id"] for item in existing):
        return path
    if screen["phase"] == "close":
        preclose = next(
            (
                item
                for item in reversed(existing)
                if item.get("phase") == "preclose" and item.get("report_date") == screen["report_date"]
            ),
            None,
        )
        if preclose:
            payload["preclose_candidate_code"] = preclose.get("candidate_code")
            payload["preclose_candidate_survived_close"] = bool(
                preclose.get("candidate_code")
                and preclose.get("candidate_code") in payload["top10_codes"]
            )
            preclose_ma5 = preclose.get("ma5")
            close_ma5 = primary.get("ma5") if primary.get("code") == preclose.get("candidate_code") else None
            payload["temporary_to_close_ma5_change_pct"] = (
                round((float(close_ma5) / float(preclose_ma5) - 1) * 100, 6)
                if preclose_ma5 and close_ma5
                else None
            )
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _write_status(root, [*existing, payload])
    return path


def simulation_status(root: Path) -> dict[str, Any]:
    path = root / "reviews" / "MA5模拟盘" / "simulation_days.jsonl"
    records = _read_records(path)
    close_records = [item for item in records if item.get("phase") == "close"]
    trading_days = sorted({item.get("report_date") for item in close_records if item.get("report_date")})
    a_records = [item for item in close_records if item.get("quality_grade") == "A"]
    actionable = [item for item in records if item.get("phase") == "preclose" and item.get("actionable")]
    preclose_records = [item for item in records if item.get("phase") == "preclose"]
    on_time = [item for item in preclose_records if item.get("on_time_before_1452") is True]
    coverage_pass = [
        item
        for item in preclose_records
        if min(
            float(item.get("universe_coverage") or 0),
            float(item.get("history_coverage") or 0),
            float(item.get("industry_coverage") or 0),
        )
        >= 0.95
    ]
    linked_close = [item for item in close_records if item.get("preclose_candidate_code")]
    survived = [item for item in linked_close if item.get("preclose_candidate_survived_close")]
    on_time_rate = round(len(on_time) / len(preclose_records), 4) if preclose_records else None
    coverage_rate = round(len(coverage_pass) / len(preclose_records), 4) if preclose_records else None
    return {
        "trading_days_recorded": len(trading_days),
        "target_days": 20,
        "complete": len(trading_days) >= 20,
        "grade_a_close_rate": round(len(a_records) / len(close_records), 4) if close_records else None,
        "actionable_preclose_count": len(actionable),
        "preclose_on_time_rate": on_time_rate,
        "preclose_coverage_pass_rate": coverage_rate,
        "preclose_candidate_close_survival_rate": round(len(survived) / len(linked_close), 4) if linked_close else None,
        "false_breakout_or_close_rejection_count": len(linked_close) - len(survived),
        "timing_and_coverage_gate_passed": bool(
            len(trading_days) >= 20
            and on_time_rate is not None
            and on_time_rate >= 0.90
            and coverage_rate is not None
            and coverage_rate >= 0.95
        ),
        "first_date": trading_days[0] if trading_days else None,
        "last_date": trading_days[-1] if trading_days else None,
    }


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _write_status(root: Path, records: list[dict[str, Any]]) -> None:
    del records
    status = simulation_status(root)
    path = root / "reviews" / "MA5模拟盘" / "status.json"
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _on_time(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        return False
    local = parsed.astimezone(TIMEZONE)
    return (local.hour, local.minute, local.second) <= (14, 52, 0)
