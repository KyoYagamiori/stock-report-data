"""Causal daily pilot samples. Never asserts official execution or publication evidence."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import math
import statistics

from market_screen.early import classify
from market_screen.research import percentile
from market_screen.technicals import calculate, rank_candidate
from .history_source import TZ, canonical, digest, read_capture

REMAINING_GAPS = ["full_historical_universe_not_collected", "provider_index_needs_independent_official_tieout",
    "official_dated_limit_and_order_fill_tape_not_supplied", "corporate_action_chain_requires_event_tieout",
    "historical_signal_times_are_simulated_not_published", "live_feature_basis_and_market_reference_parity_pending",
    "censored_outcomes_prevent_full_strategy_performance_claim", "risk_execution_and_forward_review_pending"]


def normalize(rows, index=False, allow_unknown_status=False):
    result, seen = [], set()
    for source in rows:
        day = source["date"]
        datetime.fromisoformat(day)
        if day in seen:
            raise ValueError("duplicate_history_date:" + day)
        seen.add(day)
        row = {"day": day, "code": source["code"]}
        for key in ("open", "high", "low", "close", "volume", "amount"):
            value = float(source[key])
            if not math.isfinite(value) or value < 0 or (key == "close" and value == 0):
                raise ValueError("invalid_history_" + key)
            row[key] = value
        if not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
            raise ValueError("invalid_history_ohlc")
        if not index:
            st_values = {"0", "1", "unknown"} if allow_unknown_status else {"0", "1"}
            if source.get("adjustflag") != "3" or source.get("tradestatus") not in {"0", "1"} or source.get("isST") not in st_values:
                raise ValueError("unadjusted_status_and_st_fields_required")
            row.update(preclose=float(source["preclose"]), tradestatus=source["tradestatus"], isST=source["isST"])
            if not math.isfinite(row["preclose"]) or row["preclose"] <= 0:
                raise ValueError("invalid_history_preclose")
        result.append(row)
    return sorted(result, key=lambda r: r["day"])


def causal_adjust(rows):
    """Only the current and preceding preclose reset can affect today's factors."""
    result, factor = [], 1.0
    for i, row in enumerate(rows):
        if i:
            factor *= rows[i - 1]["close"] / row["preclose"]
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError("invalid_causal_corporate_action_chain")
        item = {**row, "factor": factor, "raw": row}
        for key in ("open", "high", "low", "close"):
            item[key] *= factor
        item["volume"] /= factor
        result.append(item)
    return result


def points_for(rows):
    closes, points, widths, ranges = [], [], [], []
    contraction = None
    for i, b in enumerate(rows):
        closes.append(b["close"])
        if i:
            ranges.append(max(b["high"] - b["low"], abs(b["high"] - closes[i - 1]), abs(b["low"] - closes[i - 1])))
        if i < 19:
            widths.append(None)
            points.append(None)
            continue
        mid, sigma = statistics.mean(closes[-20:]), statistics.pstdev(closes[-20:])
        width = 4 * sigma / mid
        previous = widths[-1] if widths[-1] is not None else width
        contraction = (contraction or rows[i - 1]["day"]) if width < previous else None
        reference = [v for v in widths[-120:] if v is not None]
        widths.append(width)
        atr = statistics.mean(ranges[-20:])
        points.append({**{k: b[k] for k in ("day", "open", "high", "low", "close", "volume")},
            "mid": mid, "upper": mid + 2 * sigma, "lower": mid - 2 * sigma, "width": width,
            "width_percentile": percentile(width, reference) if len(reference) == 120 else None,
            "atr20": atr, "contraction_origin": contraction,
            "mid_slope_5d_atr": (mid - points[i - 5]["mid"]) / atr if i >= 24 and atr else None,
            "return_5d_pct": (closes[i] / closes[i - 5] - 1) * 100,
            "return_20d_pct": (closes[i] / closes[i - 20] - 1) * 100 if i >= 20 else None,
            "volume_ratio_complete": b["volume"] / statistics.median(r["volume"] for r in rows[i - 20:i])
                if i >= 20 and statistics.median(r["volume"] for r in rows[i - 20:i]) > 0 else None})
    return points


