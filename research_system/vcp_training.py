"""Independent VCP-origin daily cohort; fixed multi-horizon research candidates.

This is development work on captured provider history, not new independent
performance evidence. It never reads or updates the daily model's active state.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

from market_screen import vcp
from .daily_model import immutable
from .daily_model_data import checked
from .history_dataset import causal_adjust, labels, normalize, points_for
from .history_source import TZ, canonical, digest, read_capture, select_cohort, write

STAGES = ("preparing", "near_pivot", "breakout_volume_unconfirmed", "breakout_close_volume_confirmed")
FEATURES = ("mid_slope_5d_atr", "distance_to_mid_atr", "bandwidth_percentile_120",
    "return_5d_pct", "return_20d_pct", "volume_vs_previous20_median",
    "vcp_contractions", "vcp_contraction_ratio", "vcp_dry_volume_ratio", "vcp_pivot_distance_atr",
    "tight5_range_pct", "risk_from_pivot_pct", "origin_age_sessions",
    "stage_near_pivot", "stage_breakout_unconfirmed", "stage_breakout_confirmed")


@lru_cache(maxsize=2)
def context(root_string, manifest_file, manifest_hash, cutoff):
    root = Path(root_string)
    manifest = json.loads(gzip.decompress(checked(root,
        {"file": manifest_file, "sha256": manifest_hash}, "output/history_pilot/experiments")))
    if (not manifest.get("cohort_complete") or manifest.get("source_failures")
            or manifest.get("provider") != "qlib_public_release"
            or manifest.get("status_basis") != "unavailable_st_price_only_research"):
        raise ValueError("vcp_independent_requires_complete_hash_bound_price_only_source")
    membership = read_capture(root, manifest["membership"])
    config = manifest["config"]
    if (membership["request"]["kwargs"].get("day") != config["cohort_date"]
            or select_cohort(membership["rows"], config["sample_size"], config["seed"]) != manifest["selected_codes"]
            or set(manifest["stocks"]) != set(manifest["selected_codes"])):
        raise ValueError("vcp_independent_historical_origin_cohort_changed")
    calendar = [r["calendar_date"] for r in read_capture(root, manifest["calendar"])["rows"]
                if r["is_trading_day"] == "1" and r["calendar_date"] < cutoff]
    if not calendar or calendar != sorted(set(calendar)):
        raise ValueError("vcp_independent_invalid_calendar")
    benchmark_rows = normalize([r for r in read_capture(root, manifest["benchmark"])["rows"]
                                if r["date"] < cutoff], index=True)
    if any(r["code"] != config["benchmark_code"] for r in benchmark_rows):
        raise ValueError("vcp_independent_benchmark_identity")
    return manifest, calendar, {r["day"]: r for r in benchmark_rows}


def features_for(point, observed, age):
    atr = point["atr20"]
    features = {k: point[k] for k in ("mid_slope_5d_atr", "return_5d_pct", "return_20d_pct")}
    features.update(distance_to_mid_atr=(point["close"] - point["mid"]) / atr,
        bandwidth_percentile_120=point["width_percentile"], volume_vs_previous20_median=point["volume_ratio_complete"],
        **{k: value for k, value in vcp.feature_values(observed).items() if k in FEATURES},
        tight5_range_pct=observed["tight5_range_pct"], risk_from_pivot_pct=observed["risk_from_pivot_pct"],
        origin_age_sessions=age, stage_near_pivot=int(observed["stage"] == "near_pivot"),
        stage_breakout_unconfirmed=int(observed["stage"] == "breakout_volume_unconfirmed"),
        stage_breakout_confirmed=int(observed["stage"] == "breakout_close_volume_confirmed"))
    if set(features) != set(FEATURES) or any(isinstance(v, bool) or not isinstance(v, (int, float))
            or not math.isfinite(v) for v in features.values()):
        raise ValueError("vcp_independent_nonfinite_or_missing_feature")
    return features


def build_stock(job):
    root_string, config, code = job
    root, cutoff = Path(root_string), config["exclude_reviewed_from"]
    ref = config["source_manifest"]
    manifest, calendar, benchmark = context(root_string, ref["file"], ref["sha256"], cutoff)
    source = read_capture(root, manifest["stocks"][code])
    expected = {"code": code, "start_date": manifest["config"]["history_start"],
        "end_date": manifest["config"]["history_end"], "frequency": "d", "adjustflag": "3"}
    if source["request"]["method"] != "query_history_k_data_plus" or any(
            source["request"]["kwargs"].get(k) != value for k, value in expected.items()):
        raise ValueError("vcp_independent_stock_request_identity")
    # Filter the inspected/sealed interval before adjustment, feature or label construction.
    raw = normalize([r for r in source["rows"] if r["date"] < cutoff], allow_unknown_status=True)
    if any(r["code"] != code or r["day"] not in calendar for r in raw):
        raise ValueError("vcp_independent_stock_identity_or_calendar")
    adjusted = causal_adjust(raw)
    points = points_for(adjusted)
    raw_map, adjusted_map = {r["day"]: r for r in raw}, {r["day"]: r for r in adjusted}
    indices = {r["day"]: i for i, r in enumerate(raw)}
    rows, audits, counts, seen = [], [], Counter(), set()
    for i in range(159, len(raw)):
        bar, day = raw[i], raw[i]["day"]
        if (day < manifest["config"]["cohort_date"] or bar["tradestatus"] != "1"
                or bar["isST"] not in {"0", "unknown"} or bar["volume"] <= 0 or bar["high"] == bar["low"]):
            counts["ineligible_bar"] += 1
            continue
        observation = vcp.analyze(adjusted[max(0, i - 120):i + 1])
        counts["evaluated_stock_days"] += 1
        if not observation.get("matched") or observation["stage"] not in STAGES:
            continue
        counts["eligible_vcp_stock_days_before_dedup"] += 1
        if statistics.median(r["amount"] for r in raw[i - 19:i + 1]) < config["minimum_turnover_cny"]:
            counts["low_liquidity_proxy"] += 1
            continue
        origin = observation["origin"]
        if origin in seen:
            counts["repeated_origin_suppressed"] += 1
            continue
        # An unfilled/censored first observation cannot be replaced by a later winner.
        seen.add(origin)
        features = features_for(points[i], observation, i - indices[origin])
        targets, audit = labels(day, raw_map, adjusted_map, calendar, benchmark,
            config["round_trip_cost_bps"], allow_unknown_status=True)
        audit.update(code=code, origin=origin, setup="independent_vcp_observation")
        audit_hash = digest(canonical(audit))
        audits.append({"sha256": audit_hash, "evidence": audit})
        if targets is None:
            counts[audit["state"]] += 1
            continue
        if audit["label_end_date"] >= cutoff:
            raise ValueError("vcp_independent_sealed_label_leakage")
        rows.append({"date": day, "code": code.split(".")[1], "origin": origin,
            "stage": observation["stage"], "features": features,
            "targets_provider_benchmark_net_proxy_pct": {str(h): targets[h] for h in config["horizons_sessions"]},
            "label_end_date": audit["label_end_date"], "execution_state": audit["state"],
            "source_sha256": manifest["stocks"][code]["sha256"], "execution_audit_sha256": audit_hash,
            "signal_time_basis": "historical_simulated_close_not_actual_public_prediction"})
        counts["unique_origin_samples"] += 1
    return {"code": code, "source_sha256": manifest["stocks"][code]["sha256"],
        "captured_source_rows": len(source["rows"]), "pre_cutoff_bars": len(raw),
        "counts": dict(counts), "rows": rows, "audits": audits}


def matrix(rows, horizon):
    import numpy as np
    x = np.asarray([[r["features"][f] for f in FEATURES] for r in rows], dtype=float)
    y = np.asarray([r["targets_provider_benchmark_net_proxy_pct"][str(horizon)] for r in rows], dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("vcp_independent_nonfinite_matrix")
    return x, y


def fit_model(kind, train, valid, horizon, config):
    import numpy as np
    x, y = matrix(train, horizon)
    if kind == "ridge":
        means, scales = x.mean(axis=0), x.std(axis=0)
        scales[scales == 0] = 1
        z = (x - means) / scales
        weights = np.linalg.solve(z.T @ z + 10 * np.eye(len(FEATURES)), z.T @ (y - y.mean()))
        return {"kind": kind, "features": list(FEATURES), "means": means.tolist(), "scales": scales.tolist(),
            "weights": weights.tolist(), "intercept": float(y.mean())}
    if kind != "lightgbm":
        raise ValueError("vcp_independent_unknown_model")
    import lightgbm as lgb
    vx, vy = matrix(valid, horizon)
    settings = dict(config["lightgbm"])
    rounds, patience = settings.pop("num_boost_round"), settings.pop("early_stopping_rounds")
    model = lgb.train({**settings, "objective": "regression", "metric": "l2", "num_threads": 2,
        "verbosity": -1, "deterministic": True, "force_col_wise": True}, lgb.Dataset(x, label=y),
        num_boost_round=rounds, valid_sets=[lgb.Dataset(vx, label=vy)],
        callbacks=[lgb.early_stopping(patience, verbose=False)])
    return {"kind": kind, "features": list(FEATURES), "model_string": model.model_to_string(),
        "best_iteration": model.best_iteration}


def predict(model, rows):
    import numpy as np
    if model["features"] != list(FEATURES):
        raise ValueError("vcp_independent_feature_order_changed")
    x = np.asarray([[r["features"][f] for f in FEATURES] for r in rows], dtype=float)
    if model["kind"] == "ridge":
        return (model["intercept"] + ((x - model["means"]) / model["scales"]) @ np.asarray(model["weights"])).tolist()
    import lightgbm as lgb
    return lgb.Booster(model_str=model["model_string"]).predict(x, num_threads=2).tolist()


def temporal_split(rows, calendar, start, config):
    purge, length = config["purge_sessions"], config["validation_sessions"]
    vstart = start - length - purge
    train_days = set(calendar[max(0, vstart - purge - config["training_sessions"]):vstart - purge])
    valid_days = set(calendar[vstart:start - purge])
    boundary = calendar[start] if start < len(calendar) else config["exclude_reviewed_from"]
    train = [r for r in rows if r["date"] in train_days and r["label_end_date"] < calendar[vstart]]
    valid = [r for r in rows if r["date"] in valid_days and r["label_end_date"] < boundary]
    return train, valid


def daily_comparison(rows, scores, horizon):
    grouped = defaultdict(list)
    for row, score in zip(rows, scores):
        if not math.isfinite(float(score)):
            raise ValueError("vcp_independent_nonfinite_prediction")
        grouped[row["date"]].append((row, float(score)))
    results = []
    key = str(horizon)
    for day, group in sorted(grouped.items()):
        chosen = min(group, key=lambda pair: (-pair[1], pair[0]["code"]))[0]
        rule = min((r for r, _ in group), key=lambda r: (abs(r["features"]["vcp_pivot_distance_atr"]), r["code"]))
        a, b = chosen["targets_provider_benchmark_net_proxy_pct"][key], rule["targets_provider_benchmark_net_proxy_pct"][key]
        results.append({"date": day, "chosen_code": chosen["code"], "rule_code": rule["code"],
            "chosen_stage": chosen["stage"], "model_proxy_pct": a, "rule_proxy_pct": b,
            "model_minus_rule_proxy_pct": a - b, "cohort_count": len(group)})
    return results


def summarize_days(days, calendar):
    values = {r["date"]: r["model_minus_rule_proxy_pct"] for r in days}
    interval = None
    if len(values) >= 20:
        dates = [d for d in calendar if days[0]["date"] <= d <= days[-1]["date"]]
        rng, bootstrap = random.Random(20261117), []
        for _ in range(1000):
            sample = []
            while len(sample) < len(dates):
                index = rng.randrange(max(1, len(dates) - 4))
                sample.extend(dates[index:index + 5])
            observed = [values[d] for d in sample[:len(dates)] if d in values]
            if observed:
                bootstrap.append(statistics.mean(observed))
        bootstrap.sort()
        if bootstrap:
            interval = [bootstrap[int(.025 * len(bootstrap))], bootstrap[min(len(bootstrap) - 1, int(.975 * len(bootstrap)))]]
    return {"signal_dates": len(days), "date_balanced_model_net_proxy_pct": statistics.mean(r["model_proxy_pct"] for r in days) if days else None,
        "date_balanced_rule_net_proxy_pct": statistics.mean(r["rule_proxy_pct"] for r in days) if days else None,
        "paired_model_minus_rule_proxy_pct": statistics.mean(values.values()) if values else None,
        "paired_difference_5_calendar_session_block_95_interval": interval,
        "rank_differences": sum(r["chosen_code"] != r["rule_code"] for r in days),
        "measurement": "provider_benchmark_price_proxy_labels_not_official_excess_or_portfolio_pnl"}


def train(rows, calendar, config):
    if any(r["date"] >= config["exclude_reviewed_from"] or r["label_end_date"] >= config["exclude_reviewed_from"] for r in rows):
        raise ValueError("vcp_independent_previously_reviewed_period_leakage")
    if len({(r["code"], r["origin"]) for r in rows}) != len(rows):
        raise ValueError("vcp_independent_duplicate_origin")
    train_rows, valid = temporal_split(rows, calendar, len(calendar), config)
    if len(train_rows) < config["minimum_train_rows"] or len(valid) < config["minimum_validation_rows"]:
        raise ValueError("vcp_independent_insufficient_chronological_training_rows")
    models, summary, daily, folds = {}, {}, {}, []
    first = config["training_sessions"] + config["validation_sessions"] + 2 * config["purge_sessions"]
    fold_samples = []
    for start in range(first, len(calendar), config["rolling_sessions"]):
        a, b = temporal_split(rows, calendar, start, config)
        test_days = set(calendar[start:start + config["rolling_sessions"]])
        test = [r for r in rows if r["date"] in test_days]
        if len(a) < config["minimum_train_rows"] or len(b) < config["minimum_validation_rows"] or not test:
            folds.append({"test_start": calendar[start], "status": "insufficient_rows", "train": len(a), "validation": len(b), "test": len(test)})
            continue
        fold_samples.append((a, b, test))
        folds.append({"test_start": calendar[start], "test_end": max(test_days), "status": "evaluated_development_only",
            "training_label_end": max(r["label_end_date"] for r in a), "validation_start": min(r["date"] for r in b),
            "validation_label_end": max(r["label_end_date"] for r in b), "train": len(a), "validation": len(b), "test": len(test)})
    for horizon in config["horizons_sessions"]:
        key = str(horizon)
        models[key], summary[key], daily[key] = {}, {}, {}
        for kind in ("ridge", "lightgbm"):
            observations = []
            for a, b, test in fold_samples:
                model = fit_model(kind, a, b, horizon, config)
                observations.extend(daily_comparison(test, predict(model, test), horizon))
            models[key][kind] = fit_model(kind, train_rows, valid, horizon, config)
            daily[key][kind] = observations
            summary[key][kind] = summarize_days(observations, calendar)
        print({"trained_horizon": horizon, "training_rows": len(train_rows), "validation_rows": len(valid), "rolling_folds": len(fold_samples)}, flush=True)
    return {"models": models, "horizons": summary, "out_of_fold_daily_results": daily, "rolling_folds": folds,
        "training_rows": len(train_rows), "validation_rows": len(valid),
        "training_feature_start": min(r["date"] for r in train_rows), "training_label_end": max(r["label_end_date"] for r in train_rows),
        "validation_feature_start": min(r["date"] for r in valid), "validation_label_end": max(r["label_end_date"] for r in valid)}


def run(root, workers=4):
    root = Path(root).resolve()
    config = json.loads((root / "config/vcp_training.json").read_bytes())
    if config["evaluation_mode"] != "retrospective_development_only_not_new_independent_test" or any(
            config[k] for k in ("automatic_activation", "probabilities_enabled", "automatic_trading")):
        raise ValueError("vcp_independent_research_only_contract_required")
    ref = config["source_manifest"]
    manifest, full_calendar, _ = context(str(root), ref["file"], ref["sha256"], config["exclude_reviewed_from"])
    calendar = [d for d in full_calendar if d >= manifest["config"]["cohort_date"]]
    code_hashes = {name: digest((root / name).read_bytes()) for name in (
        "research_system/vcp_training.py", "research_system/history_dataset.py", "market_screen/vcp.py")}
    experiment = digest(canonical({"config": config, "code_sha256": code_hashes}))[:24]
    directory = root / "output/history_pilot/vcp_independent" / experiment
    directory.mkdir(parents=True, exist_ok=True)
    status_path = directory / "status.json"
    latest_path = root / "output/research/latest/vcp_training_status.json"
    if status_path.exists():
        status = json.loads(status_path.read_bytes())
        for key in ("dataset", "models", "result", "audits"):
            checked(root, status[key], "output/history_pilot/vcp_independent")
        write(latest_path, status)
        return status
    immutable(root, directory / "registration.json", {"config": config, "code_sha256": code_hashes,
        "source_scope": "512_fixed_historical_origin_mainboard_members_not_full_market",
        "independent_final_test": False, "live_active_model_unchanged": True})
    packs, missing = [], []
    for code in manifest["selected_codes"]:
        path = directory / "stocks" / (code + ".json.gz")
        if path.exists():
            pack = json.loads(gzip.decompress(path.read_bytes()))
            if pack["source_sha256"] != manifest["stocks"][code]["sha256"]:
                raise ValueError("vcp_independent_cached_source_changed")
            packs.append(pack)
        else:
            missing.append(code)
    with ProcessPoolExecutor(max_workers=workers) as executor:
        tasks = {executor.submit(build_stock, (str(root), config, code)): code for code in missing}
        for task in as_completed(tasks):
            code, pack = tasks[task], task.result()
            path = directory / "stocks" / (code + ".json.gz")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(canonical(pack), mtime=0))
            packs.append(pack)
            if len(packs) % 32 == 0 or len(packs) == len(manifest["selected_codes"]):
                print({"vcp_codes_built": len(packs), "total": len(manifest["selected_codes"]), "samples": sum(len(p["rows"]) for p in packs)}, flush=True)
    packs.sort(key=lambda p: p["code"])
    rows = sorted((r for p in packs for r in p["rows"]), key=lambda r: (r["date"], r["code"]))
    counts = Counter()
    for pack in packs:
        counts.update(pack["counts"])
    dataset = {"metadata": {"source_manifest": ref, "config": config, "feature_names": list(FEATURES),
        "cohort": "independent_vcp_origins_not_filtered_by_boll_pools", "st_status": "unknown_not_assumed_normal",
        "label_basis": "causally_adjusted_provider_benchmark_price_proxy_official_tieout_pending"}, "rows": rows}
    def frozen_gzip(name, payload):
        path = directory / name
        raw = gzip.compress(canonical(payload), mtime=0)
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("vcp_independent_refuse_evidence_replacement")
        path.write_bytes(raw)
        return {"file": path.relative_to(root).as_posix(), "sha256": digest(raw)}
    dataset_ref = frozen_gzip("dataset.json.gz", dataset)
    audits_ref = frozen_gzip("audits.json.gz", [a for p in packs for a in p["audits"]])
    result = train(rows, calendar, config)
    now = datetime.now(TZ).isoformat()
    model_ref = immutable(root, directory / "models.json", {"version": config["version"], "model_frozen_at": now,
        "feature_names": list(FEATURES), "models": result.pop("models"), "training_dataset": dataset_ref,
        "score_meaning": "uncalibrated_ranking_not_probability_or_promised_return", "automatic_activation": False})
    result_ref = immutable(root, directory / "result.json", {**result, "config": config, "independent_final_test": False,
        "evaluation_mode": config["evaluation_mode"], "models": model_ref})
    status = {"version": config["version"], "generated_at": now, "experiment_id": experiment,
        "status": "trained_candidate_not_activated", "model_status": "trained_research_candidate",
        "source_manifest": ref, "sampled_codes": len(packs), "source_failures": 0,
        "captured_source_rows": sum(p["captured_source_rows"] for p in packs),
        "pre_cutoff_bars": sum(p["pre_cutoff_bars"] for p in packs), "coverage": dict(counts),
        "unique_origin_samples": len(rows), "feature_dates": len({r["date"] for r in rows}),
        "stage_counts": dict(Counter(r["stage"] for r in rows)), "training_rows": result["training_rows"],
        "validation_rows": result["validation_rows"], "training_label_end": result["training_label_end"],
        "validation_label_end": result["validation_label_end"], "horizons": result["horizons"],
        "dataset": dataset_ref, "audits": audits_ref, "models": model_ref, "result": result_ref,
        "independent_final_test": False, "automatic_activation": False, "probabilities_enabled": False,
        "automatic_trading": False, "active_daily_model_unchanged": True,
        "limitations": ["retrospective_development_reused_not_independent_test",
            "fixed_512_origin_cohort_excludes_later_listings_not_full_market", "historical_st_status_unknown",
            "official_benchmark_corporate_actions_and_execution_not_independently_tied_out",
            "observation_next_open_labels_do_not_model_pivot_trigger_fills", "historical_causal_adjusted_vs_live_raw_basis_gap",
            "no_new_prospective_outcomes_matured_by_training"],
        "next_action": "audit_feature_basis_and_execution_then_register_separate_forward_candidate_without_replacing_old_predictions"}
    immutable(root, status_path, status)
    write(latest_path, status)
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    status = run(args.root, args.workers)
    print(json.dumps({k: status[k] for k in ("status", "experiment_id", "sampled_codes", "unique_origin_samples", "training_rows", "validation_rows")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
