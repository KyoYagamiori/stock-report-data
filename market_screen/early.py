"""Early-stage BOLL discovery. Research triage, never a fitted probability."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics

from .research import percentile

VERSION = "boll_early_v3_20261105"
POOLS = ("fresh_mid_reclaim", "first_mid_retest", "squeeze_prepare", "first_expansion")
DEFAULTS = {
    "fresh_max_age": 1, "fresh_max_distance_atr": .5,
    "retest_max_age": 10, "retest_tolerance_atr": .35,
    "retest_advance_atr": .75, "expansion_max_distance_atr": 2.5,
    "maximum_mid_slope_weakness_atr": -.25,
    "prepare_bandwidth_percentile": .35, "squeeze_percentile": .25,
    "pool_limit": 20, "shortlist_limit": 15, "valid_sessions": 3,
    "intraday_max_quote_age_seconds": 120,
}


def completed_state(bars, series):
    """Retain exact sufficient history for tomorrow's provisional 20-day band."""
    if len(bars) < 145:
        return {"version": VERSION, "available": False}
    points, ranges = [], []
    contraction_origin = None
    for i in range(1, len(bars)):
        b, prev = bars[i], bars[i - 1]
        ranges.append(max(b["high"] - b["low"], abs(b["high"] - prev["close"]),
                          abs(b["low"] - prev["close"])))
        if i < 24:
            continue
        item, old = series[i], series[i - 1]
        reference = [s["width"] for s in series[max(19, i - 120):i]]
        shrinking = item["width"] < old["width"]
        contraction_origin = (contraction_origin or prev["day"]) if shrinking else None
        atr = statistics.mean(ranges[-20:])
        points.append({
            "day": b["day"], "close": b["close"], "open": b["open"],
            "high": b["high"], "low": b["low"], "mid": item["mid"],
            "upper": item["upper"], "lower": item["lower"], "width": item["width"],
            "atr20": atr, "volume": b["volume"],
            "width_percentile": percentile(item["width"], reference) if len(reference) == 120 else None,
            "contraction_origin": contraction_origin,
            "mid_slope_5d_atr": (item["mid"] - series[i - 5]["mid"]) / atr if atr else None,
            "return_5d_pct": (b["close"] / bars[i - 5]["close"] - 1) * 100,
            "return_20d_pct": (b["close"] / bars[i - 20]["close"] - 1) * 100,
            "prior20_high": max(r["high"] for r in bars[i - 20:i]),
            "support_low_5d": min(r["low"] for r in bars[i - 4:i + 1]),
            "volume_ratio_complete": b["volume"] / statistics.median([r["volume"] for r in bars[i - 20:i]])
                if statistics.median([r["volume"] for r in bars[i - 20:i]]) > 0 else None,
            "mid_turn_up_close_threshold": bars[i - 20]["close"],
        })
    from .vcp import analyze, prepare
    return {"version": VERSION, "available": True, "asof": bars[-1]["day"],
            "vcp_completed": analyze(bars), "vcp_next_session": prepare(bars),
            "points": points[-16:], "closes": [r["close"] for r in bars[-21:]],
            "width_reference": [s["width"] for s in series[-120:]],
            "last19_true_ranges": ranges[-19:]}


def project(state, quote):
    """19 completed closes + current cumulative OHLC; no synthetic completed bar."""
    p = state["points"]
    closes = state["closes"][-19:] + [quote["close"]]
    mid, sigma = statistics.mean(closes), statistics.pstdev(closes)
    atr = statistics.mean(state["last19_true_ranges"] + [
        max(quote["high"] - quote["low"], abs(quote["high"] - state["closes"][-1]),
            abs(quote["low"] - state["closes"][-1]))])
    width = 4 * sigma / mid
    point = {"day": quote["date"], **{k: quote[k] for k in ("open", "high", "low", "close", "volume")},
             "mid": mid, "upper": mid + 2 * sigma, "lower": mid - 2 * sigma,
             "width": width, "atr20": atr, "width_percentile": percentile(width, state["width_reference"]),
             "contraction_origin": (p[-1]["contraction_origin"] or p[-1]["day"]) if width < p[-1]["width"] else None,
             "mid_slope_5d_atr": (mid - p[-5]["mid"]) / atr if atr else None,
             "return_5d_pct": (quote["close"] / state["closes"][-5] - 1) * 100,
             "return_20d_pct": (quote["close"] / state["closes"][-20] - 1) * 100,
             "support_low_5d": min([r["low"] for r in p[-4:]] + [quote["low"]]),
             "volume_ratio_complete": None,
             "mid_turn_up_close_threshold": state["closes"][-20]}
    return p + [point]


