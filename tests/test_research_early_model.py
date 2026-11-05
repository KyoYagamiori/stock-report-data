from copy import deepcopy
import importlib.util
import unittest

from market_screen.early import POOLS
from research_system.early_model import block_interval, daily_results, experiment, fit, predictions, split, validate
from tests.test_research_model import dataset


def early_dataset(n=730):
    data = dataset(n)
    data["metadata"].update(entry_policy="next_eligible_open_after_publication",
        execution_limits_basis="dated_limits_halts_unfilled_audited")
    for index, r in enumerate(data["rows"]):
        r.update(setup=POOLS[index % 4], execution_audit_sha256="b"*64)
        r["features"].update(signal_age_sessions=index % 2, alpha101_101=.2)
    return data


def ridge_fitter(kind, train, valid):
    return fit("ridge", train, valid)


class EarlyModelTests(unittest.TestCase):
    def test_unverified_execution_and_160_day_history_block_training(self):
        data = early_dataset(160)
        self.assertEqual("not_trained", experiment(data)["model_status"])
        data["metadata"]["execution_limits_basis"] = "ignore_limits"
        with self.assertRaises(ValueError): validate(data)

    def test_missing_extra_feature_and_execution_hash_are_rejected(self):
        for key in ("alpha101_101", "hash"):
            data = early_dataset(20)
            if key == "hash": del data["rows"][0]["execution_audit_sha256"]
            else: del data["rows"][0]["features"][key]
            with self.assertRaises(ValueError): validate(data)

    def test_actual_label_end_is_purged_from_validation(self):
        rows = validate(early_dataset())
        dates = sorted({r["date"] for r in rows})
        rows[900]["label_end_date"] = dates[-1]
        train, valid = split(rows, dates, 451)
        self.assertNotIn(rows[900], train + valid)

    def test_holdout_cannot_change_fit_or_model_selection(self):
        data = early_dataset()
        first = experiment(data, fitter=ridge_fitter)
        changed = deepcopy(data)
        for r in changed["rows"]:
            if r["date"] >= first["locked_holdout_start"]:
                r["features"]["alpha101_101"] += 999
                r["target_t3_net_excess_pct"] += 100
        second = experiment(changed, fitter=ridge_fitter)
        self.assertEqual(first["model"], second["model"])
        self.assertEqual(first["selected_model"], second["selected_model"])
        self.assertFalse(second["production_activation"])

    def test_same_stock_in_two_setup_pools_is_not_duplicated_in_daily_labels(self):
        row = early_dataset(5)["rows"][0]
        duplicate = {**row, "setup": POOLS[1]}
        out = daily_results([row, duplicate], [1., 2.])
        self.assertEqual([row["code"]], out[0]["selected_codes"])

    def test_uncertainty_uses_date_blocks_and_refuses_tiny_sample(self):
        self.assertIsNone(block_interval([1.]*10))
        self.assertEqual([1., 1.], block_interval([1.]*30))

    @unittest.skipUnless(importlib.util.find_spec("lightgbm"), "optional LightGBM dependency")
    def test_native_lightgbm_fit_and_predict_on_synthetic_data(self):
        rows = validate(early_dataset(80))
        model = fit("lightgbm", rows[:100], rows[100:])
        self.assertEqual("lightgbm", model["kind"])
        self.assertEqual(10, len(predictions(model, rows[:10])))


if __name__ == "__main__":
    unittest.main()
