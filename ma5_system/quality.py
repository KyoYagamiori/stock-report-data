from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


TIMEZONE = ZoneInfo("Asia/Shanghai")
REQUIRED_CARD_FIELDS = (
    "code",
    "name",
    "score",
    "ma5",
    "ma10",
    "box_top",
    "box_bottom",
    "buy_zone_low",
    "buy_zone_high",
    "confirmation_price",
    "hard_invalidation",
    "reward_risk",
)


def assess_quality(
    universe_total: int,
    valid_quotes: int,
    history_ready: int,
    industry_ready: int,
    quote_time_max: str | None,
    cards: list[dict[str, Any]],
    phase: str,
    completed_at: datetime,
    config: dict[str, Any],
    *,
    market_complete: bool = True,
    deep_scan_complete: bool = True,
    is_trading_day: bool = True,
    calendar_valid: bool = True,
) -> dict[str, Any]:
    expected_min = int(config["universe"]["expected_min_stocks"])
    denominator = max(universe_total, expected_min)
    quote_coverage = valid_quotes / denominator if denominator else 0.0
    history_coverage = history_ready / max(1, valid_quotes)
    industry_coverage = industry_ready / max(1, valid_quotes)
    quote_age = _quote_age_minutes(quote_time_max, completed_at)
    phase_fields = REQUIRED_CARD_FIELDS + (("minute_vwap", "local_tail_high", "minute_quote_time") if phase == "preclose" else ())
    cards_complete = all(all(card.get(field) is not None for field in phase_fields) for card in cards)
    cards_complete = cards_complete and all(
        card.get("daily_history_refreshed") is True and card.get("event_data_complete") is True
        for card in cards
    )
    if phase == "preclose":
        cards_complete = cards_complete and all(
            card.get("intraday_data_complete") is True
            for card in cards
        )
    quality = config["quality"]
    reasons: list[str] = []
    if quote_coverage < quality["grade_a_universe_coverage"]:
        reasons.append(f"universe coverage {quote_coverage:.2%} below 95%")
    if history_coverage < quality["grade_a_history_coverage"]:
        reasons.append(f"history coverage {history_coverage:.2%} below 95%")
    if industry_coverage < quality["grade_a_industry_coverage"]:
        reasons.append(f"industry coverage {industry_coverage:.2%} below 95%")
    if quote_age is None or quote_age > quality["maximum_quote_age_minutes"]:
        reasons.append("quote age exceeds 10 minutes")
    if not cards_complete:
        reasons.append("Top10 card fields are incomplete")
    if not market_complete:
        reasons.append("market environment inputs are incomplete")
    if not deep_scan_complete:
        reasons.append("Top30 deep-data refresh did not cover enough candidates")
    if not calendar_valid:
        reasons.append("trading calendar is unverified")
    if not is_trading_day:
        reasons.append("report date is not an A-share trading day")
    grade_a = not reasons
    grade_b = (
        is_trading_day
        and calendar_valid
        and quote_coverage >= quality["grade_b_universe_coverage"]
        and history_coverage >= quality["grade_b_history_coverage"]
        and industry_coverage >= quality["grade_b_industry_coverage"]
        and quote_age is not None
        and quote_age <= 30
    )
    grade = "A" if grade_a else "B" if grade_b else "F"
    deadline_met = True
    if phase == "preclose":
        deadline = datetime.strptime(quality["preclose_action_deadline"], "%H:%M").time()
        deadline_met = completed_at.astimezone(TIMEZONE).time() <= deadline
        if not deadline_met:
            reasons.append("preclose scan completed after 14:52")
    actionable = grade == "A" and phase == "preclose" and deadline_met
    return {
        "grade": grade,
        "report_readiness": "ready_a" if grade == "A" else "ready_b" if grade == "B" else "not_ready",
        "actionable": actionable,
        "next_day_reference_only": phase == "preclose" and not deadline_met,
        "universe_coverage": round(quote_coverage, 6),
        "history_coverage": round(history_coverage, 6),
        "industry_coverage": round(industry_coverage, 6),
        "market_complete": market_complete,
        "deep_scan_complete": deep_scan_complete,
        "calendar_valid": calendar_valid,
        "is_trading_day": is_trading_day,
        "quote_age_minutes": quote_age,
        "top10_complete": cards_complete,
        "reasons": reasons,
    }


def _quote_age_minutes(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TIMEZONE)
    return round(max(0.0, (now.astimezone(TIMEZONE) - parsed.astimezone(TIMEZONE)).total_seconds() / 60), 3)
