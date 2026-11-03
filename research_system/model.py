"""Leakage-controlled ridge experiment. Training never activates production."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

FEATURES = ("mid_slope_5d_atr", "distance_to_mid_atr", "bandwidth_percentile_120",
            "return_5d_pct", "return_20d_pct", "volume_vs_previous20_median",
            "relative_market_5d_pct", "relative_market_20d_pct")


def fit_ridge(rows, alpha=10.0):
    import numpy as np
    x = np.asarray([[r["features"][f] for f in FEATURES] for r in rows], dtype=float)
    y = np.asarray([r["target_t3_net_excess_pct"] for r in rows], dtype=float)
    if len(rows) < len(FEATURES) + 2 or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("insufficient_or_nonfinite_training_rows")
    means, scales = x.mean(axis=0), x.std(axis=0)
    scales[scales == 0] = 1
    z = (x - means) / scales
    intercept = float(y.mean())
    weights = np.linalg.solve(z.T @ z + alpha * np.eye(len(FEATURES)), z.T @ (y - intercept))
    return {"features": list(FEATURES), "means": means.tolist(), "scales": scales.tolist(),
            "weights": weights.tolist(), "intercept": intercept, "alpha": alpha,
            "meaning": "experimental_t_plus_3_net_excess_estimate_not_probability"}


def predict(model, row):
    return model["intercept"] + sum((row["features"][f] - m) / s * w
        for f, m, s, w in zip(model["features"], model["means"], model["scales"], model["weights"]))


def metrics(rows, model):
    from collections import defaultdict
    import statistics
    days = defaultdict(list)
    for row in rows:
        days[row["date"]].append(row)
    selected, baseline, paired_days, differences, day_returns = [], [], [], [], []
    for day, cohort in sorted(days.items()):
        chosen = sorted(cohort, key=lambda r: (-predict(model, r), r["code"]))[:10]
        values = [r["target_t3_net_excess_pct"] for r in chosen]
        selected.extend(values)
        day_returns.append(statistics.mean(values))
        controls = sorted((r for r in cohort if r.get("baseline_v1_eligible") and r.get("baseline_v1_score") is not None),
                          key=lambda r: (-r["baseline_v1_score"], r["code"]))[:10]
        if controls:
            old = [r["target_t3_net_excess_pct"] for r in controls]
            baseline.extend(old)
            paired_days.append(day)
            differences.append(statistics.mean(values) - statistics.mean(old))
    return {"rows": len(rows), "signal_dates": len(days), "selected_rows": len(selected),
            "daily_equal_weight_mean_net_excess_pct": statistics.mean(day_returns) if day_returns else None,
            "positive_label_fraction": sum(x > 0 for x in selected) / len(selected) if selected else None,
            "baseline_v1_mean_net_excess_pct": statistics.mean(baseline) if baseline else None,
            "paired_control_dates": len(paired_days),
            "paired_daily_improvement_pct": statistics.mean(differences) if differences else None,
            "portfolio_maximum_drawdown": None,
            "note": "Date-balanced fixed-horizon labels; overlapping dates are not independent portfolio trades."}


def validate_dataset(data):
    import math
    from .ledger import stamp
    meta = data.get("metadata", {})
    if meta.get("universe_basis") != "historical_point_in_time" or meta.get("benchmark_basis") != "verified_official":
        raise ValueError("historical_universe_and_official_benchmark_required")
    if meta.get("corporate_actions_basis") != "asof_adjusted_and_execution_prices_retained":
        raise ValueError("point_in_time_corporate_actions_required")
    if meta.get("primary_horizon_sessions") != 3 or meta.get("costs_in_target") is not True:
        raise ValueError("t_plus_3_net_excess_label_required")
    asof = stamp(meta["asof"])
    rows, seen = data.get("rows", []), set()
    for row in rows:
        key = (row["date"], row["code"])
        if key in seen:
            raise ValueError("duplicate_stock_signal_date")
        seen.add(key)
        issued, known, label_known = stamp(row["signal_available_at"]), stamp(row["features_known_at"]), stamp(row["label_known_at"])
        if not known <= issued < label_known <= asof or issued.date().isoformat() != row["date"]:
            raise ValueError("point_in_time_feature_label_chain_invalid")
        if row["label_end_date"] <= row["date"] or row["label_end_date"] > label_known.date().isoformat():
            raise ValueError("invalid_forward_label_end")
        if not re_hash(row.get("source_sha256", "")):
            raise ValueError("source_hash_reference_required")
        if not all(isinstance(row["features"].get(f), (int, float)) and not isinstance(row["features"].get(f), bool)
                   and math.isfinite(row["features"][f]) for f in FEATURES):
            raise ValueError("complete_finite_features_required")
        if not math.isfinite(float(row["target_t3_net_excess_pct"])):
            raise ValueError("nonfinite_target")
    return sorted(rows, key=lambda r: (r["date"], r["code"]))


def re_hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def eligible_train(rows, date_set, boundary):
    # Purge by BOTH feature dates and actual label end, including halted stocks.
    return [r for r in rows if r["date"] in date_set and r["label_end_date"] < boundary]


def experiment(data, minimum_sessions=720, holdout_sessions=120, purge=5):
    rows = validate_dataset(data)
    dates = sorted({r["date"] for r in rows})
    if len(dates) < minimum_sessions:
        return {"status": "blocked_insufficient_history", "feature_dates": len(dates),
                "required_sessions": minimum_sessions, "production_activation": False}
    start_holdout = len(dates) - holdout_sessions
    if start_holdout <= 0:
        raise ValueError("holdout_leaves_no_training_data")
    folds = []
    for test_start in range(378 + 63 + 2 * purge, start_holdout - 62, 63):
        train_dates = set(dates[test_start - 63 - 2 * purge - 378:test_start - 63 - 2 * purge])
        val_start = test_start - 63 - purge
        train = eligible_train(rows, train_dates, dates[val_start])
        valid_dates = set(dates[val_start:test_start - purge])
        valid = [r for r in rows if r["date"] in valid_dates and r["label_end_date"] < dates[test_start]]
        test_dates = set(dates[test_start:test_start + 63])
        # Keep development labels out of the locked final holdout.
        test = [r for r in rows if r["date"] in test_dates and r["label_end_date"] < dates[start_holdout]]
        if not train or not valid or not test:
            continue
        model = fit_ridge(train)
        folds.append({"train_start": min(train_dates), "validation_start": dates[val_start],
                      "test_start": dates[test_start], "train_rows": len(train),
                      "validation": metrics(valid, model), "test": metrics(test, model)})
    if not folds:
        return {"status": "blocked_no_valid_rolling_folds", "production_activation": False}
    final_train_dates = set(dates[:start_holdout - purge])
    train = eligible_train(rows, final_train_dates, dates[start_holdout])
    model = fit_ridge(train)
    final = [r for r in rows if r["date"] in set(dates[start_holdout:])]
    return {"status": "research_results_require_review", "model": model, "rolling_folds": folds,
            "locked_holdout_start": dates[start_holdout], "final_holdout": metrics(final, model),
            "production_activation": False, "probabilities_enabled": False,
            "required_review": ["source_bytes_and_point_in_time_universe", "date_block_uncertainty_and_multiple_trials",
                                "drawdown_and_executable_exit_backtest", "20_session_forward_operations", "manual_promotion"],
            "source_validation": "dataset timing/hash references checked; referenced raw evidence needs independent audit"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    result = experiment(json.loads(raw))
    result["dataset_sha256"] = hashlib.sha256(raw).hexdigest()
    from report_support.index import write_json
    write_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in {"model", "rolling_folds"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