def entry_rejection(bar, allow_unknown_status=False):
    if bar is None:
        return "missing_next_session_bar"
    if bar["tradestatus"] != "1" or bar["volume"] <= 0:
        return "halt_or_no_volume"
    if bar["isST"] != "0" and not (allow_unknown_status and bar["isST"] == "unknown"):
        return "risk_warning_at_entry"
    if bar["high"] == bar["low"]:
        return "one_price_bar"
    # Conservative main-board proxy, deliberately not an official price-limit audit.
    if not .905 < bar["open"] / bar["preclose"] < 1.095:
        return "open_near_limit_or_exceptional_session"
    return None


def labels(day, raw_by_day, adjusted_by_day, calendar, benchmark, cost_bps, allow_unknown_status=False):
    t = calendar.index(day)
    if t + 6 >= len(calendar):
        return None, {"state": "immature_horizon", "signal_date": day}
    entry_day, exit_days = calendar[t + 1], {h: calendar[t + 1 + h] for h in (1, 3, 5)}
    entry = raw_by_day.get(entry_day)
    rejection = entry_rejection(entry, allow_unknown_status)
    evidence = {"signal_date": day, "entry_date": entry_day, "scheduled_exit_dates": exit_days,
                "entry_rule": "next_session_open_no_wait", "limit_basis": "conservative_9.5pct_mainboard_proxy",
                "raw_entry_bar": entry, "round_trip_cost_bps_assumption": cost_bps}
    if allow_unknown_status:
        evidence["status_basis"] = "st_status_unknown_price_only_research_not_verified_execution"
    if rejection:
        return {h: 0.0 for h in exit_days}, {**evidence, "state": "unfilled_cash_zero", "reason": rejection,
                "label_end_date": exit_days[5]}
    values, exits = {}, {}
    for h, exit_day in exit_days.items():
        exit_bar = raw_by_day.get(exit_day)
        if (exit_bar is None or exit_bar["tradestatus"] != "1" or exit_bar["volume"] <= 0
                or exit_bar["close"] / exit_bar["preclose"] <= .905):
            return None, {**evidence, "state": "censored_exit", "reason": "missing_halted_or_near_limit_exit", "horizon": h}
        if entry_day not in benchmark or exit_day not in benchmark:
            return None, {**evidence, "state": "censored_exit", "reason": "benchmark_date_missing"}
        a, z = adjusted_by_day[entry_day], adjusted_by_day[exit_day]
        total = z["close"] / a["open"] - 1
        index_return = benchmark[exit_day]["close"] / benchmark[entry_day]["open"] - 1
        values[h] = (total - index_return) * 100 - cost_bps / 100
        exits[h] = {"raw_exit_bar": exit_bar, "entry_factor": a["factor"], "exit_factor": z["factor"],
                    "gross_stock_return_pct": total * 100, "benchmark_return_pct": index_return * 100}
    return values, {**evidence, "state": "filled_daily_proxy", "exits": exits, "label_end_date": exit_days[5]}


