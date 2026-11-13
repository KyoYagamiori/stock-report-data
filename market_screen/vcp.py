"""Causal VCP-inspired shadow observations; parameter choices are our hypotheses."""
from __future__ import annotations

import math
import statistics

VERSION = "vcp_shadow_20261113_v1"
FEATURES = ("vcp_evaluable", "vcp_setup", "vcp_contractions", "vcp_contraction_ratio",
            "vcp_dry_volume_ratio", "vcp_pivot_distance_atr", "vcp_trend_pass")
POLICY = {"swing_confirmation_bars": 2, "lookback_bars": 120, "minimum_base_bars": 14,
          "maximum_last_low_age": 15, "successive_depth_ratio_max": .8,
          "first_depth_max_pct": 35, "last_depth_max_pct": 8, "tight5_range_max_pct": 8,
          "dry_volume_ratio_max": .75, "breakout_volume_ratio_min": 1.5,
          "near_pivot_atr": .5, "extension_max_atr": .5}


def swings(bars):
    """A swing is visible only after two complete bars on its right exist."""
    out, n = [], POLICY["swing_confirmation_bars"]
    for i in range(n, len(bars) - n):
        b = bars[i]
        high = b["high"] > max(x["high"] for x in bars[i-n:i]) and b["high"] >= max(x["high"] for x in bars[i+1:i+n+1])
        low = b["low"] < min(x["low"] for x in bars[i-n:i]) and b["low"] <= min(x["low"] for x in bars[i+1:i+n+1])
        if high == low:  # Ambiguous outside bars cannot establish a turn order.
            continue
        point = {"kind": "high" if high else "low", "index": i, "day": b["day"],
                 "price": b["high"] if high else b["low"], "known_on": bars[i+n]["day"]}
        if out and out[-1]["kind"] == point["kind"]:
            replace = point["price"] >= out[-1]["price"] if high else point["price"] <= out[-1]["price"]
            if replace:
                out[-1] = point
        else:
            out.append(point)
    return out


def prepare(bars):
    """Freeze the base before the evaluation session; that session cannot move its pivot."""
    bars = bars[-POLICY["lookback_bars"]:]
    base = {"version": VERSION, "available": False, "matched": False,
            "scope": "vcp_inspired_price_volume_proxy_not_jlaw_proprietary_rules",
            "production_activation": False}
    if len(bars) < 65:
        return {**base, "reason": "insufficient_completed_history"}
    if any(not math.isfinite(float(b[k])) or b[k] <= 0 for b in bars for k in ("high", "low", "close")):
        return {**base, "reason": "invalid_completed_prices"}
    if any(not math.isfinite(float(b["volume"])) or b["volume"] < 0 for b in bars):
        return {**base, "reason": "invalid_completed_volume"}
    if any(b["day"] >= bars[i+1]["day"] for i, b in enumerate(bars[:-1])):
        raise ValueError("vcp_completed_bars_must_be_unique_and_ordered")
    points = swings(bars)
    pairs = [{"high": a, "low": b, "depth_pct": (1 - b["price"] / a["price"]) * 100}
             for a, b in zip(points, points[1:]) if a["kind"] == "high" and b["kind"] == "low" and b["price"] < a["price"]]
    legs = pairs[-1:]
    for pair in reversed(pairs[-4:-1]):
        if legs[0]["depth_pct"] > pair["depth_pct"] * POLICY["successive_depth_ratio_max"]:
            break
        if legs[0]["low"]["price"] <= pair["low"]["price"]:
            break
        legs.insert(0, pair)
    ranges = [max(b["high"]-b["low"], abs(b["high"]-a["close"]), abs(b["low"]-a["close"]))
              for a, b in zip(bars[-21:-1], bars[-20:])]
    atr = statistics.mean(ranges)
    volume_ref = statistics.median(b["volume"] for b in bars[-25:-5])
    dry = statistics.median(b["volume"] for b in bars[-5:]) / volume_ref if volume_ref > 0 else None
    ma50 = statistics.mean(b["close"] for b in bars[-50:])
    old_ma50 = statistics.mean(b["close"] for b in bars[-60:-10])
    trend = bars[-1]["close"] >= ma50 and ma50 > old_ma50
    tight = (max(b["high"] for b in bars[-5:]) / min(b["low"] for b in bars[-5:]) - 1) * 100
    count = len(legs)
    first, last = (legs[0], legs[-1]) if legs else (None, None)
    # Include overhead resistance after the first selected swing high.
    pivot = max(b["high"] for b in bars[first["high"]["index"]:]) if first else None
    base_bars = last["low"]["index"] - first["high"]["index"] + 1 if first else 0
    age = len(bars) - 1 - last["low"]["index"] if last else None
    checks = {"multiple_contracting_pullbacks": count >= 2,
              "base_long_enough": base_bars >= POLICY["minimum_base_bars"],
              "final_low_recent": age is not None and age <= POLICY["maximum_last_low_age"],
              "initial_depth_controlled": first is not None and first["depth_pct"] <= POLICY["first_depth_max_pct"],
              "last_depth_tight": last is not None and last["depth_pct"] <= POLICY["last_depth_max_pct"],
              "tight_last_five": tight <= POLICY["tight5_range_max_pct"],
              "volume_dry": dry is not None and dry <= POLICY["dry_volume_ratio_max"],
              "rising_ma50_context": trend, "atr_and_volume_available": atr > 0 and volume_ref > 0}
    return {**base, "available": atr > 0 and volume_ref > 0, "matched": all(checks.values()),
            "base_asof": bars[-1]["day"], "origin": last["low"]["day"] if last else None,
            "pivot": pivot, "invalidation_below": last["low"]["price"] if last else None,
            "contraction_depths_pct": [p["depth_pct"] for p in legs], "contraction_count": count,
            "contraction_ratio": last["depth_pct"] / first["depth_pct"] if first else 1.,
            "confirmed_swings": [{"high": p["high"]["day"], "low": p["low"]["day"],
                                  "known_on": p["low"]["known_on"]} for p in legs],
            "atr20": atr, "reference_volume": volume_ref, "dry_volume_ratio": dry,
            "tight5_range_pct": tight, "trend_pass": trend, "checks": checks,
            "previous_close": bars[-1]["close"], "risk_note": "reference_low_is_not_a_guaranteed_stop_fill"}