def classify(points, config=None):
    c = {**DEFAULTS, **(config or {})}
    p, prev = points[-1], points[-2]
    atr = p["atr20"]
    if not atr or not math.isfinite(atr) or atr <= 0:
        return [], "unavailable", None
    distance = (p["close"] - p["mid"]) / atr
    crosses = [i for i in range(1, len(points))
               if points[i - 1]["close"] < points[i - 1]["mid"] and points[i]["close"] >= points[i]["mid"]]
    cross = crosses[-1] if crosses else None
    age = len(points) - 1 - cross if cross is not None else None
    origin = points[cross]["day"] if cross is not None else None
    slope_ok = p["mid_slope_5d_atr"] is not None and p["mid_slope_5d_atr"] >= c["maximum_mid_slope_weakness_atr"]
    setups = []
    if slope_ok and age is not None and age <= c["fresh_max_age"] and 0 <= distance <= c["fresh_max_distance_atr"]:
        setups.append({"pool": POOLS[0], "origin": origin, "signal_age_sessions": age})
    if (slope_ok and age is not None and 2 <= age <= c["retest_max_age"]
            and 0 <= distance <= .75 and abs(p["low"] - p["mid"]) <= c["retest_tolerance_atr"] * atr):
        advance = next((j for j in range(cross + 1, len(points) - 1)
                        if points[j]["close"] - points[j]["mid"] >= c["retest_advance_atr"] * points[j]["atr20"]), None)
        # Only a return AFTER clear advancement is a retest. Initial basing
        # near the crossing is not a prior failed "first pullback".
        touched_before = advance is not None and any(
            x["low"] <= x["mid"] + c["retest_tolerance_atr"] * x["atr20"]
            for x in points[advance + 1:-1])
        if advance is not None and not touched_before and p["close"] > p["open"]:
            setups.append({"pool": POOLS[1], "origin": origin, "signal_age_sessions": age})
    q = p.get("width_percentile")
    contracting = p["width"] < prev["width"] and prev["width"] < points[-3]["width"]
    if (slope_ok and contracting and q is not None and q <= c["prepare_bandwidth_percentile"]
            and -.35 <= distance <= .5 and p.get("contraction_origin")):
        contraction_age, j = 0, len(points) - 1
        while j > 0 and points[j]["width"] < points[j - 1]["width"]:
            contraction_age += 1; j -= 1
        setups.append({"pool": POOLS[2], "origin": p["contraction_origin"],
                       "signal_age_sessions": contraction_age, "signal_age_is_lower_bound": j == 0})
    def expansion(i):
        x, prior = points[i], points[i - 1]
        squeeze = any(z.get("width_percentile") is not None and z["width_percentile"] <= c["squeeze_percentile"]
                      for z in points[max(0, i - 5):i])
        return (squeeze and x["upper"] > prior["upper"] and x["width"] > prior["width"]
                and prior["width"] <= points[max(0, i - 2)]["width"]
                and x["close"] > prior["upper"] and prior["close"] <= prior["upper"])
    if (slope_ok and 0 <= distance <= c["expansion_max_distance_atr"]
            and p["close"] - prev["upper"] <= .5 * atr and expansion(len(points) - 1)):
        setups.append({"pool": POOLS[3], "origin": p["day"], "signal_age_sessions": 0})
    stage = ("initial_reclaim" if any(s["pool"] == POOLS[0] for s in setups) else
             "first_retest" if any(s["pool"] == POOLS[1] for s in setups) else
             "initial_expansion" if any(s["pool"] == POOLS[3] for s in setups) else
             "preparing" if setups else
             "mature_extension" if p["close"] >= p["mid"] and age is not None and age > 1 else "no_early_setup")
    return setups, stage, distance


def quote_errors(quote, code, dates, now, config):
    from .quotes import validate_quote
    if not quote or quote.get("code") != code:
        return ["missing_or_mismatched_quote"]
    phase = dates["phase"]
    errors = validate_quote(quote, dates["report_date"], phase, now=now)
    if not errors and phase == "intraday":
        quoted = datetime.fromisoformat(quote["date"] + "T" + quote["time"] + "+08:00")
        if (now - quoted).total_seconds() > config["intraday_max_quote_age_seconds"]:
            errors.append("stale_intraday_quote")
    return errors


