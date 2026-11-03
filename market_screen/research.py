"""Versioned shadow features and three setup queues; never trade probabilities."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics

VERSION = "boll_context_atr_v2"
POOLS = ("squeeze_breakout", "trend_pullback", "trend_repair")


def percentile(value, reference):
    if not reference:
        return None
    return (sum(x < value for x in reference) + .5 * sum(x == value for x in reference)) / len(reference)


def completed_features(bars, series):
    latest = series[-1]
    if len(bars) < 25 or "mid" not in latest:
        return {"version": VERSION, "available": False}
    closes = [r["close"] for r in bars]
    true_ranges = [max(bars[i]["high"] - bars[i]["low"],
                       abs(bars[i]["high"] - closes[i - 1]), abs(bars[i]["low"] - closes[i - 1]))
                   for i in range(max(1, len(bars) - 20), len(bars))]
    atr = statistics.mean(true_ranges)
    previous = series[-2]
    widths = [r["width"] for r in series[:-1] if "width" in r][-120:]
    # Each recent observation is compared only with widths known before it.
    recent_quantiles = []
    for i in range(max(20, len(series) - 6), len(series) - 1):
        reference = [r["width"] for r in series[max(0, i - 120):i] if "width" in r]
        if len(reference) >= 60:
            recent_quantiles.append(percentile(series[i]["width"], reference))
    prior_high = max(r["high"] for r in bars[-21:-1])
    support = min(r["low"] for r in bars[-5:])
    span = latest["upper"] - latest["lower"]
    return {"version": VERSION, "available": True, "asof": bars[-1]["day"],
            "price_basis": "unadjusted_requires_corporate_action_review",
            "atr20": atr, "atr_method": "simple_mean_20_true_ranges", "atr_pct": atr / closes[-1] * 100,
            "bandwidth_percentile_120": percentile(latest["width"], widths) if len(widths) >= 120 else None,
            "bandwidth_reference_count": len(widths),
            "recent_squeeze_120": any(p <= .25 for p in recent_quantiles),
            "mid_slope_5d_atr": (latest["mid"] - series[-6]["mid"]) / atr if atr else None,
            "distance_to_mid_atr": (closes[-1] - latest["mid"]) / atr if atr else None,
            "band_position": (closes[-1] - latest["lower"]) / span if span else .5,
            "prior20_high": prior_high, "support_low_5d": support,
            "breakout_prior20": closes[-1] > prior_high,
            "reclaimed_mid": closes[-2] < previous["mid"] and closes[-1] >= latest["mid"],
            "pullback_reclaimed": bool(atr and latest["mid"] > previous["mid"]
                and abs(bars[-1]["low"] - latest["mid"]) <= .75 * atr
                and closes[-1] >= latest["mid"] and closes[-1] > closes[-2]),
            "return_5d_pct": (closes[-1] / closes[-6] - 1) * 100,
            "return_20d_pct": (closes[-1] / closes[-21] - 1) * 100,
            "macd_hist_atr": latest["hist2"] / atr if atr else None,
            "two_close_mid_failure": closes[-1] < latest["mid"] and closes[-2] < previous["mid"]}


def context_for(records, quote_returns=None):
    values, industries = defaultdict(list), defaultdict(lambda: defaultdict(list))
    for row in records:
        f = row.get("indicators", {}).get("research_features", {})
        if row.get("status") != "screened" or not f.get("available"):
            continue
        for key in ("return_5d_pct", "return_20d_pct"):
            if f.get(key) is not None:
                values[key].append(f[key])
                if row.get("industry"):
                    industries[row["industry"]][key].append(f[key])
    medians = {k: statistics.median(v) for k, v in values.items() if v}
    groups = {industry: {k: statistics.median(v) for k, v in metrics.items() if len(v) >= 3}
              for industry, metrics in industries.items()}
    above = [r["indicators"]["price"] >= r["indicators"]["boll"]["mid"] for r in records
             if r.get("status") == "screened" and r.get("indicators", {}).get("boll")]
    breadth = sum(above) / len(above) if above else None
    r20 = medians.get("return_20d_pct")
    regime = ("up" if r20 is not None and r20 > 0 and breadth is not None and breadth >= .6 else
              "down" if r20 is not None and r20 < 0 and breadth is not None and breadth <= .4 else "mixed")
    noon = list((quote_returns or {}).values())
    return {"market_medians": medians, "industry_medians": groups,
            "market_reference": "median_of_feature_available_screened_stocks_proxy_not_official_index",
            "feature_cohort_count": len(values.get("return_5d_pct", [])), "breadth_count": len(above),
            "fraction_above_mid": breadth, "regime": regime,
            "regime_status": "research_label_no_production_filter",
            "noon_return_median_pct": statistics.median(noon) if noon else None,
            "noon_return_count": len(noon)}


def evaluate_record(row, context, config, quote=None, phase="close", noon_baseline=None):
    indicators = row.get("indicators", {})
    f = indicators.get("research_features", {})
    rejected, gaps, setups = [], [], []
    if row.get("status") != "screened":
        rejected += row.get("reasons") or ["daily_record_not_screened"]
    if not f.get("available"):
        gaps.append("v2_completed_features_unavailable")
    if (row.get("source") or {}).get("corporate_action_basis_change") or "corporate_action_price_basis_review_required" in row.get("ranking", {}).get("reasons", []):
        rejected.append("corporate_action_price_basis_review_required")
    if indicators.get("bar_count", 0) < config.get("minimum_history_bars", 160) or not indicators.get("history_current"):
        rejected.append("completed_history_not_eligible")
    if indicators.get("estimated_turnover_20d_median", 0) < config.get("minimum_estimated_turnover_20d_median_cny", 5e7):
        rejected.append("low_liquidity_proxy")
    last = indicators.get("last_bar", {})
    if last.get("volume", 0) <= 0 or last.get("high") == last.get("low"):
        rejected.append("no_activity_or_one_price_bar")
    if "ST" in str(row.get("name", "")).upper() or "退" in str(row.get("name", "")):
        rejected.append("risk_warning_name")
    price = indicators.get("price")
    noon_change = noon_rs = volume_ratio = None
    if phase == "noon":
        if not quote:
            rejected.append("no_valid_noon_quote")
        else:
            price = quote["close"]
            if abs(quote["prev_close"] - indicators.get("price", quote["prev_close"])) > .011:
                rejected.append("noon_price_basis_conflict")
            noon_change = (price / quote["prev_close"] - 1) * 100
            median = context.get("noon_return_median_pct")
            noon_rs = noon_change - median if median is not None else None
            if noon_baseline and noon_baseline.get("volume", 0) > 0:
                volume_ratio = quote["volume"] / noon_baseline["volume"]
            else:
                gaps.append("previous_full_morning_volume_unavailable")
    relative = {}
    for h in (5, 20):
        key = f"return_{h}d_pct"
        base = context["market_medians"].get(key)
        relative[f"market_{h}d_pct"] = f[key] - base if base is not None and f.get(key) is not None else None
        group = context["industry_medians"].get(row.get("industry"), {}).get(key)
        relative[f"industry_{h}d_pct"] = f[key] - group if group is not None and f.get(key) is not None else None
    if relative.get("industry_5d_pct") is None:
        gaps.append("dated_industry_reference_unavailable")
    if row.get("industry"):
        gaps.append("exchange_industry_category_may_be_coarse_not_subsector")
    gaps.append("corporate_action_window_requires_source_review")
    if f.get("available"):
        if f.get("recent_squeeze_120") and indicators.get("opening_up") and (f.get("breakout_prior20") or f.get("band_position", 0) >= .85):
            setups.append("squeeze_breakout")
        if f.get("pullback_reclaimed") and (f.get("mid_slope_5d_atr") or 0) > 0:
            setups.append("trend_pullback")
        if f.get("reclaimed_mid"):
            setups.append("trend_repair")
    if phase == "noon" and price is not None and indicators.get("boll"):
        if price < indicators["boll"]["mid"]:
            rejected.append("noon_price_below_completed_mid")
        if (price / indicators["boll"]["upper"] - 1) * 100 > config.get("maximum_extension_above_upper_pct", 3):
            rejected.append("noon_extension_above_completed_upper")
    elif indicators.get("distance_to_upper_pct", 0) > config.get("maximum_extension_above_upper_pct", 3):
        rejected.append("extension_above_upper")
    if not setups:
        rejected.append("no_v2_setup")
    return {"code": row["code"], "name": row.get("name"), "industry": row.get("industry"),
            "daily_asof": row.get("market_date"), "setups": setups, "features": f,
            "relative_strength": relative, "context": {"regime": context["regime"], "reference": context["market_reference"]},
            "structure_eligible": not rejected, "rejection_reasons": sorted(set(rejected)),
            "entry_status": "review_required" if not rejected else "ineligible",
            "evidence_gaps": sorted(set(gaps)), "baseline_v1_eligible": bool(row.get("ranking", {}).get("eligible")),
            "baseline_v1_score": row.get("ranking", {}).get("score"), "price": price,
            "noon_return_pct": noon_change, "noon_relative_market_pct": noon_rs,
            "volume_vs_previous_full_morning": volume_ratio,
            "ranking_meaning": "lexicographic_shadow_research_priority_not_expected_return_or_probability"}


def build_shadow(records, dates, config, quotes=None, noon_baselines=None):
    context = context_for(records, {code: (q["close"] / q["prev_close"] - 1) * 100 for code, q in (quotes or {}).items()})
    evaluated = [evaluate_record(r, context, config, (quotes or {}).get(r["code"]), dates["phase"],
                                (noon_baselines or {}).get(r["code"])) for r in records]
    def key(r):
        rs = r["relative_strength"]["market_5d_pct"]
        noon = r.get("noon_relative_market_pct")
        slope = r["features"].get("mid_slope_5d_atr")
        distance = r["features"].get("distance_to_mid_atr")
        return (-(noon if noon is not None else 0), -(rs if rs is not None else -1e9),
                -(slope if slope is not None else -1e9), abs(distance or 0), r["code"])
    pools = {name: sorted((r for r in evaluated if r["structure_eligible"] and name in r["setups"]), key=key)[:config.get("pool_limit", 20)] for name in POOLS}
    unique = {r["code"]: r for pool in pools.values() for r in pool}
    shortlist = sorted(unique.values(), key=key)[:config.get("shortlist_limit", 15)]
    return {"schema_version": "1.0", "experiment_id": "boll_multisetup_v2_20261103", "mode": "shadow",
            "production_strategy": "boll_v1", "feature_version": VERSION, "report_date": dates["report_date"],
            "market_date": dates["market_date"], "phase": dates["phase"], "evaluated_count": len(evaluated),
            "feature_available_count": sum(r.get("status") == "screened" and r.get("indicators", {}).get("research_features", {}).get("available", False) for r in records),
            "feature_computed_including_exclusions_count": sum(r["features"].get("available", False) for r in evaluated),
            "structure_eligible_count": sum(r["structure_eligible"] for r in evaluated),
            "pool_counts": {k: len(v) for k, v in pools.items()}, "deduplicated_candidate_count": len(unique),
            "context": context, "pools": pools, "shortlist": shortlist,
            "entry_qualified_count": 0, "entry_qualification_note": "Company/event/price-structure review is required; no automatic buy signal.",
            "activation_status": "blocked_pending_historical_out_of_sample_and_20_session_shadow_review",
            "gap_counts": dict(Counter(g for r in evaluated for g in r["evidence_gaps"])),
            "evaluations": evaluated}


def write_shadow(root, directory, records, dates, config, quotes=None, published_at=None):
    from .history import write_json
    from .quotes import validate_quote
    from datetime import datetime
    moment = datetime.fromisoformat(published_at) if published_at else None
    valid = {code: q for code, q in (quotes or {}).items()
             if dates["phase"] == "noon" and validate_quote(q, dates["report_date"], "noon", now=moment) == []}
    baseline_path = root / "output/research/noon" / (dates["market_date"] + ".json")
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    if baseline and (baseline.get("market_date") != dates["market_date"] or baseline.get("cutoff") != "11:30"):
        raise ValueError("invalid_previous_morning_reference")
    settings = root / "config/research_v2.json"
    policy = json.loads(settings.read_text()) if settings.exists() else {}
    data = build_shadow(records, dates, {**config, **policy}, valid, baseline.get("quotes", {}))
    evaluations = data.pop("evaluations")
    refs = []
    for offset in range(0, len(evaluations), 100):
        part = evaluations[offset:offset + 100]
        path = directory / "research_records" / (part[0]["code"] + "-" + part[-1]["code"] + ".json")
        write_json(path, {"feature_version": VERSION, "records": part})
        refs.append({"file": path.relative_to(root).as_posix(), "count": len(part), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    data.update(published_at=published_at, record_shards=refs)
    path = directory / "research_shadow.json"
    write_json(path, data)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    # Reports read this compact, nonduplicated queue. The evaluator alone needs
    # full pool rows and all record shards.
    reader = {k: data[k] for k in ("schema_version", "experiment_id", "mode", "production_strategy", "feature_version",
        "report_date", "market_date", "phase", "published_at", "evaluated_count", "feature_available_count",
        "pool_counts", "deduplicated_candidate_count", "entry_qualified_count", "activation_status")}
    reader["full_result"] = {"file": path.relative_to(root).as_posix(), "sha256": digest}
    reader["pool_codes"] = {pool: [r["code"] for r in rows] for pool, rows in data["pools"].items()}
    reader["context"] = {k: v for k, v in data["context"].items() if k != "industry_medians"}
    reader["shortlist"] = [{"code": r["code"], "name": r["name"], "setups": r["setups"], "price": r["price"],
        "daily_asof": r["daily_asof"], "structure_eligible": r["structure_eligible"], "entry_status": r["entry_status"],
        "atr20": r["features"].get("atr20"), "bandwidth_percentile_120": r["features"].get("bandwidth_percentile_120"),
        "mid_slope_5d_atr": r["features"].get("mid_slope_5d_atr"), "relative_strength": r["relative_strength"],
        "noon_relative_market_pct": r["noon_relative_market_pct"], "volume_vs_previous_full_morning": r["volume_vs_previous_full_morning"],
        "evidence_gaps": r["evidence_gaps"], "baseline_v1_score": r["baseline_v1_score"]} for r in data["shortlist"]]
    reader_path = directory / "research_queue.json"
    write_json(reader_path, reader)
    return {"selected_file": path.relative_to(root).as_posix(), "sha256": digest,
            "reader_file": reader_path.relative_to(root).as_posix(), "reader_sha256": hashlib.sha256(reader_path.read_bytes()).hexdigest(),
            "mode": "shadow", "feature_version": VERSION, "evaluated_count": data["evaluated_count"],
            "feature_available_count": data["feature_available_count"], "pool_counts": data["pool_counts"],
            "entry_qualified_count": 0, "activation_status": data["activation_status"]}
