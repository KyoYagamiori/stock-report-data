from copy import deepcopy
from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from research_system.vcp_training import (FEATURES, build_stock, daily_comparison, fit_model,
    predict, summarize_days, temporal_split, train)


def fixtures():
    config = json.loads((Path(__file__).resolve().parents[1] / "config/vcp_training.json").read_bytes())
    calendar = [(date(2018, 1, 2) + timedelta(days=i)).isoformat() for i in range(220)]
    raw = [{"date": d, "code": "sh.600001", "open": 10, "high": 11, "low": 9, "close": 10,
        "volume": 1e7, "amount": 1e8, "preclose": 10, "adjustflag": "3", "tradestatus": "1", "isST": "unknown"}
        for d in calendar]
    manifest = {"config": {"history_start": calendar[0], "history_end": "2030-01-01", "cohort_date": calendar[0]},
        "stocks": {"sh.600001": {"sha256": "a" * 64}}}
    source = {"rows": raw + [{**raw[-1], "date": "2030-01-01", "close": 9999}],
        "request": {"method": "query_history_k_data_plus", "kwargs": {"code": "sh.600001", "start_date": calendar[0],
            "end_date": "2030-01-01", "frequency": "d", "adjustflag": "3"}}}
    point = {"mid_slope_5d_atr": .2, "return_5d_pct": 1., "return_20d_pct": 2., "atr20": 1.,
        "close": 10., "mid": 9.8, "width_percentile": .2, "volume_ratio_complete": .5}
    observation = {"available": True, "matched": True, "stage": "preparing", "origin": calendar[150],
        "contraction_count": 3, "contraction_ratio": .5, "dry_volume_ratio": .5,
        "distance_to_pivot_atr": .5, "tight5_range_pct": 3., "risk_from_pivot_pct": 4.}
    return config, calendar, raw, manifest, source, point, observation


class VcpTrainingTests(unittest.TestCase):
    def test_independent_candidate_origin_is_not_boll_filtered_or_repeated(self):
        config, calendar, raw, manifest, source, point, observation = fixtures()
        observed_days = []
        def observe(bars):
            observed_days.append(bars[-1]["day"])
            self.assertTrue(all(b["day"] < config["exclude_reviewed_from"] for b in bars))
            return observation
        benchmark = {d: {"open": 10, "close": 10} for d in calendar}
        with patch("research_system.vcp_training.context", return_value=(manifest, calendar, benchmark)), \
                patch("research_system.vcp_training.read_capture", return_value=source), \
                patch("research_system.vcp_training.points_for", return_value=[point] * len(raw)), \
                patch("research_system.vcp_training.vcp.analyze", side_effect=observe):
            result = build_stock(("/tmp", config, "sh.600001"))
        self.assertEqual(1, len(result["rows"]))
        self.assertEqual(calendar[159], result["rows"][0]["date"])
        self.assertEqual(set(FEATURES), set(result["rows"][0]["features"]))
        self.assertGreater(result["counts"]["repeated_origin_suppressed"], 0)
        self.assertLess(max(observed_days), config["exclude_reviewed_from"])
        self.assertNotIn("setup", result["rows"][0])

    def test_censored_first_observation_never_becomes_a_later_success(self):
        config, calendar, raw, manifest, source, point, observation = fixtures()
        with patch("research_system.vcp_training.context", return_value=(manifest, calendar, {})), \
                patch("research_system.vcp_training.read_capture", return_value=source), \
                patch("research_system.vcp_training.points_for", return_value=[point] * len(raw)), \
                patch("research_system.vcp_training.vcp.analyze", return_value=observation), \
                patch("research_system.vcp_training.labels", return_value=(None, {"state": "censored_exit"})) as label:
            result = build_stock(("/tmp", config, "sh.600001"))
        self.assertEqual([], result["rows"])
        self.assertEqual(1, label.call_count)

    def test_calendar_split_purges_actual_label_end(self):
        config, calendar, *_ = fixtures()
        config.update(training_sessions=100, validation_sessions=30, purge_sessions=5)
        rows = [{"date": calendar[80], "label_end_date": calendar[150]},
            {"date": calendar[81], "label_end_date": calendar[82]},
            {"date": calendar[150], "label_end_date": calendar[180]},
            {"date": calendar[151], "label_end_date": calendar[152]}]
        a, b = temporal_split(rows, calendar, 180, config)
        self.assertEqual([rows[1]], a)
        self.assertEqual([rows[3]], b)

    def test_reviewed_period_and_duplicate_origins_are_rejected(self):
        config, calendar, *_ = fixtures()
        row = {"date": config["exclude_reviewed_from"], "label_end_date": config["exclude_reviewed_from"]}
        with self.assertRaisesRegex(ValueError, "reviewed_period_leakage"):
            train([row], calendar, config)
        row.update(date=calendar[0], label_end_date=calendar[5], code="600001", origin=calendar[0])
        with self.assertRaisesRegex(ValueError, "duplicate_origin"):
            train([row, deepcopy(row)], calendar, config)

    def test_same_pool_rule_comparison_and_empty_result_have_no_win_rate(self):
        rows = [{"date": "2020-01-02", "code": code, "stage": "preparing",
            "features": {"vcp_pivot_distance_atr": distance}, "targets_provider_benchmark_net_proxy_pct": {"3": value}}
            for code, distance, value in [("600001", .1, -1), ("600002", .3, 2)]]
        days = daily_comparison(rows, [0, 1], 3)
        self.assertEqual(3, days[0]["model_minus_rule_proxy_pct"])
        self.assertNotIn("win_rate", summarize_days(days, ["2020-01-02"]))
        self.assertIsNone(summarize_days([], [])['paired_model_minus_rule_proxy_pct'])

    @unittest.skipUnless(importlib.util.find_spec("lightgbm"), "optional model dependency")
    def test_actual_models_learn_separate_horizons_and_serialize_feature_order(self):
        config, *_ = fixtures()
        rows = [{"features": {f: float(i % 7) for f in FEATURES},
            "targets_provider_benchmark_net_proxy_pct": {"1": .25, "3": .5, "5": 1.5}} for i in range(120)]
        for kind in ("ridge", "lightgbm"):
            a = fit_model(kind, rows[:100], rows[100:], 1, config)
            b = fit_model(kind, rows[:100], rows[100:], 5, config)
            self.assertAlmostEqual(.25, predict(json.loads(json.dumps(a)), rows[:1])[0])
            self.assertAlmostEqual(1.5, predict(b, rows[:1])[0])
            b["features"] = list(reversed(FEATURES))
            with self.assertRaisesRegex(ValueError, "feature_order_changed"):
                predict(b, rows[:1])


if __name__ == "__main__":
    unittest.main()