def build(root, manifest):
    config = manifest["config"]
    origin, end = config["cohort_date"], config["history_end"]
    price_only = manifest.get("status_basis") == "unavailable_st_price_only_research"
    if price_only and manifest.get("provider") != "qlib_public_release":
        raise ValueError("price_only_scope_requires_explicit_qlib_release_provenance")
    membership = read_capture(root, manifest["membership"])
    if membership["request"] != {"method": "query_all_stock", "kwargs": {"day": origin}}:
        raise ValueError("historical_membership_request_date_mismatch")
    from .history_source import select_cohort
    if select_cohort(membership["rows"], config["sample_size"], config["seed"]) != manifest["selected_codes"]:
        raise ValueError("historical_cohort_was_changed")
    calendar_payload = read_capture(root, manifest["calendar"])
    calendar = [r["calendar_date"] for r in calendar_payload["rows"] if r["is_trading_day"] == "1"]
    if calendar != sorted(set(calendar)) or not calendar or calendar[-1] != end or origin not in calendar:
        raise ValueError("historical_calendar_range_or_uniqueness_invalid")
    benchmark_rows = normalize(read_capture(root, manifest["benchmark"])["rows"], index=True)
    benchmark = {r["day"]: r for r in benchmark_rows}
    if benchmark_rows[-1]["day"] != end or any(r["code"] != config["benchmark_code"] for r in benchmark_rows):
        raise ValueError("historical_benchmark_identity_invalid")
    samples, audits, excluded, errors = [], [], Counter(), dict(manifest["source_failures"])
    signal_dates, seen = set(), set()
    for code in manifest["selected_codes"]:
        if code not in manifest["stocks"]:
            continue
        try:
            source = read_capture(root, manifest["stocks"][code])
            expected = {"code": code, "start_date": config["history_start"], "end_date": end, "frequency": "d", "adjustflag": "3"}
            if source["request"]["method"] != "query_history_k_data_plus" or any(source["request"]["kwargs"].get(k) != v for k, v in expected.items()):
                raise ValueError("stock_history_request_identity_invalid")
            raw = normalize(source["rows"], allow_unknown_status=price_only)
            if any(r["code"] != code or not config["history_start"] <= r["day"] <= end for r in raw):
                raise ValueError("stock_history_identity_or_range_invalid")
            observed = {r["day"] for r in raw}
            expected_dates = {d for d in calendar if raw[0]["day"] <= d <= raw[-1]["day"]}
            if observed - expected_dates or (observed != expected_dates and not price_only):
                raise ValueError("stock_history_has_missing_or_off_calendar_sessions")
            adjusted = causal_adjust(raw)
            points = points_for(adjusted)
            raw_map, adjusted_map = {r["day"]: r for r in raw}, {r["day"]: r for r in adjusted}
            for i in range(159, len(raw)):
                day, bar, point = raw[i]["day"], raw[i], points[i]
                if day < origin or bar["tradestatus"] != "1" or bar["isST"] not in ({"0", "unknown"} if price_only else {"0"}) or bar["volume"] <= 0 or bar["high"] == bar["low"]:
                    continue
                if statistics.median(r["amount"] for r in raw[i - 19:i + 1]) < config["minimum_turnover_cny"]:
                    continue
                setups, stage, distance = classify(points[max(24, i - 15):i + 1])
                fresh = [s for s in setups if (code, s["pool"], s["origin"]) not in seen]
                if not fresh:
                    continue
                # One dated stock sample; deterministic first pool resolves overlaps.
                setup = fresh[0]
                for s in setups:
                    seen.add((code, s["pool"], s["origin"]))
                signal_dates.add(day)
                target, audit = labels(day, raw_map, adjusted_map, calendar, benchmark, config["round_trip_cost_bps"], price_only)
                audit.update(code=code, setup=setup["pool"], origin=setup["origin"])
                audit_hash = digest(canonical(audit))
                audits.append({"sha256": audit_hash, "evidence": audit})
                if target is None:
                    excluded[audit["state"]] += 1
                    continue
                features = {"mid_slope_5d_atr": point["mid_slope_5d_atr"], "distance_to_mid_atr": distance,
                    "bandwidth_percentile_120": point["width_percentile"], "return_5d_pct": point["return_5d_pct"],
                    "return_20d_pct": point["return_20d_pct"], "volume_vs_previous20_median": point["volume_ratio_complete"],
                    "signal_age_sessions": setup["signal_age_sessions"],
                    "alpha101_101": (point["close"] - point["open"]) / (point["high"] - point["low"] + .001)}
                bi = next((j for j, r in enumerate(benchmark_rows) if r["day"] == day), -1)
                if bi < 20 or any(features[k] is None for k in features):
                    excluded["feature_or_benchmark_warmup"] += 1
                    continue
                for h in (5, 20):
                    features[f"relative_market_{h}d_pct"] = features[f"return_{h}d_pct"] - (benchmark_rows[bi]["close"] / benchmark_rows[bi - h]["close"] - 1) * 100
                # Calculate only early candidates, using the same 160-bar v1 implementation.
                indicators = calculate(adjusted[i - 159:i + 1], day)
                baseline = rank_candidate({"name": code}, indicators, {"minimum_history_bars": 160,
                    "maximum_extension_above_upper_pct": 3, "minimum_estimated_turnover_20d_median_cny": 5e7})
                samples.append({"date": day, "code": code.split(".")[1], "setup": setup["pool"], "stage": stage,
                    "features": features, "target_t3_net_excess_pct": target[3],
                    "secondary_net_excess_pct": {str(h): v for h, v in target.items()},
                    "signal_available_at": day + "T16:00:00+08:00", "features_known_at": day + "T15:30:00+08:00",
                    "label_end_date": audit["label_end_date"], "label_known_at": audit["label_end_date"] + "T16:00:00+08:00",
                    "source_sha256": manifest["stocks"][code]["sha256"], "execution_audit_sha256": audit_hash,
                    "execution_state": audit["state"], "round_trip_cost_bps_assumption": config["round_trip_cost_bps"],
                    "baseline_v1_eligible": baseline["eligible"], "baseline_v1_score": baseline["score"]})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            # Partial per-code samples must never survive a failed stock audit.
            samples = [r for r in samples if r["code"] != code.split(".")[1]]
            errors[code] = str(exc)[:250]
        print({"built_code": code, "samples_so_far": len(samples), "stock_errors": len(errors)}, flush=True)
    metadata = {"scope": "pilot", "asof": datetime.now(TZ).isoformat(),
        "universe_basis": "fixed_historical_origin_cohort", "benchmark_basis": "provider_index_not_independently_verified",
        "corporate_actions_basis": "causal_preclose_chain_raw_execution_retained", "primary_horizon_sessions": 3,
        "costs_in_target": True, "entry_policy": "simulated_next_session_open_no_wait",
        "execution_limits_basis": "conservative_daily_proxy_not_official_limit_tape",
        "decision_clock": "historical_simulation_assumption_not_actual_publication_time",
        "horizon_origin": "entry_day_zero_exit_h_trading_sessions_later", "unfilled_policy": "cash_zero_excess_exposure",
        "market_reference": "provider_csi300_index_not_live_cross_sectional_median",
        "config_sha256": manifest["config_sha256"], "remaining_gaps": REMAINING_GAPS}
    if price_only:
        metadata.update(execution_limits_basis="price_only_proxy_st_status_unknown",
                        st_status="not_supplied_never_assumed_normal", sparse_dates="unobserved_never_imputed",
                        source_provider="qlib_public_release", provenance=manifest.get("provenance"))
        metadata["remaining_gaps"] = REMAINING_GAPS + ["historical_st_status_not_supplied", "unobserved_price_dates_not_classified_as_verified_halts"]
    receipt = {"sample_size": len(manifest["selected_codes"]), "source_code_count": len(manifest["stocks"]),
        "source_failures": errors, "training_rows": len(samples), "feature_dates": len({r["date"] for r in samples}),
        "detected_signal_dates": len(signal_dates), "execution_counts": dict(Counter(a["evidence"]["state"] for a in audits)),
        "excluded_counts": dict(excluded), "remaining_gaps": metadata["remaining_gaps"], "full_market_complete": False,
        "label_scope": "hypothetical_price_returns_st_status_unknown" if price_only else "conservative_daily_execution_proxy"}
    return {"metadata": metadata, "rows": sorted(samples, key=lambda r: (r["date"], r["code"]))}, audits, receipt