def evaluate(row, dates, now, config=None, quote=None):
    c = {**DEFAULTS, **(config or {})}
    i = row.get("indicators") or {}
    state = i.get("early_state") or {}
    reasons = []
    gaps = ["corporate_action_window_requires_source_review", "company_catalyst_review_required",
            "dated_subsector_benchmark_unavailable"]
    intraday = dates["phase"] in ("noon", "intraday")
    if row.get("status") != "screened":
        reasons.append("daily_record_not_screened")
    if not state.get("available") or state.get("version") != VERSION or state.get("asof") != dates["market_date"]:
        reasons.append("early_state_missing_or_wrong_date")
    if not i.get("history_current") or i.get("bar_count", 0) < c.get("minimum_history_bars", 160):
        reasons.append("completed_history_not_eligible")
    if "ST" in str(row.get("name", "")).upper() or "退" in str(row.get("name", "")):
        reasons.append("risk_warning_name")
    if i.get("estimated_turnover_20d_median", 0) < c.get("minimum_estimated_turnover_20d_median_cny", 5e7):
        reasons.append("low_liquidity_proxy")
    if ((row.get("source") or {}).get("corporate_action_basis_change")
            or "corporate_action_price_basis_review_required" in row.get("ranking", {}).get("reasons", [])):
        reasons.append("corporate_action_basis_conflict")
    if intraday:
        reasons += quote_errors(quote, row["code"], dates, now, c)
        if quote and abs(quote.get("prev_close", 0) - i.get("price", 0)) > .011:
            reasons.append("quote_previous_close_basis_conflict")
    points = None
    if not reasons:
        points = project(state, quote) if intraday else state["points"]
        if intraday and quote["date"] <= state["asof"]:
            reasons.append("provisional_session_not_after_completed_baseline")
    if reasons:
        return {"code": row["code"], "name": row.get("name"), "structure_eligible": False,
                "rejection_reasons": sorted(set(reasons)), "setups": [], "stage": "unavailable", "evidence_gaps": gaps}
    setups, stage, distance = classify(points, c)
    p = points[-1]
    if p["volume"] <= 0 or p["high"] == p["low"]:
        reasons.append("no_volume_or_one_price_bar")
    if not setups:
        reasons.append("no_early_setup")
    price_asof = (quote["date"] + "T" + quote["time"] + "+08:00") if intraday else p["day"] + "T15:00:00+08:00"
    if intraday:
        gaps += ["unfinished_daily_band_requires_close_confirmation", "completed_5_15_minute_confirmation_unavailable",
                 "same_time_volume_reference_required"]
    if stage == "preparing":
        gaps.append("squeeze_direction_not_confirmed")
    from .vcp import VERSION as VCP_VERSION, observe
    if intraday and state.get("vcp_next_session", {}).get("version") == VCP_VERSION:
        vcp = observe(state["vcp_next_session"], {**quote, "day": quote["date"]}, completed=False)
    else:
        vcp = state.get("vcp_completed", {"version": VCP_VERSION, "available": False,
                    "matched": False, "stage": "unavailable", "reason": "completed_vcp_state_not_hydrated"})
    return {"code": row["code"], "name": row.get("name"), "industry": row.get("industry"),
            "daily_asof": dates["market_date"], "price_asof": price_asof,
            "band_status": "provisional" if intraday else "completed", "price": p["close"],
            "stage": stage, "setups": setups, "structure_eligible": not reasons, "vcp_shadow": vcp,
            "rejection_reasons": reasons, "entry_status": "observation_wait_direction" if stage == "preparing" else "confirmation_and_diligence_required",
            "entry_qualified": False, "evidence_gaps": gaps,
            "boll": {k: p[k] for k in ("mid", "upper", "lower", "width")},
            "features": {"atr20": p["atr20"], "distance_to_mid_atr": distance,
                         "distance_to_mid_pct": (p["close"] / p["mid"] - 1) * 100,
                         "bandwidth_percentile_120": p["width_percentile"],
                         "mid_slope_5d_atr": p["mid_slope_5d_atr"],
                         "return_5d_pct": p["return_5d_pct"], "return_20d_pct": p["return_20d_pct"],
                         "volume_vs_previous20_median": p["volume_ratio_complete"],
                         "alpha101_101": (p["close"] - p["open"]) / (p["high"] - p["low"] + .001)},
            "conditional_prices": {"mid_turns_up_if_close_above": p["mid_turn_up_close_threshold"],
                "mid_reclaim_close_threshold": statistics.mean(state["closes"][-19:]) if intraday else None,
                "structural_reference_low": p["support_low_5d"],
                "meaning": "algebraic_close_scenarios_not_a_price_forecast"},
            "baseline_v1_eligible": bool(row.get("ranking", {}).get("eligible")),
            "baseline_v1_score": row.get("ranking", {}).get("score")}