def observe(state, bar, completed=True):
    out = {**state, "observation_asof": bar["day"], "price": bar["close"],
           "bar_status": "completed" if completed else "provisional", "entry_qualified": False}
    if not state.get("available"):
        return {**out, "stage": "unavailable"}
    if bar["day"] <= state["base_asof"]:
        raise ValueError("vcp_observation_must_follow_frozen_base")
    pivot, atr = state.get("pivot"), state["atr20"]
    distance = (pivot - bar["close"]) / atr if pivot else None
    volume_ratio = bar["volume"] / state["reference_volume"] if completed else None
    stage = "no_vcp_setup"
    if state["matched"]:
        if bar["close"] < state["invalidation_below"]:
            stage = "invalidated"
        elif bar["close"] > pivot + POLICY["extension_max_atr"] * atr:
            stage = "extended_do_not_chase"
        elif bar["close"] > pivot:
            stage = ("mature_breakout" if state["previous_close"] > pivot else
                     "breakout_provisional" if not completed else
                     "breakout_close_volume_confirmed" if volume_ratio >= POLICY["breakout_volume_ratio_min"] else
                     "breakout_volume_unconfirmed")
        else:
            stage = "near_pivot" if distance <= POLICY["near_pivot_atr"] else "preparing"
    return {**out, "stage": stage, "distance_to_pivot_atr": distance,
            "completed_volume_ratio": volume_ratio, "same_time_volume_confirmation": "not_supplied" if not completed else "not_required_for_completed_daily_bar",
            "risk_from_pivot_pct": (1 - state["invalidation_below"] / pivot) * 100 if pivot else None}


def analyze(bars):
    if not bars:
        return {"version": VERSION, "available": False, "matched": False, "stage": "unavailable"}
    return observe(prepare(bars[:-1]), bars[-1])


def feature_values(observation):
    def bounded(value, default, low, high):
        return min(high, max(low, value)) if value is not None and math.isfinite(value) else default
    return {"vcp_evaluable": int(observation.get("available", False)),
            "vcp_setup": int(observation.get("matched", False)),
            "vcp_contractions": observation.get("contraction_count", 0),
            "vcp_contraction_ratio": bounded(observation.get("contraction_ratio"), 1., 0., 1.),
            "vcp_dry_volume_ratio": bounded(observation.get("dry_volume_ratio"), 1., 0., 5.),
            "vcp_pivot_distance_atr": bounded(observation.get("distance_to_pivot_atr"), 0., -5., 5.),
            "vcp_trend_pass": int(observation.get("trend_pass", False))}
