from copy import deepcopy
import unittest

from market_screen.technicals import calculate, rank_candidate
from market_screen.research import build_shadow, context_for, evaluate_record, percentile
from tests.test_boll_runner import CONFIG, history, stock, TARGET


def record(code="600000", industry=None):
    indicators = calculate(history()["bars"], TARGET)
    return {**stock(code, industry=industry), "market_date": TARGET, "status": "screened", "source": {},
            "indicators": indicators, "ranking": rank_candidate(stock(code), indicators, CONFIG)}


class ShadowFeatureTests(unittest.TestCase):
    def test_atr_and_reference_window_are_exact_and_use_only_past_bars(self):
        row = record()
        f = row["indicators"]["research_features"]
        self.assertAlmostEqual(.4, f["atr20"])
        self.assertEqual(120, f["bandwidth_reference_count"])
        self.assertGreaterEqual(f["bandwidth_percentile_120"], 0)
        self.assertLessEqual(f["bandwidth_percentile_120"], 1)
        bars = history()["bars"]
        future = {**bars[-1], "day": "2099-01-01", "close": 2000, "high": 2001}
        self.assertEqual(calculate(bars, TARGET), calculate(bars + [future], TARGET))

    def test_percentile_ties_do_not_make_flat_width_extremely_low(self):
        self.assertEqual(.5, percentile(1, [1] * 120))

    def test_raw_basis_and_unknown_industry_are_not_marked_verified(self):
        row = record()
        result = evaluate_record(row, context_for([row]), CONFIG)
        self.assertIn("corporate_action_window_requires_source_review", result["evidence_gaps"])
        self.assertIn("dated_industry_reference_unavailable", result["evidence_gaps"])
        self.assertIsNone(result["relative_strength"]["industry_5d_pct"])

    def test_breakout_can_pass_with_lower_rail_down_but_never_becomes_buy_signal(self):
        row = record()
        row["indicators"].update(rails_up=False, opening_up=True)
        f = row["indicators"]["research_features"]
        f.update(recent_squeeze_120=True, breakout_prior20=True, pullback_reclaimed=False)
        result = evaluate_record(row, context_for([row]), CONFIG)
        self.assertIn("squeeze_breakout", result["setups"])
        self.assertTrue(result["structure_eligible"])
        self.assertEqual("review_required", result["entry_status"])

    def test_known_price_basis_change_cannot_be_offset_by_good_features(self):
        row = record()
        row["source"]["corporate_action_basis_change"] = True
        result = evaluate_record(row, context_for([row]), CONFIG)
        self.assertFalse(result["structure_eligible"])
        self.assertIn("corporate_action_price_basis_review_required", result["rejection_reasons"])

    def test_market_reference_and_industry_reference_are_separate(self):
        rows = [record("60000" + str(i), "制造") for i in range(4)]
        for i, row in enumerate(rows):
            row["indicators"]["research_features"]["return_5d_pct"] = i
        context = context_for(rows)
        result = evaluate_record(rows[-1], context, CONFIG)
        self.assertEqual(1.5, result["relative_strength"]["market_5d_pct"])
        self.assertEqual(1.5, result["relative_strength"]["industry_5d_pct"])
        self.assertIn("proxy_not_official_index", context["market_reference"])

    def test_noon_volume_never_compares_with_full_previous_day(self):
        row = record()
        context = context_for([row])
        q = {"close": row["indicators"]["price"], "prev_close": row["indicators"]["price"], "volume": 100}
        first = evaluate_record(row, context, CONFIG, q, "noon")
        self.assertIsNone(first["volume_vs_previous_full_morning"])
        self.assertIn("previous_full_morning_volume_unavailable", first["evidence_gaps"])
        second = evaluate_record(row, context, CONFIG, q, "noon", {"volume": 50})
        self.assertEqual(2, second["volume_vs_previous_full_morning"])

    def test_shadow_pools_deduplicate_and_production_rank_is_unchanged(self):
        row = record()
        baseline = deepcopy(row["ranking"])
        row["indicators"]["research_features"].update(reclaimed_mid=True, pullback_reclaimed=True)
        result = build_shadow([row], {"phase": "close", "market_date": TARGET, "report_date": TARGET}, CONFIG)
        self.assertEqual(baseline, row["ranking"])
        self.assertEqual(1, result["deduplicated_candidate_count"])
        self.assertEqual(0, result["entry_qualified_count"])
        self.assertEqual("shadow", result["mode"])


if __name__ == "__main__":
    unittest.main()
