"""Expanded retrospective review. Previously inspected dates never become holdouts again."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import math
import statistics

from .early_model import MODELS, block_interval, daily_results, fit, predictions, split, summarize, validate


def diagnostic_table(rows, scores):
    """Describe frozen out-of-fold choices; none of these slices select a model."""
    days = daily_results(rows, scores)
    chosen = {(d["date"], code) for d in days for code in d["selected_codes"]}
    selected = [r for r in rows if (r["date"], r["code"]) in chosen]

    def describe(group):
        by_day = defaultdict(list)
        for row in group:
            by_day[row["date"]].append(row["target_t3_net_excess_pct"])
        means = [statistics.mean(v) for _, v in sorted(by_day.items())]
        ordered = sorted(means)
        return {"selected_rows": len(group), "signal_dates": len(means),
                "date_balanced_mean_net_excess_pct": statistics.mean(means) if means else None,
                "positive_label_fraction": sum(r["target_t3_net_excess_pct"] > 0 for r in group) / len(group) if group else None,
                "p05_daily_label_pct": ordered[math.floor(.05 * (len(ordered) - 1))] if ordered else None,
                "unfilled_selected_rows": sum(r.get("execution_state") == "unfilled_cash_zero" for r in group)}

    by_year, by_setup = defaultdict(list), defaultdict(list)
    for row in selected:
        by_year[row["date"][:4]].append(row)
        by_setup[row["setup"]].append(row)
    cost = {}
    for bps in (10, 20, 40):
        # Unfilled signals retain zero exposure and never pay hypothetical costs.
        stressed = [{**r, "target_t3_net_excess_pct": r["target_t3_net_excess_pct"] -
                    ((bps - r["round_trip_cost_bps_assumption"]) / 100
                     if r.get("execution_state") == "filled_daily_proxy" else 0)} for r in selected]
        cost[str(bps)] = describe(stressed)
    secondary = {}
    for horizon in (1, 3, 5):
        available = [{**r, "target_t3_net_excess_pct": r["secondary_net_excess_pct"][str(horizon)]}
                     for r in selected if str(horizon) in r.get("secondary_net_excess_pct", {})]
        secondary[str(horizon)] = describe(available)
    return {"overall": describe(selected), "by_year": {k: describe(v) for k, v in sorted(by_year.items())},
            "by_setup": {k: describe(v) for k, v in sorted(by_setup.items())},
            "round_trip_cost_bps_sensitivity": cost, "secondary_horizons_sessions": secondary,
            "secondary_horizons_used_for_selection": False,
            "measurement": "date_balanced_overlapping_labels_not_portfolio_pnl_or_trade_win_rate"}


def review(data, policy, fitter=fit, minimum_sessions=720, scope="pilot"):
    rows = validate(data, scope=scope)
    cutoff = policy["previously_reviewed_start_date"]
    forward = policy["prospective_start_date"]
    date.fromisoformat(cutoff)
    date.fromisoformat(forward)
    if cutoff >= forward or policy.get("mode") != "development_only_prior_holdout_excluded":
        raise ValueError("expanded_review_requires_explicit_inspected_period_exclusion")
    if any(r["date"] >= forward for r in rows):
        raise ValueError("forward_dates_must_be_sealed_from_retrospective_review")
    # Both the feature and every label must finish before the previously read period.
    development = [r for r in rows if r["date"] < cutoff and r["label_end_date"] < cutoff]
    dates = sorted({r["date"] for r in development})
    base = {"evaluation_mode": policy["mode"], "previously_reviewed_start_date": cutoff,
            "previously_reviewed_rows_excluded": len(rows) - len(development),
            "prospective_start_date": forward, "prospective_status": "not_yet_evaluated",
            "locked_holdout_start": None, "final_holdout": None,
            "production_activation": False, "probabilities_enabled": False,
            "development_feature_dates": len(dates), "development_rows": len(development),
            "feature_dates": len({r["date"] for r in rows}), "training_rows": len(rows)}
    if len(dates) < minimum_sessions:
        return {**base, "status": "blocked_insufficient_qualified_history", "model_status": "not_trained",
                "required_sessions": minimum_sessions}
    folds, validation, out_of_fold = [], defaultdict(list), {k: ([], []) for k in MODELS}
    # The last partial fold is retained; every test is later than its training and validation.
    for t in range(451, len(dates), 63):
        train, valid = split(development, dates, t)
        test_dates = set(dates[t:t + 63])
        test = [r for r in development if r["date"] in test_dates]
        if not train or not valid or not test:
            continue
        result = {}
        for kind in MODELS:
            model = fitter(kind, train, valid)
            validation[kind].extend(daily_results(valid, predictions(model, valid)))
            scores = predictions(model, test)
            out_of_fold[kind][0].extend(test)
            out_of_fold[kind][1].extend(scores)
            result[kind] = summarize(daily_results(test, scores))
        folds.append({"train_start": train[0]["date"], "validation_start": valid[0]["date"],
                      "test_start": dates[t], "test_end": test[-1]["date"],
                      "train_rows": len(train), "validation_rows": len(valid), "test_rows": len(test),
                      "models": result})
    if not folds:
        return {**base, "status": "blocked_no_usable_rolling_folds", "model_status": "not_trained"}
    quality = {k: summarize(v)["paired_early_rule_improvement_pct"] for k, v in validation.items()}
    chosen = "lightgbm" if quality["lightgbm"] > quality["ridge"] + .02 else "ridge"
    train, valid = split(development, dates, len(dates) - 1)
    model = fitter(chosen, train, valid)
    comparison = {k: {"rolling_test": summarize(daily_results(*out_of_fold[k])),
                       "diagnostics": diagnostic_table(*out_of_fold[k])} for k in MODELS}
    selected_days = daily_results(*out_of_fold[chosen])
    improvement = [d["paired_improvement_pct"] for d in selected_days]
    interval = block_interval(improvement)
    average = comparison[chosen]["rolling_test"]["date_balanced_mean_net_excess_pct"]
    reasons = ["retrospective_development_review_is_not_independent_final_test",
               "point_in_time_st_limits_and_benchmark_audits_incomplete",
               "prospective_outcomes_not_evaluated"]
    if average is None or average <= 0:
        reasons.append("cost_adjusted_mean_excess_not_positive")
    if interval is None or interval[0] <= 0:
        reasons.append("improvement_over_early_rule_not_established")
    return {**base, "schema_version": "2.0", "status": "expanded_pilot_review_not_production_qualified",
            "model_status": "trained_pilot_only", "dataset_scope": scope, "selected_model": chosen,
            "selection_basis": "pre_inspected_period_validation_only_fixed_0.02pct_simple_model_margin",
            "validation_comparison": quality, "rolling_folds": folds, "development_comparison": comparison,
            "model": model, "out_of_fold_daily_results": {k: daily_results(*out_of_fold[k]) for k in MODELS},
            "deployment_decision": "retain_existing_early_rules", "nonpromotion_reasons": reasons,
            "uncertainty_basis": "moving_blocks_of_5_observed_signal_dates_not_independent_trades",
            "required_next_evidence": ["full_market_point_in_time_universe_including_later_listings",
                                      "historical_st_status_and_official_price_limit_evidence",
                                      "corporate_action_event_and_official_benchmark_tieout",
                                      "fixed_forward_predictions_and_executable_portfolio_replay"]}
