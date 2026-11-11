"""Pre-registered Ridge / LightGBM comparison, with purged chronological labels."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics

from market_screen.early import POOLS
from .model import FEATURES as BASE_FEATURES, eligible_train, re_hash, validate_dataset

FEATURES = BASE_FEATURES + ("signal_age_sessions", "alpha101_101")
MODELS = ("ridge", "lightgbm")


def validate(data, scope="formal"):
    rows = validate_dataset(data, scope=scope)
    meta = data["metadata"]
    expected = ("next_eligible_open_after_publication", "dated_limits_halts_unfilled_audited") if scope == "formal" else (
        "simulated_next_session_open_no_wait", "conservative_daily_proxy_not_official_limit_tape")
    if (scope == "pilot" and meta.get("execution_limits_basis") == "price_only_proxy_st_status_unknown"
            and meta.get("source_provider") == "qlib_public_release"
            and meta.get("st_status") == "not_supplied_never_assumed_normal"):
        expected = ("simulated_next_session_open_no_wait", "price_only_proxy_st_status_unknown")
    if (meta.get("entry_policy"), meta.get("execution_limits_basis")) != expected:
        raise ValueError("executable_point_in_time_labels_required")
    for row in rows:
        if row.get("setup") not in POOLS:
            raise ValueError("early_setup_cohort_required")
        if not re_hash(row.get("execution_audit_sha256")):
            raise ValueError("execution_audit_hash_required")
        for f in FEATURES:
            value = row["features"].get(f)
            import math
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("complete_early_features_required:" + f)
    return rows


def matrix(rows):
    import numpy as np
    # Setup identity is included, avoiding the assumption that a fresh reclaim
    # and a squeeze precursor have the same conditional return relationship.
    x = np.asarray([[r["features"][f] for f in FEATURES] + [int(r["setup"] == p) for p in POOLS] for r in rows], dtype=float)
    y = np.asarray([r["target_t3_net_excess_pct"] for r in rows], dtype=float)
    return x, y


def fit(kind, train, valid):
    import numpy as np
    x, y = matrix(train)
    if kind == "ridge":
        means, scales = x.mean(axis=0), x.std(axis=0)
        scales[scales == 0] = 1
        z = (x - means) / scales
        weights = np.linalg.solve(z.T @ z + 10 * np.eye(x.shape[1]), z.T @ (y - y.mean()))
        return {"kind": kind, "means": means.tolist(), "scales": scales.tolist(),
                "weights": weights.tolist(), "intercept": float(y.mean())}
    if kind != "lightgbm":
        raise ValueError("unknown_preregistered_model")
    import lightgbm as lgb
    vx, vy = matrix(valid)
    # Deliberately small trees; no copied CSI300 hyperparameter optimum.
    model = lgb.train({"objective": "regression", "metric": "l2", "learning_rate": .03,
        "num_leaves": 15, "max_depth": 4, "min_data_in_leaf": 50, "lambda_l2": 10,
        "seed": 20261105, "num_threads": 2, "verbosity": -1, "deterministic": True, "force_col_wise": True},
        lgb.Dataset(x, label=y), num_boost_round=200, valid_sets=[lgb.Dataset(vx, label=vy)],
        callbacks=[lgb.early_stopping(20, verbose=False)])
    return {"kind": kind, "model_string": model.model_to_string(), "best_iteration": model.best_iteration}


def predictions(model, rows):
    import numpy as np
    x, _ = matrix(rows)
    if model["kind"] == "ridge":
        return (model["intercept"] + ((x - model["means"]) / model["scales"]) @ np.asarray(model["weights"])).tolist()
    import lightgbm as lgb
    return lgb.Booster(model_str=model["model_string"]).predict(x, num_threads=2).tolist()


def daily_results(rows, scores):
    by_day = defaultdict(lambda: defaultdict(list))
    for r, score in zip(rows, scores):
        by_day[r["date"]][r["setup"]].append((r, float(score)))
    out = []
    for day, pools in sorted(by_day.items()):
        chosen, controls, legacy = {}, {}, {}
        for pool, cohort in pools.items():
            best = max(cohort, key=lambda v: (v[1], v[0]["code"]))[0]
            old = min((r for r, _ in cohort), key=lambda r:
                (r["features"]["signal_age_sessions"], abs(r["features"]["distance_to_mid_atr"]), r["code"]))
            chosen[best["code"]], controls[old["code"]] = best, old
            eligible = [r for r, _ in cohort if r.get("baseline_v1_eligible") and r.get("baseline_v1_score") is not None]
            if eligible:
                v1 = max(eligible, key=lambda r: (r["baseline_v1_score"], r["code"]))
                legacy[v1["code"]] = v1
        mean = lambda group: statistics.mean(r["target_t3_net_excess_pct"] for r in group.values()) if group else None
        out.append({"date": day, "net_excess_pct": mean(chosen), "early_rule_control_pct": mean(controls),
                    "paired_improvement_pct": mean(chosen) - mean(controls),
                    "v1_same_cohort_control_pct": mean(legacy), "selected_codes": sorted(chosen),
                    "mean_signal_age_sessions": statistics.mean(r["features"]["signal_age_sessions"] for r in chosen.values()),
                    "mean_abs_mid_distance_atr": statistics.mean(abs(r["features"]["distance_to_mid_atr"]) for r in chosen.values())})
    return out


def block_interval(values, block=5, repeats=1000):
    """Calendar-date blocks; never treat same-day stocks as independent trials."""
    import random
    if len(values) < 20:
        return None
    rng, means = random.Random(20261105), []
    for _ in range(repeats):
        sample = []
        while len(sample) < len(values):
            start = rng.randrange(max(1, len(values) - block + 1))
            sample.extend(values[start:start + block])
        means.append(statistics.mean(sample[:len(values)]))
    means.sort()
    return [means[int(repeats * .025)], means[min(repeats - 1, int(repeats * .975))]]


def summarize(days):
    delta = [d["paired_improvement_pct"] for d in days]
    return {"signal_dates": len(days),
            "date_balanced_mean_net_excess_pct": statistics.mean(d["net_excess_pct"] for d in days) if days else None,
            "paired_early_rule_improvement_pct": statistics.mean(delta) if delta else None,
            "paired_improvement_5_session_block_95_interval": block_interval(delta),
            "mean_signal_age_sessions": statistics.mean(d["mean_signal_age_sessions"] for d in days) if days else None,
            "mean_abs_mid_distance_atr": statistics.mean(d["mean_abs_mid_distance_atr"] for d in days) if days else None,
            "measurement": "overlapping_fixed_horizon_labels_not_portfolio_pnl"}


def split(rows, dates, test_start, purge=5):
    vstart = test_start - 63 - purge
    train_dates = set(dates[max(0, vstart - purge - 378):vstart - purge])
    train = eligible_train(rows, train_dates, dates[vstart])
    valid_dates = set(dates[vstart:test_start - purge])
    valid = eligible_train(rows, valid_dates, dates[test_start])
    return train, valid


def experiment(data, minimum_sessions=720, holdout_sessions=120, fitter=fit, scope="formal"):
    rows = validate(data, scope=scope)
    dates = sorted({r["date"] for r in rows})
    if len(dates) < minimum_sessions:
        return {"status": "blocked_insufficient_qualified_history", "feature_dates": len(dates),
                "required_sessions": minimum_sessions, "production_activation": False, "model_status": "not_trained"}
    if holdout_sessions < 20 or len(dates) - holdout_sessions < 451:
        raise ValueError("insufficient_pre_holdout_development_span")
    boundary = len(dates) - holdout_sessions
    folds, validation = [], defaultdict(list)
    for t in range(451, boundary - 62, 63):
        train, valid = split(rows, dates, t)
        test_set = set(dates[t:t + 63])
        test = [r for r in rows if r["date"] in test_set and r["label_end_date"] < dates[boundary]]
        if not train or not valid or not test:
            continue
        result = {}
        for kind in MODELS:
            fitted = fitter(kind, train, valid)
            vd = daily_results(valid, predictions(fitted, valid))
            validation[kind].extend(vd)
            result[kind] = {"validation": summarize(vd), "test": summarize(daily_results(test, predictions(fitted, test)))}
        folds.append({"train_start": min(r["date"] for r in train), "validation_start": min(r["date"] for r in valid),
                      "test_start": dates[t], "models": result})
    if not folds:
        return {"status": "blocked_no_usable_rolling_folds", "model_status": "not_trained", "production_activation": False}
    # Choose by DEVELOPMENT validation only. A tiny margin favours the simpler control.
    quality = {k: summarize(v)["paired_early_rule_improvement_pct"] for k, v in validation.items()}
    chosen = "lightgbm" if quality["lightgbm"] > quality["ridge"] + .02 else "ridge"
    train, valid = split(rows, dates, boundary)
    model = fitter(chosen, train, valid)
    holdout = [r for r in rows if r["date"] >= dates[boundary]]
    final = summarize(daily_results(holdout, predictions(model, holdout)))
    return {"status": "pilot_results_not_production_qualified" if scope == "pilot" else "research_results_require_execution_and_source_review",
        "model_status": "trained_pilot_only" if scope == "pilot" else "trained_research_only", "dataset_scope": scope,
        "feature_dates": len(dates), "training_rows": len(rows), "selected_model": chosen,
        "selection_basis": "development_validation_only_simpler_model_margin_0.02_percentage_point",
        "validation_comparison": quality, "rolling_folds": folds, "locked_holdout_start": dates[boundary],
        "final_holdout": final, "model": model, "production_activation": False, "probabilities_enabled": False,
        "remaining_gates": ["raw_source_and_historical_universe_audit", "cost_and_limit_fill_replay",
            "risk_and_drawdown_noninferiority", "date_block_uncertainty_and_multiple_trials",
            "forward_operations_and_explicit_model_promotion"],
        "comparison_scope": "models_compared_within_same_early_setup_cohort; not_full_universe_v1_strategy_comparison",
        "method_origin": "Qlib_style_workflow_and_small_LightGBM; selected_price_volume_features_and_Alpha101_101; not_full_Alpha158_replication"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    result = experiment(json.loads(raw))
    result["dataset_sha256"] = hashlib.sha256(raw).hexdigest()
    from market_screen.history import write_json
    write_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in {"model", "rolling_folds"}}, ensure_ascii=False))


def run_registered(root):
    """A source manifest may enable training; absence is a truthful blocked receipt."""
    from market_screen.history import write_json
    root = Path(root).resolve()
    registration = root / "config/early_model_dataset.json"
    result = {"method_version": "boll_early_v3_20261105",
              "status": "blocked_missing_qualified_dataset", "model_status": "not_trained",
              "production_activation": False, "probabilities_enabled": False,
              "required": ["720_point_in_time_feature_dates", "official_benchmarks",
                           "asof_corporate_actions", "audited_t_plus_1_limits_and_fills"]}
    if registration.exists():
        reference = json.loads(registration.read_text())
        path = (root / reference["file"]).resolve()
        if not path.is_relative_to(root / "output/research/datasets"):
            raise ValueError("model_dataset_outside_registered_directory")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
            raise ValueError("registered_model_dataset_hash_mismatch")
        result = experiment(json.loads(raw))
        result["dataset_sha256"] = reference["sha256"]
    pilot_path = root / "output/research/latest/history_pilot_status.json"
    if pilot_path.exists():
        pilot = json.loads(pilot_path.read_text())
        result["historical_pilot"] = {k: pilot.get(k) for k in (
            "status", "model_status", "generated_at", "sample_size", "history_start", "history_end",
            "feature_dates", "training_rows", "source_failures", "remaining_gaps", "next_action", "result_file",
            "reason", "error_type", "formal_model_status", "provider", "label_scope", "selected_model")}
    write_json(root / "output/research/latest/early_model_status.json", result)
    return {k: v for k, v in result.items() if k not in {"model", "rolling_folds"}}


if __name__ == "__main__":
    main()
