from copy import deepcopy
from datetime import date, timedelta
import unittest

from research_system.model import FEATURES, eligible_train, experiment, fit_ridge, predict, validate_dataset


def dataset(count=730):
    days, day = [], date(2020, 1, 2)
    while len(days) < count + 6:
        if day.weekday() < 5: days.append(day.isoformat())
        day += timedelta(days=1)
    rows = []
    for i, d in enumerate(days[:count]):
        for code, scale in (("600000", 1), ("600001", 2)):
            features = {f: ((i % (7 + j)) + scale) / (j + 1) for j, f in enumerate(FEATURES)}
            rows.append({"date": d, "code": code, "features": features,
                "target_t3_net_excess_pct": features[FEATURES[0]] * .1 - .2,
                "signal_available_at": d + "T16:00:00+08:00", "features_known_at": d + "T15:30:00+08:00",
                "label_end_date": days[i + 3], "label_known_at": days[i + 3] + "T16:00:00+08:00",
                "source_sha256": "a" * 64, "baseline_v1_eligible": True, "baseline_v1_score": scale})
    return {"metadata": {"asof": days[-1] + "T21:00:00+08:00", "universe_basis": "historical_point_in_time",
        "benchmark_basis": "verified_official", "corporate_actions_basis": "asof_adjusted_and_execution_prices_retained",
        "primary_horizon_sessions": 3, "costs_in_target": True}, "rows": rows}


class ExperimentalModelTests(unittest.TestCase):
    def test_current_universe_or_unadjusted_history_cannot_pass(self):
        for key, value in (("universe_basis", "current_survivors"), ("corporate_actions_basis", "raw_unreviewed")):
            data = dataset(30)
            data["metadata"][key] = value
            with self.assertRaises(ValueError): validate_dataset(data)

    def test_unknown_features_or_future_knowledge_cannot_pass(self):
        for kind in ("future", "missing", "duplicate"):
            data = dataset(30)
            if kind == "future": data["rows"][0]["features_known_at"] = "2029-01-01T15:00:00+08:00"
            elif kind == "missing": del data["rows"][0]["features"][FEATURES[0]]
            else: data["rows"].append(deepcopy(data["rows"][0]))
            with self.assertRaises(ValueError): validate_dataset(data)

    def test_160_bar_feature_window_is_not_a_valid_history_backtest(self):
        result = experiment(dataset(160))
        self.assertEqual("blocked_insufficient_history", result["status"])
        self.assertFalse(result["production_activation"])

    def test_purge_respects_actual_long_halted_label_end(self):
        rows = [{"date": "2026-01-01", "label_end_date": "2026-03-01"},
                {"date": "2026-01-02", "label_end_date": "2026-01-05"}]
        self.assertEqual([rows[1]], eligible_train(rows, {r["date"] for r in rows}, "2026-02-01"))

    def test_final_holdout_does_not_change_fit_or_training_scaler(self):
        data = dataset()
        baseline = experiment(data)
        self.assertTrue(baseline["rolling_folds"])
        self.assertFalse(baseline["production_activation"])
        self.assertFalse(baseline["probabilities_enabled"])
        changed = deepcopy(data)
        for row in changed["rows"]:
            if row["date"] >= baseline["locked_holdout_start"]:
                row["features"][FEATURES[0]] += 100000
                row["target_t3_net_excess_pct"] += 500
        second = experiment(changed)
        self.assertEqual(baseline["model"], second["model"])


if __name__ == "__main__":
    unittest.main()