def build(records, dates, now, config=None, quotes=None):
    c = {**DEFAULTS, **(config or {})}
    codes = [r["code"] for r in records]
    if len(codes) != len(set(codes)):
        raise ValueError("duplicate_early_universe_code")
    rows = [evaluate(r, dates, now, c, (quotes or {}).get(r["code"])) for r in records]
    medians = {h: statistics.median([r["features"][f"return_{h}d_pct"] for r in rows if "features" in r])
               for h in (5, 20) if any("features" in r for r in rows)}
    for r in rows:
        if "features" in r:
            for h in (5, 20):
                r["features"][f"relative_market_{h}d_pct"] = r["features"][f"return_{h}d_pct"] - medians[h]
            r["features"]["signal_age_sessions"] = min((s["signal_age_sessions"] for s in r["setups"]), default=None)
    def key(r):
        ages = [s["signal_age_sessions"] for s in r["setups"]]
        f = r["features"]
        return (min(ages), abs(f["distance_to_mid_atr"]),
                -(f.get("relative_market_5d_pct") or 0), r["code"])
    pools = {p: sorted([r for r in rows if r["structure_eligible"] and any(s["pool"] == p for s in r["setups"])], key=key)[:c["pool_limit"]] for p in POOLS}
    # Round-robin protects near-mid and pre-squeeze opportunities from momentum dominance.
    shortlist, seen = [], set()
    for n in range(c["pool_limit"]):
        for p in POOLS:
            if len(pools[p]) > n:
                r = pools[p][n]
                if r["code"] not in seen and len(shortlist) < c["shortlist_limit"]:
                    shortlist.append(r); seen.add(r["code"])
    # VCP is an independent shadow watchlist, including stocks outside BOLL's four pools.
    vcp_rows = [r for r in rows if r.get("vcp_shadow", {}).get("matched")
                and set(r["rejection_reasons"]) <= {"no_early_setup"}
                and r["vcp_shadow"]["stage"] in {"preparing", "near_pivot", "breakout_provisional",
                    "breakout_close_volume_confirmed", "breakout_volume_unconfirmed"}]
    vcp_rows.sort(key=lambda r: (abs(r["vcp_shadow"].get("distance_to_pivot_atr") or 0), r["code"]))
    return {"schema_version": "1.0", "method_version": VERSION,
            "mode": "active_research_discovery_unvalidated_ranking", "model_status": "not_trained",
            "probabilities_enabled": False, "production_prediction_activation": False,
            "report_date": dates["report_date"], "market_date": dates["market_date"], "phase": dates["phase"],
            "published_at": now.isoformat(), "evaluated_count": len(rows),
            "feature_available_count": sum("features" in r for r in rows),
            "pool_counts": {p: len(v) for p, v in pools.items()}, "shortlist": shortlist,
            "pool_codes": {p: [r["code"] for r in v] for p, v in pools.items()},
            "entry_qualified_count": 0,
            "vcp_shadow": {"mode": "observation_only_no_ranking_weight", "eligible_count": len(vcp_rows),
                "feature_available_count": sum(r.get("vcp_shadow", {}).get("available", False) for r in rows),
                "watchlist": [{k: r[k] for k in ("code", "name", "price_asof", "vcp_shadow")} for r in vcp_rows[:10]],
                "probabilities_enabled": False, "entry_qualified": False},
            "ranking_meaning": "age_then_entry_distance_within_setup_round_robin_not_expected_return",
            "market_reference": "same_available_cohort_median_proxy_not_official_index",
            "parameter_status": "preregistered_hypotheses_not_empirical_optimum",
            "valid_sessions": c["valid_sessions"],
            "stage_counts": dict(Counter(r["stage"] for r in rows)),
            "rejection_counts": dict(Counter(x for r in rows for x in r["rejection_reasons"])),
            "evaluations": rows}


def write_early(root, directory, records, dates, config, quotes, published_at):
    from .history import write_json
    from .early_runtime import hydrate_states
    hydration = hydrate_states(root, records, dates["market_date"])
    policy = root / "config/early_signals.json"
    settings = json.loads(policy.read_text()) if policy.exists() else {}
    data = build(records, dates, datetime.fromisoformat(published_at), {**config, **settings}, quotes)
    rows = data.pop("evaluations")
    data["feature_hydration"] = hydration
    refs = []
    for offset in range(0, len(rows), 100):
        part = rows[offset:offset + 100]
        path = directory / "early_records" / (part[0]["code"] + "-" + part[-1]["code"] + ".json")
        write_json(path, {"method_version": VERSION, "records": part})
        refs.append({"file": path.relative_to(root).as_posix(), "count": len(part),
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    data["record_shards"] = refs
    path = directory / "early_queue.json"
    write_json(path, data)
    return {"reader_file": path.relative_to(root).as_posix(), "reader_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "method_version": VERSION, "mode": data["mode"], "feature_available_count": data["feature_available_count"],
            "evaluated_count": len(rows), "pool_counts": data["pool_counts"], "model_status": "not_trained"}
