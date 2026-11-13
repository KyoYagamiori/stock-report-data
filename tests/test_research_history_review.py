from copy import deepcopy
import unittest

from research_system.early_model import FEATURES, fit, predictions
from research_system.history_review import diagnostic_table, review
from research_system.history_source import select_cohort
from tests.test_research_early_model import early_dataset


def review_data(n=950):
    data = early_dataset(n)
    data["metadata"].update(scope="pilot", universe_basis="fixed_historical_origin_cohort",
        benchmark_basis="provider_index_not_independently_verified",
        corporate_actions_basis="causal_preclose_chain_raw_execution_retained",
        entry_policy="simulated_next_session_open_no_wait",
        execution_limits_basis="conservative_daily_proxy_not_official_limit_tape")
    for row in data["rows"]:
        row.update(execution_state="filled_daily_proxy", round_trip_cost_bps_assumption=20,
                   secondary_net_excess_pct={str(h): row["target_t3_net_excess_pct"] for h in (1, 3, 5)})
    dates = sorted({r["date"] for r in data["rows"]})
    policy = {"mode": "development_only_prior_holdout_excluded",
              "previously_reviewed_start_date": dates[820], "prospective_start_date": "2030-01-01"}
    return data, policy


def ridge_only(kind, train, valid):
    return fit("ridge", train, valid)


class ExpandedReviewTests(unittest.TestCase):
    def test_model_persists_vcp_feature_order_for_prediction(self):
        rows = early_dataset(80)["rows"]
        for i, row in enumerate(rows):
            row["features"]["vcp_setup"] = i % 2
        model = fit("ridge", rows[:120], rows[120:], feature_names=FEATURES+("vcp_setup",))
        self.assertEqual("vcp_setup", model["features"][-1])
        self.assertEqual(10, len(predictions(model, rows[:10])))

    def test_inspected_period_cannot_change_model_selection_scalers_or_diagnostics(self):
        data, policy = review_data()
        first = review(data, policy, fitter=ridge_only)
        changed = deepcopy(data)
        for row in changed["rows"]:
            if row["date"] >= policy["previously_reviewed_start_date"]:
                row["features"]["alpha101_101"] += 99999
                row["target_t3_net_excess_pct"] -= 777
        second = review(changed, policy, fitter=ridge_only)
        for key in ("model", "selected_model", "development_comparison", "rolling_folds", "validation_comparison"):
            self.assertEqual(first[key], second[key], key)
        self.assertIsNone(second["final_holdout"])
        self.assertGreater(second["previously_reviewed_rows_excluded"], 0)
        self.assertFalse(second["production_activation"])

    def test_every_fit_and_validation_label_finishes_before_review_boundary(self):
        data, policy = review_data()
        called = []
        def check(kind, train, valid):
            called.append(kind)
            for row in train + valid:
                self.assertLess(row["label_end_date"], policy["previously_reviewed_start_date"])
            self.assertLess(max(r["label_end_date"] for r in train), min(r["date"] for r in valid))
            return ridge_only(kind, train, valid)
        result = review(data, policy, fitter=check)
        self.assertTrue(called)
        self.assertEqual("trained_pilot_only", result["model_status"])
        self.assertEqual("retain_existing_early_rules", result["deployment_decision"])

    def test_inspected_dates_cannot_supply_minimum_training_span(self):
        data, policy = review_data()
        policy["previously_reviewed_start_date"] = sorted({r["date"] for r in data["rows"]})[600]
        result = review(data, policy, fitter=ridge_only)
        self.assertEqual("not_trained", result["model_status"])
        self.assertLess(result["development_feature_dates"], 720)

    def test_new_forward_dates_are_sealed_and_not_described_as_another_holdout(self):
        data, policy = review_data()
        policy["prospective_start_date"] = data["rows"][-1]["date"]
        with self.assertRaisesRegex(ValueError, "forward_dates_must_be_sealed"):
            review(data, policy, fitter=ridge_only)

    def test_cost_stress_never_charges_unfilled_signals(self):
        data, _ = review_data()
        rows = data["rows"][:1]
        rows[0].update(execution_state="unfilled_cash_zero", target_t3_net_excess_pct=0)
        table = diagnostic_table(rows, [1])
        for case in table["round_trip_cost_bps_sensitivity"].values():
            self.assertEqual(0, case["date_balanced_mean_net_excess_pct"])
        rows[0].update(execution_state="filled_daily_proxy", target_t3_net_excess_pct=1)
        table = diagnostic_table(rows, [1])
        cases = table["round_trip_cost_bps_sensitivity"]
        self.assertAlmostEqual(1.1, cases["10"]["date_balanced_mean_net_excess_pct"])
        self.assertAlmostEqual(.8, cases["40"]["date_balanced_mean_net_excess_pct"])
        self.assertFalse(table["secondary_horizons_used_for_selection"])

    def test_expanded_cohort_contains_original_prefix_without_survivor_replacement(self):
        members = [{"code": f"sh.{600000 + i}"} for i in range(300)]
        old = select_cohort(members, 32, "fixed")
        new = select_cohort(list(reversed(members)), 256, "fixed")
        self.assertEqual(old, new[:32])
        with self.assertRaises(ValueError): select_cohort(members, 513, "fixed")


if __name__ == "__main__":
    unittest.main()
