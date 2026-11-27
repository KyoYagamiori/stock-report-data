"""Use the repository's verified rolling bars for forward price-label feedback.

Daily OHLC proxies are deliberately not audited fills or portfolio returns.
Missing benchmarks and corporate-action evidence cannot be promoted by this module.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
import gzip
import hashlib
import json
import statistics

from market_screen.history import canonical_bytes, write_json
from market_screen.technicals import normalize_bars


def immutable(root, path, payload):
    raw = canonical_bytes(payload) + b"\n"
    if path.exists() and path.read_bytes() != raw:
        raise ValueError("refuse_to_replace_frozen_daily_model_evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"file": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}


def checked(root, reference, prefix):
    relative = reference.get("file", reference.get("selected_file", ""))
    path = (root / relative).resolve()
    if not path.is_relative_to(root / prefix):
        raise ValueError("daily_model_source_path_invalid:" + relative)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("daily_model_source_hash_mismatch:" + relative)
    return raw


def write_changed_latest(path, snapshot, timestamp, *, after=None):
    """Keep the original publication timestamp when the substantive receipt is unchanged."""
    try:
        previous = json.loads(path.read_bytes())
        before = {key: value for key, value in previous.items() if key != timestamp}
        incoming = {key: value for key, value in snapshot.items() if key != timestamp}
        if before == incoming:
            prior_time = datetime.fromisoformat(previous[timestamp])
            if ((after is None or prior_time > after)
                    and prior_time <= datetime.fromisoformat(snapshot[timestamp])):
                return previous
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    write_json(path, snapshot)
    return snapshot


def load_bars(root, needed, now):
    directory = root / "output/boll/bootstrap"
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if manifest.get("adjustment") != "unadjusted" or manifest["market_date"] > now.date().isoformat():
        raise ValueError("daily_model_own_history_basis_or_future_date")
    ref = {"file": "output/boll/bootstrap/history.jsonl.gz", "sha256": manifest["sha256"]}
    raw = checked(root, ref, "output/boll/bootstrap")
    histories, seen, starts, ends = {}, set(), [], []
    bar_count = 0
    for line in gzip.decompress(raw).splitlines():
        payload = json.loads(line)
        code = payload["code"]
        if code in seen or payload.get("adjustment") != "unadjusted":
            raise ValueError("daily_model_own_history_duplicate_or_basis")
        seen.add(code)
        if hashlib.sha256(canonical_bytes(payload["bars"])).hexdigest() != payload["history_sha256"]:
            raise ValueError("daily_model_own_history_bar_hash_mismatch:" + code)
        bars = normalize_bars(payload["bars"], manifest["market_date"])
        if not bars:
            raise ValueError("daily_model_own_history_empty:" + code)
        starts.append(bars[0]["day"])
        ends.append(bars[-1]["day"])
        bar_count += len(bars)
        if code in needed:
            histories[code] = {b["day"]: b for b in bars}
    if len(seen) != manifest["record_count"]:
        raise ValueError("daily_model_own_history_count_mismatch")
    return histories, {**ref, "market_date": manifest["market_date"], "codes": len(seen),
        "bars": bar_count, "earliest_bar": min(starts), "latest_bar": max(ends),
        "requested_codes": len(needed), "available_requested_codes": len(histories),
        "role": "live_features_and_forward_price_labels_not_multiyear_independent_training_history"}


def next_entry(calendar, now, lead_minutes):
    threshold = now + timedelta(minutes=lead_minutes)
    return next(d for d in calendar if datetime.fromisoformat(d + "T09:30:00+08:00") > threshold)


def price_outcome(ep, bars, calendar, horizon, now, cost_bps):
    entry_day = ep["entry_date"]
    index = calendar.index(entry_day)
    if index + horizon >= len(calendar):
        return {"state": "calendar_gap"}
    exit_day = calendar[index + horizon]
    if datetime.fromisoformat(exit_day + "T15:05:00+08:00") > now:
        return {"state": "pending", "scheduled_exit_date": exit_day}
    entry, exit_bar = bars.get(entry_day), bars.get(exit_day)
    if entry is None:
        return {"state": "unresolved_entry", "entry_date": entry_day}
    if exit_bar is None:
        return {"state": "unresolved_exit", "scheduled_exit_date": exit_day}
    sessions = calendar[index:index + horizon + 1]
    if any(d not in bars for d in sessions):
        return {"state": "unresolved_path_gap", "scheduled_exit_date": exit_day}
    if any(bars[d]["volume"] <= 0 for d in sessions):
        return {"state": "unresolved_no_volume", "scheduled_exit_date": exit_day}
    # These are price proxies; no unverifiable ST or official limit flags invented.
    prior_dates = [d for d in bars if d < entry_day]
    previous = bars[max(prior_dates)]["close"] if prior_dates else None
    if previous is None:
        return {"state": "unresolved_previous_close"}
    if entry["high"] == entry["low"] or not .905 < entry["open"] / previous < 1.095:
        return {"state": "unfilled_price_proxy", "price_net_return_pct": 0.0,
                "net_excess_pct": None, "entry_date": entry_day, "exit_date": exit_day}
    path = [bars[d] for d in sessions]
    if any(not .89 < b["open"] / a["close"] < 1.11 for a, b in zip(path, path[1:])):
        return {"state": "unresolved_action_or_exceptional_gap", "scheduled_exit_date": exit_day}
    previous_exit = bars[calendar[index + horizon - 1]]["close"]
    if exit_bar["high"] == exit_bar["low"] or exit_bar["close"] / previous_exit <= .905:
        return {"state": "unresolved_exit_limit_proxy", "scheduled_exit_date": exit_day}
    return {"state": "matured_price_proxy", "entry_date": entry_day, "exit_date": exit_day,
        "entry_price_proxy": entry["open"], "exit_price_proxy": exit_bar["close"],
        "price_net_return_pct": (exit_bar["close"] / entry["open"] - 1) * 100 - cost_bps / 100,
        "round_trip_cost_bps": cost_bps, "net_excess_pct": None,
        "benchmark_status": "not_supplied_no_excess_return_invented",
        "corporate_action_status": "unverified_raw_price_proxy",
        "execution_status": "daily_proxy_not_audited_ST_limits_or_real_fill"}


def settle(episodes, histories, calendar, now, config, history_ref):
    for ep in episodes.values():
        outcomes = ep.setdefault("outcomes", {})
        available = ep.get("public_available_by")
        entry_at = datetime.fromisoformat(ep["entry_date"] + "T09:30:00+08:00")
        if not available or datetime.fromisoformat(available) >= entry_at:
            for h in config["horizons_sessions"]:
                outcomes[str(h)] = {"state": "pending_public_availability_audit" if now < entry_at
                                   else "excluded_publication_not_verified_before_entry"}
            continue
        for h in config["horizons_sessions"]:
            key = str(h)
            if outcomes.get(key, {}).get("state") in {"matured_price_proxy", "unfilled_price_proxy"}:
                continue
            result = price_outcome(ep, histories.get(ep["code"], {}), calendar, h, now,
                                   config["round_trip_cost_bps"])
            if result["state"] in {"matured_price_proxy", "unfilled_price_proxy"}:
                result.update(label_recorded_at=now.isoformat(), source=history_ref)
            outcomes[key] = result


def feedback(episodes):
    rows = []
    for ep in episodes.values():
        if ep.get("outcomes", {}).get("3", {}).get("state") not in {"matured_price_proxy", "unfilled_price_proxy"}:
            continue
        rows.append({"signal_id": ep["signal_id"], "model_sha256": ep["model_sha256"],
            "date": ep["feature_date"], "code": ep["code"], "setup": ep["setup"],
            "features": ep["features"], "prediction_registered_at": ep["prediction_registered_at"],
            "outcomes": ep["outcomes"], "eligible_for_formal_training": False,
            "target_t3_net_excess_pct": None,
            "missing_for_retraining": ["same_benchmark_return", "corporate_action_and_execution_audit"],
            "scope": "prospective_own_library_feedback_not_qualified_excess_return_training"})
    return rows


def summarize(episodes):
    per_horizon = {}
    for h in (1, 3, 5):
        states = Counter(ep.get("outcomes", {}).get(str(h), {}).get("state", "pending") for ep in episodes.values())
        groups = {}
        for role in ("lightgbm", "ridge", "early_rule"):
            by_day = defaultdict(list)
            for ep in episodes.values():
                out = ep.get("outcomes", {}).get(str(h), {})
                if role in ep.get("selected_by", []) and out.get("price_net_return_pct") is not None:
                    by_day[ep["prediction_registered_at"][:10]].append(out["price_net_return_pct"])
            groups[role] = {"matured_signal_dates": len(by_day),
                "date_balanced_price_net_return_pct": statistics.mean(statistics.mean(v) for v in by_day.values()) if by_day else None}
        # A paired comparison requires every registered choice in both arms.
        paired = []
        cohorts = defaultdict(list)
        for ep in episodes.values():
            # Never pair one setup's new model winner with another setup's
            # new control when the other choices were already registered.
            cohorts[(ep["cohort_id"], ep["setup"])].append(ep)
        for cohort in cohorts.values():
            arms = {role: [e for e in cohort if role in e.get("selected_by", [])]
                    for role in ("lightgbm", "early_rule")}
            if not all(arms.values()):
                continue
            all_chosen = [e for arm in arms.values() for e in arm]
            if any(e.get("outcomes", {}).get(str(h), {}).get("price_net_return_pct") is None for e in all_chosen):
                continue
            means = {r: statistics.mean(e["outcomes"][str(h)]["price_net_return_pct"] for e in arm)
                     for r, arm in arms.items()}
            paired.append(means["lightgbm"] - means["early_rule"])
        per_horizon[str(h)] = {"states": dict(states), "groups": groups,
            "paired_complete_cohorts": len(paired),
            "paired_model_minus_rule_price_proxy_pct": statistics.mean(paired) if paired else None}
    return {"registered_unique_signals": len(episodes), "horizons": per_horizon,
        "measurement": "fixed_horizon_price_proxies_not_trade_win_rate_or_portfolio_pnl",
        "net_excess_return_available": False, "production_activation": False}
