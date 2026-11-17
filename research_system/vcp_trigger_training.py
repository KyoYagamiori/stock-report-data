"""Frozen VCP close-confirmation entry contracts, separate development candidates."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import gzip
import json
from pathlib import Path

from market_screen import vcp
from .daily_model import immutable
from .daily_model_data import checked
from .history_dataset import causal_adjust, entry_rejection, labels, normalize, points_for
from .history_source import TZ, canonical, digest, read_capture, write
from .vcp_training import FEATURES, STAGES, context, features_for, train


def trigger_labels(day, state, raw, adjusted, calendar, benchmark, config):
    """Use completed closes to confirm; never infer an intraday execution from high.

    A fixed-origin card either confirms inside its original window, expires,
    invalidates, or remains unresolved. Later prices never refresh that window.
    """
    if not state.get("matched") or not state.get("base_asof", "9999") < day:
        raise ValueError("trigger_requires_known_frozen_prior_session_base")
    start = calendar.index(day)
    window = calendar[start:start + config["waiting_sessions"]]
    pivot, atr, low = state["pivot"], state["atr20"], state["invalidation_below"]
    if not pivot > low > 0 or atr <= 0 or state["reference_volume"] <= 0:
        raise ValueError("trigger_invalid_frozen_structure")
    frozen = {k: state[k] for k in ("base_asof", "origin", "pivot", "invalidation_below", "atr20", "reference_volume")}
    audit = {"signal_date": day, "frozen_structure": frozen,
        "waiting_sessions": config["waiting_sessions"], "observed_window": window,
        "entry_policy": config["entry_policy"], "actual_trade": False}
    zero = {h: 0. for h in config["horizons_sessions"]}
    for index, observed_day in enumerate(window, start):
        bar, price = raw.get(observed_day), adjusted.get(observed_day)
        if bar is None or price is None or bar["tradestatus"] != "1" or bar["volume"] <= 0:
            return None, {**audit, "state": "unresolved_observation_data", "missing_date": observed_day}
        if price["close"] < low:
            return zero, {**audit, "state": "invalidated_before_entry", "label_end_date": observed_day}
        if price["close"] > pivot + config["maximum_extension_atr"] * atr:
            return zero, {**audit, "state": "extended_before_entry", "label_end_date": observed_day}
        if not (price["close"] > pivot and price["volume"] >= state["reference_volume"] * config["breakout_volume_ratio_min"]):
            continue
        audit.update(confirmation_date=observed_day, confirmation_basis="completed_close_and_full_day_volume",
            decision_time_assumption=observed_day + "T16:00:00+08:00")
        if index + 1 >= len(calendar):
            return None, {**audit, "state": "immature_entry"}
        entry_day = calendar[index + 1]
        entry, adjusted_entry = raw.get(entry_day), adjusted.get(entry_day)
        audit["entry_date"] = entry_day
        if entry is None or adjusted_entry is None:
            return None, {**audit, "state": "unresolved_entry_data"}
        rejection = entry_rejection(entry, allow_unknown_status=True)
        if rejection:
            return zero, {**audit, "state": "unfilled_daily_proxy", "reason": rejection, "label_end_date": entry_day}
        if adjusted_entry["open"] > pivot + config["maximum_extension_atr"] * atr:
            return zero, {**audit, "state": "entry_gap_extended_skip", "label_end_date": entry_day}
        if adjusted_entry["open"] < pivot - config["entry_failure_buffer_atr"] * atr:
            return zero, {**audit, "state": "entry_gap_failed_skip", "label_end_date": entry_day}
        target, execution = labels(observed_day, raw, adjusted, calendar, benchmark,
            config["round_trip_cost_bps"], allow_unknown_status=True)
        # The longest label remains entry+5 sessions, strictly T+1 compatible.
        return target, {**audit, "execution": execution, "state": execution["state"],
            **({"label_end_date": execution["label_end_date"]} if "label_end_date" in execution else {})}
    if len(window) != config["waiting_sessions"]:
        return None, {**audit, "state": "immature_waiting_window"}
    return zero, {**audit, "state": "expired_without_confirmation", "label_end_date": window[-1]}


def build(root, config):
    root = Path(root).resolve()
    ref = config["source_manifest"]
    manifest, calendar, benchmark = context(str(root), ref["file"], ref["sha256"], config["exclude_reviewed_from"])
    origins = json.loads(gzip.decompress(checked(root, config["origin_audits"], "output/history_pilot/vcp_independent")))
    groups, identities = defaultdict(list), set()
    for item in origins:
        origin = item["evidence"]
        if digest(canonical(origin)) != item["sha256"]:
            raise ValueError("trigger_origin_audit_hash_mismatch")
        identity = (origin["code"], origin["origin"])
        if identity in identities:
            raise ValueError("trigger_duplicate_frozen_origin")
        identities.add(identity)
        groups[origin["code"]].append(origin)
    rows, audits, states = [], [], Counter()
    for code, cards in sorted(groups.items()):
        source = read_capture(root, manifest["stocks"][code])
        raw = normalize([r for r in source["rows"] if r["date"] < config["exclude_reviewed_from"]], allow_unknown_status=True)
        adjusted = causal_adjust(raw)
        points = points_for(adjusted)
        raw_map, adjusted_map = {r["day"]: r for r in raw}, {r["day"]: r for r in adjusted}
        indices = {r["day"]: i for i, r in enumerate(raw)}
        for card in cards:
            day = card["signal_date"]
            i = indices[day]
            observation = vcp.analyze(adjusted[max(0, i - 120):i + 1])
            if (not observation.get("matched") or observation.get("origin") != card["origin"]
                    or observation["stage"] not in STAGES):
                raise ValueError("trigger_frozen_origin_reconstruction_changed")
            features = features_for(points[i], observation, i - indices[card["origin"]])
            target, audit = trigger_labels(day, observation, raw_map, adjusted_map, calendar, benchmark, config)
            audit.update(code=code, origin=card["origin"], source_sha256=manifest["stocks"][code]["sha256"])
            audit_hash = digest(canonical(audit))
            audits.append({"sha256": audit_hash, "evidence": audit})
            states[audit["state"]] += 1
            if target is None:
                continue
            if audit["label_end_date"] >= config["exclude_reviewed_from"]:
                raise ValueError("trigger_label_crosses_sealed_period")
            rows.append({"date": day, "code": code.split(".")[1], "origin": card["origin"],
                "stage": observation["stage"], "features": features,
                "targets_provider_benchmark_net_proxy_pct": {str(h): target[h] for h in config["horizons_sessions"]},
                "label_end_date": audit["label_end_date"], "execution_state": audit["state"],
                "execution_audit_sha256": audit_hash, "source_sha256": manifest["stocks"][code]["sha256"]})
    if sum(states.values()) != len(origins):
        raise ValueError("trigger_origin_count_mismatch")
    return sorted(rows, key=lambda r: (r["date"], r["code"])), audits, {
        "historical_source_cohort_codes": len(manifest["selected_codes"]), "codes_with_origins": len(groups),
        "all_frozen_origins": len(origins), "resolved_label_rows": len(rows), "states": dict(states),
        "original_censored_origins_retained_for_reconstruction": sum(
            a["evidence"]["state"] in {"censored_exit", "immature_horizon"} for a in origins)}


def run(root):
    root = Path(root).resolve()
    config = json.loads((root / "config/vcp_trigger_training.json").read_bytes())
    if (config["waiting_sessions"] != 3 or config["evaluation_mode"] != "retrospective_development_only_not_new_independent_test"
            or any(config[k] for k in ("automatic_activation", "probabilities_enabled", "automatic_trading"))):
        raise ValueError("trigger_fixed_research_only_contract_required")
    code_hashes = {p: digest((root / p).read_bytes()) for p in (
        "research_system/vcp_trigger_training.py", "research_system/vcp_training.py",
        "research_system/history_dataset.py", "market_screen/vcp.py")}
    identity = digest(canonical({"config": config, "code_sha256": code_hashes}))[:24]
    directory = root / "output/history_pilot/vcp_triggered" / identity
    directory.mkdir(parents=True, exist_ok=True)
    latest = root / "output/research/latest/vcp_trigger_training_status.json"
    if (directory / "status.json").exists():
        status = json.loads((directory / "status.json").read_bytes())
        for key in ("dataset", "audits", "models", "result"):
            checked(root, status[key], "output/history_pilot/vcp_triggered")
        write(latest, status)
        return status
    immutable(root, directory / "registration.json", {"config": config, "code_sha256": code_hashes,
        "independent_final_test": False, "active_daily_model_unchanged": True})
    rows, audits, coverage = build(root, config)
    def frozen(name, payload):
        raw = gzip.compress(canonical(payload), mtime=0)
        path = directory / name
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("trigger_frozen_evidence_cannot_be_replaced")
        path.write_bytes(raw)
        return {"file": path.relative_to(root).as_posix(), "sha256": digest(raw)}
    dataset_ref = frozen("dataset.json.gz", {"metadata": {"config": config, "coverage": coverage,
        "feature_names": list(FEATURES), "scope": "trigger_aware_fixed_origin_price_only_development"}, "rows": rows})
    audits_ref = frozen("audits.json.gz", audits)
    ref = config["source_manifest"]
    manifest, calendar, _ = context(str(root), ref["file"], ref["sha256"], config["exclude_reviewed_from"])
    calendar = [d for d in calendar if d >= manifest["config"]["cohort_date"]]
    result = train(rows, calendar, config)
    now = datetime.now(TZ).isoformat()
    models_ref = immutable(root, directory / "models.json", {"version": config["version"], "model_frozen_at": now,
        "models": result.pop("models"), "feature_names": list(FEATURES), "training_dataset": dataset_ref,
        "score_meaning": "uncalibrated_ordering_not_trigger_probability_win_rate_or_promised_return",
        "automatic_activation": False})
    result_ref = immutable(root, directory / "result.json", {**result, "config": config,
        "coverage": coverage, "independent_final_test": False, "models": models_ref})
    status = {"version": config["version"], "experiment_id": identity, "generated_at": now,
        "status": "trained_trigger_aware_candidate_not_activated", "model_status": "trained_research_candidate",
        "coverage": coverage, "source_manifest": config["source_manifest"], "origin_audits": config["origin_audits"],
        "training_rows": result["training_rows"], "validation_rows": result["validation_rows"],
        "training_label_end": result["training_label_end"], "validation_label_end": result["validation_label_end"],
        "horizons": result["horizons"], "dataset": dataset_ref, "audits": audits_ref, "models": models_ref, "result": result_ref,
        "independent_final_test": False, "automatic_activation": False, "probabilities_enabled": False,
        "automatic_trading": False, "active_daily_model_unchanged": True,
        "limitations": ["reused_historical_development_not_new_independent_test", "fixed_512_origin_mainboard_cohort_not_full_market",
            "st_corporate_actions_official_benchmark_and_real_execution_not_independently_audited",
            "completed_close_confirmation_next_open_proxy_not_intraday_pivot_fill",
            "cash_zero_outcomes_are_not_winning_trades", "censored_observations_retained_but_not_trainable",
            "historical_adjusted_live_raw_feature_basis_gap", "no_live_model_replacement_from_reused_development_scores"],
        "next_action": "review_confirmed_origin_sample_size_and_actions_before_registering_separate_forward_predictions"}
    immutable(root, directory / "status.json", status)
    write(latest, status)
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = run(args.root)
    print(json.dumps({k: result[k] for k in ("status", "experiment_id", "coverage", "training_rows", "validation_rows")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
