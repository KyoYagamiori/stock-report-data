from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ma5_system.data import listing_age_days, safe_number


@dataclass(frozen=True)
class ScoreResult:
    card: dict[str, Any]
    eligible: bool
    failures: tuple[str, ...]


def apply_direction_context(record: dict[str, Any], direction: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(record)
    if direction is None:
        updated.update(
            {
                "direction_rank": None,
                "direction_strength": None,
                "direction_positive_ratio": None,
                "direction_retreating": True,
            }
        )
        return updated
    rank = int(direction["rank"])
    median_pct = safe_number(direction.get("median_pct_change")) or 0.0
    positive_ratio = safe_number(direction.get("positive_ratio")) or 0.0
    updated.update(
        {
            "direction_rank": rank,
            "direction_strength": safe_number(direction.get("strength")),
            "direction_positive_ratio": positive_ratio,
            "direction_retreating": rank > 3 or median_pct <= 0 or positive_ratio < 0.5,
        }
    )
    return updated


def rank_directions(spot: pd.DataFrame, previous: list[str] | None = None) -> list[dict[str, Any]]:
    previous = previous or []
    if spot.empty or "industry" not in spot.columns:
        return []
    records: list[dict[str, Any]] = []
    valid = spot.dropna(subset=["pct_change", "amount"]).copy()
    for industry, group in valid.groupby("industry"):
        if not industry or industry == "Unknown" or len(group) < 3:
            continue
        pct = pd.to_numeric(group["pct_change"], errors="coerce")
        amount = pd.to_numeric(group["amount"], errors="coerce")
        positive_ratio = float((pct > 0).mean()) if len(pct) else 0.0
        median_pct = float(pct.median()) if pct.notna().any() else 0.0
        total_amount = float(amount.sum()) if amount.notna().any() else 0.0
        persistence = 1.0 if industry in previous else 0.0
        strength = median_pct * 2.0 + positive_ratio * 4.0 + min(total_amount / 50_000_000_000, 2.0) + persistence
        records.append(
            {
                "name": str(industry),
                "median_pct_change": round(median_pct, 4),
                "positive_ratio": round(positive_ratio, 4),
                "total_amount": total_amount,
                "persistence": bool(persistence),
                "strength": round(strength, 4),
                "members": int(len(group)),
            }
        )
    records.sort(key=lambda item: (item["strength"], item["total_amount"]), reverse=True)
    for index, record in enumerate(records, start=1):
        record["rank"] = index
        record["role"] = "active" if index <= 3 else "reserve" if index <= 5 else "other"
    return records


def build_technical_record(
    quote: dict[str, Any],
    history: pd.DataFrame,
    market_date: str,
    phase: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    history = history.copy()
    for column in ("date", "close", "high", "low", "amount"):
        if column not in history.columns:
            history[column] = None
    history = history.sort_values("date")
    history = history[history["date"].astype(str) < market_date]
    closes = pd.to_numeric(history["close"], errors="coerce").dropna().tolist()
    highs = pd.to_numeric(history["high"], errors="coerce").dropna().tolist()
    lows = pd.to_numeric(history["low"], errors="coerce").dropna().tolist()
    amounts = pd.to_numeric(history["amount"], errors="coerce").dropna().tolist()
    current = safe_number(quote.get("latest"))
    current_high = safe_number(quote.get("high")) or current
    current_low = safe_number(quote.get("low")) or current
    if current is None:
        return {**quote, "history_days": len(closes), "technical_complete": False}
    combined_close = [*closes, current]
    combined_high = [*highs, current_high]
    combined_low = [*lows, current_low]
    ma = {period: _mean_last(combined_close, period) for period in (5, 10, 20, 60)}
    prior_ma5 = _mean_last(closes, 5)
    box_days = int(config["candidate"]["box_lookback_days"])
    box_source_highs = highs[-box_days:] or combined_high[-box_days:]
    box_source_lows = lows[-box_days:] or combined_low[-box_days:]
    box_top = max(box_source_highs) if box_source_highs else None
    box_bottom = min(box_source_lows) if box_source_lows else None
    recent_days = int(config["candidate"]["recent_low_days"])
    recent_low = min(combined_low[-recent_days:]) if combined_low else None
    invalid_base = max(value for value in (ma[10], recent_low) if value is not None)
    hard_invalid = invalid_base * (1 - config["candidate"]["invalidation_buffer_pct"] / 100)
    distance = (current / ma[5] - 1) * 100 if ma[5] else None
    buy_zone_pct = config["candidate"]["buy_zone_pct"] / 100
    buy_low = max(ma[5] * (1 - buy_zone_pct), hard_invalid * 1.002) if ma[5] else None
    buy_high = ma[5] * (1 + buy_zone_pct) if ma[5] else None
    entry_reference = min(max(current, buy_low or current), buy_high or current)
    risk_per_share = entry_reference - hard_invalid
    planned_risk_pct = risk_per_share / entry_reference * 100 if entry_reference > 0 else None
    reward = (box_top - entry_reference) if box_top is not None else None
    reward_risk = reward / risk_per_share if reward is not None and risk_per_share > 0 else None
    touch_threshold = (ma[5] or current) * 1.01
    touched_today = current_low <= touch_threshold and current >= (ma[5] or current)
    touched_recent = _recent_touch(history, 2)
    median_amount_20 = float(pd.Series(amounts[-20:]).median()) if amounts else None
    amount = safe_number(quote.get("amount"))
    amount_ratio = amount / median_amount_20 if amount and median_amount_20 else None
    confirmation = max(value for value in (ma[5] * 1.002 if ma[5] else None, safe_number(quote.get("open")), closes[-1] if closes else None) if value is not None)
    return {
        **quote,
        "market_date": market_date,
        "phase": phase,
        "history_days": len(closes),
        "technical_complete": len(closes) >= 59 and all(ma[period] is not None for period in (5, 10, 20, 60)),
        "ma5": ma[5],
        "ma10": ma[10],
        "ma20": ma[20],
        "ma60": ma[60],
        "ma5_prior": prior_ma5,
        "ma5_rising": ma[5] is not None and prior_ma5 is not None and ma[5] > prior_ma5,
        "distance_to_ma5_pct": distance,
        "touched_ma5_recently": touched_today or touched_recent,
        "reclaimed_ma5": bool(ma[5] and current >= ma[5]),
        "box_top": box_top,
        "box_bottom": box_bottom,
        "recent_low": recent_low,
        "buy_zone_low": buy_low,
        "buy_zone_high": buy_high,
        "confirmation_price": confirmation,
        "hard_invalidation": hard_invalid,
        "planned_risk_pct": planned_risk_pct,
        "reward_risk": reward_risk,
        "target_2r": entry_reference + 2 * risk_per_share,
        "entry_reference": entry_reference,
        "median_amount_20": median_amount_20,
        "amount_ratio_20": amount_ratio,
        "profit_zone_low": min(box_top, entry_reference + 2 * risk_per_share) if box_top is not None else entry_reference + 2 * risk_per_share,
        "profit_zone_high": box_top,
        "ma5_warning": ma[5],
    }


def score_stock(
    record: dict[str, Any],
    direction_rank: int | None,
    config: dict[str, Any],
) -> ScoreResult:
    failures = _eligibility_failures(record, direction_rank, config)
    direction = {1: 30, 2: 27, 3: 24, 4: 18, 5: 15}.get(direction_rank or 99, 0)
    trend = 0
    trend += 8 if record.get("ma5_rising") else 0
    trend += 7 if _gt(record, "ma5", "ma10") else 0
    trend += 5 if _price_gt(record, "ma5") else 0
    trend += 3 if _gt(record, "ma10", "ma20") else 0
    trend += 2 if _price_gt(record, "ma20") else 0
    pullback = 0
    pullback += 10 if record.get("touched_ma5_recently") and record.get("reclaimed_ma5") else 0
    distance = safe_number(record.get("distance_to_ma5_pct"))
    pullback += 5 if distance is not None and -0.5 <= distance <= 1.5 else 3 if distance is not None and -1 <= distance <= 2.5 else 0
    pullback += 5 if record.get("confirmation_met") else 3 if (safe_number(record.get("pct_change")) or 0) > 0 else 2 if record.get("reclaimed_ma5") else 0
    volume = 0
    ratio = safe_number(record.get("amount_ratio_20"))
    volume += 8 if ratio is not None and 0.8 <= ratio <= 1.8 else 5 if ratio is not None and 0.5 <= ratio <= 2.5 else 0
    volume += 4 if (safe_number(record.get("pct_change")) or 0) > 0 else 0
    volume += 3 if (safe_number(record.get("turnover")) or 0) > 0 else 0
    liquidity = 0
    median_amount = safe_number(record.get("median_amount_20"))
    liquidity += 4 if median_amount is not None and median_amount >= config["universe"]["minimum_median_amount_20"] else 0
    risk = safe_number(record.get("planned_risk_pct"))
    liquidity += 4 if risk is not None and 0 < risk <= config["candidate"]["maximum_planned_risk_pct"] else 0
    liquidity += 2 if not record.get("one_price_limit") and not record.get("event_risk") else 0
    score = min(100, direction + trend + pullback + volume + liquidity)
    reward_risk = safe_number(record.get("reward_risk"))
    grade = str(record.get("data_grade", "F"))
    a_plus = (
        not failures
        and score >= config["candidate"]["a_plus_score"]
        and reward_risk is not None
        and reward_risk >= config["candidate"]["minimum_reward_risk"]
        and direction_rank is not None
        and direction_rank <= 3
        and not record.get("direction_retreating")
        and grade == "A"
        and not record.get("one_price_limit")
        and not record.get("major_data_gap")
    )
    card = {
        **record,
        "direction_rank": direction_rank,
        "score_components": {
            "direction": direction,
            "trend": trend,
            "pullback_reclaim": pullback,
            "volume_price": volume,
            "liquidity_risk": liquidity,
        },
        "score": score,
        "eligible": not failures and score >= config["candidate"]["minimum_score"],
        "a_plus": a_plus,
        "eligibility_failures": failures,
    }
    return ScoreResult(card=card, eligible=bool(card["eligible"]), failures=tuple(failures))


def market_score(
    spot: pd.DataFrame,
    indices: list[dict[str, Any]],
    directions: list[dict[str, Any]],
    turnover_ratio: float | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    valid_pct = pd.to_numeric(spot.get("pct_change", pd.Series(dtype=float)), errors="coerce").dropna()
    trend_points = [safe_number(item.get("trend_points")) for item in indices]
    if any(value is not None for value in trend_points):
        index_component = round(min(30.0, sum(value or 0 for value in trend_points)), 2)
    else:
        positive_indices = sum(1 for item in indices if (safe_number(item.get("pct_change")) or 0) > 0)
        index_component = round(30 * positive_indices / max(3, len(indices)), 2)
    breadth_ratio = float((valid_pct > 0).mean()) if len(valid_pct) else 0.0
    breadth_component = round(max(0.0, min(25.0, (breadth_ratio - 0.30) / 0.35 * 25)), 2)
    if turnover_ratio is None:
        turnover_component = 7.5
    else:
        turnover_component = round(max(0.0, min(15.0, 7.5 + (turnover_ratio - 1.0) * 25)), 2)
    active = [item for item in directions[:3] if item["positive_ratio"] >= 0.55 and item["median_pct_change"] > 0]
    persistent = sum(1 for item in active if item.get("persistence"))
    sector_component = round(min(20.0, len(active) * 5 + persistent * 2.5), 2)
    limit_down = int((valid_pct <= -9.95).sum()) if len(valid_pct) else 0
    limit_down_ratio = limit_down / max(1, len(valid_pct))
    risk_component = round(max(0.0, min(10.0, 10 - limit_down_ratio * 500)), 2)
    components = {
        "index_trend": index_component,
        "breadth": breadth_component,
        "turnover": turnover_component,
        "sector_persistence": sector_component,
        "limit_down_risk": risk_component,
    }
    total = round(sum(components.values()), 2)
    market = config["market"]
    if total >= market["strong_minimum"]:
        regime, cap = "strong", market["strong_cap_pct"]
    elif total >= market["neutral_minimum"]:
        regime, cap = "neutral", market["neutral_cap_pct"]
    else:
        regime, cap = "weak", market["weak_cap_pct"]
    return {
        "score": total,
        "regime": regime,
        "maximum_position_pct": cap,
        "components": components,
        "breadth_ratio": round(breadth_ratio, 4),
        "limit_down_count_proxy": limit_down,
        "turnover_ratio": turnover_ratio,
    }


def _eligibility_failures(record: dict[str, Any], direction_rank: int | None, config: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    universe = config["universe"]
    candidate = config["candidate"]
    history_days = int(record.get("history_days") or 0)
    if record.get("is_st") or record.get("suspended"):
        failures.append("excluded_security_status")
    if listing_age_days(record.get("listing_date"), record.get("market_date", ""), history_days) < universe["minimum_listing_days"]:
        failures.append("listing_age_below_60_days")
    if history_days < universe["minimum_history_days"]:
        failures.append("history_below_60_days")
    if (safe_number(record.get("median_amount_20")) or 0) < universe["minimum_median_amount_20"]:
        failures.append("median_amount_below_100m")
    if not record.get("ma5_rising"):
        failures.append("ma5_not_rising")
    if not _gt(record, "ma5", "ma10"):
        failures.append("ma5_not_above_ma10")
    distance = safe_number(record.get("distance_to_ma5_pct"))
    if distance is None or not candidate["distance_to_ma5_min_pct"] <= distance <= candidate["distance_to_ma5_max_pct"]:
        failures.append("price_outside_ma5_distance")
    if not record.get("touched_ma5_recently") or not record.get("reclaimed_ma5"):
        failures.append("no_recent_ma5_reclaim")
    risk = safe_number(record.get("planned_risk_pct"))
    if risk is None or risk <= 0 or risk > candidate["maximum_planned_risk_pct"]:
        failures.append("planned_risk_over_5pct")
    buy_low = safe_number(record.get("buy_zone_low"))
    buy_high = safe_number(record.get("buy_zone_high"))
    if buy_low is None or buy_high is None or buy_low > buy_high:
        failures.append("invalid_buy_zone")
    if direction_rank is None or direction_rank > 5:
        failures.append("direction_not_top5")
    if record.get("one_price_limit"):
        failures.append("one_price_limit")
    return failures


def _mean_last(values: list[float], period: int) -> float | None:
    return float(sum(values[-period:]) / period) if len(values) >= period else None


def _recent_touch(history: pd.DataFrame, days: int) -> bool:
    if len(history) < 6:
        return False
    frame = history.copy().tail(days + 5)
    closes = pd.to_numeric(frame["close"], errors="coerce")
    lows = pd.to_numeric(frame["low"], errors="coerce")
    rolling = closes.rolling(5).mean()
    tail = pd.DataFrame({"close": closes, "low": lows, "ma5": rolling}).tail(days)
    return bool(((tail["low"] <= tail["ma5"] * 1.01) & (tail["close"] >= tail["ma5"])).any())


def _gt(record: dict[str, Any], left: str, right: str) -> bool:
    a, b = safe_number(record.get(left)), safe_number(record.get(right))
    return a is not None and b is not None and a > b


def _price_gt(record: dict[str, Any], field: str) -> bool:
    price, value = safe_number(record.get("latest")), safe_number(record.get(field))
    return price is not None and value is not None and price >= value
