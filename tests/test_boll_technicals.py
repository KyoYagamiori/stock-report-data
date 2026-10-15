from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import math
import statistics
import unittest

from market_screen.technicals import calculate, normalize_bars, rank_candidate


CONFIG = {
    "minimum_history_bars": 160,
    "maximum_extension_above_upper_pct": 3,
    "minimum_estimated_turnover_20d_median_cny": 50_000_000,
}


def bars_for(prices, *, volume=1_000_000, amount=None):
    result, day = [], date(2025, 1, 2)
    for price in prices:
        while day.weekday() > 4:
            day += timedelta(days=1)
        row = {"day": day.isoformat(), "open": price, "high": price + .5,
               "low": price - .5, "close": price, "volume": volume}
        if amount is not None:
            row["amount"] = amount
        result.append(row)
        day += timedelta(days=1)
    return result


class CompletedHistoryTests(unittest.TestCase):
    def test_future_bars_do_not_change_target_indicators(self):
        bars = bars_for([100 + i * .1 for i in range(161)])
        target = bars[-2]["day"]
        baseline = calculate(bars[:-1], target)
        with_future = calculate(bars, target)
        self.assertEqual(baseline, with_future)
        self.assertEqual(target, with_future["bar_date"])
        self.assertEqual(160, with_future["bar_count"])

    def test_duplicate_days_are_rejected_before_ranking(self):
        bars = bars_for([10, 11])
        bars.append(deepcopy(bars[-1]))
        with self.assertRaisesRegex(ValueError, "duplicate_daily_date"):
            normalize_bars(bars, bars[-1]["day"])

    def test_negative_nonfinite_missing_or_bad_range_bars_are_rejected(self):
        baseline = bars_for([10])[0]
        invalid = [(field, value) for field in ("open", "high", "low", "close")
                   for value in (-1, 0, math.nan, math.inf)]
        invalid += [("volume", -1), ("volume", math.nan), ("volume", math.inf),
                    ("amount", -1), ("amount", math.nan), ("amount", math.inf),
                    ("high", 9), ("low", 11)]
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                row = {**baseline, field: value}
                with self.assertRaises(ValueError):
                    normalize_bars([row], row["day"])
        row = deepcopy(baseline)
        del row["close"]
        with self.assertRaises((KeyError, ValueError)):
            normalize_bars([row], row["day"])

    def test_sorting_and_zero_activity_preserve_observations(self):
        bars = bars_for([10, 11, 12], volume=0)
        rows = normalize_bars(list(reversed(bars)), bars[-1]["day"])
        self.assertEqual([row["day"] for row in bars], [row["day"] for row in rows])
        self.assertTrue(all(row["volume"] == 0 for row in rows))

    def test_stale_history_is_disclosed_and_cannot_rank(self):
        bars = bars_for([100 + i * .1 for i in range(160)])
        target = (date.fromisoformat(bars[-1]["day"]) + timedelta(days=3)).isoformat()
        indicators = calculate(bars, target)
        result = rank_candidate({"name": "测试公司"}, indicators, CONFIG)
        self.assertFalse(indicators["history_current"])
        self.assertFalse(result["eligible"])
        self.assertIn("history_not_current", result["reasons"])


class IndicatorArithmeticTests(unittest.TestCase):
    def test_boll_known_1_to_20_sample_uses_population_variance(self):
        bars = bars_for(list(range(1, 21)))
        indicators = calculate(bars, bars[-1]["day"])
        boll = indicators["boll"]
        self.assertAlmostEqual(10.5, boll["mid"], places=12)
        self.assertAlmostEqual(22.032562594670797, boll["upper"], places=12)
        self.assertAlmostEqual(-1.0325625946707966, boll["lower"], places=12)
        self.assertAlmostEqual(4 * math.sqrt(33.25) / 10.5, boll["width"], places=12)
        self.assertEqual(0, indicators["parameters"]["boll"]["ddof"])

    def test_less_than_20_bars_has_no_boll_setup(self):
        bars = bars_for([10] * 19)
        indicators = calculate(bars, bars[-1]["day"])
        self.assertIsNone(indicators["boll"])
        self.assertEqual([], indicators["patterns"])

    def test_kdj_seed_and_first_full_nine_bar_rsv(self):
        bars = bars_for([10] * 8 + [12])
        for row in bars[:8]:
            row.update(high=12, low=8)
        bars[-1].update(high=13, low=11)
        seed = calculate(bars[:8], bars[7]["day"])
        self.assertEqual({"k": 50.0, "d": 50.0, "j": 50.0}, seed["kdj"])
        latest = calculate(bars, bars[-1]["day"])["kdj"]
        # Ninth RSV = (12 - 8) / (13 - 8) * 100 = 80.
        self.assertAlmostEqual(60, latest["k"], places=12)
        self.assertAlmostEqual(160 / 3, latest["d"], places=12)
        self.assertAlmostEqual(220 / 3, latest["j"], places=12)

    def test_macd_first_price_seed_and_double_histogram(self):
        bars = bars_for([10, 12])
        initial = calculate(bars[:1], bars[0]["day"])["macd"]
        self.assertEqual({"dif": 0.0, "dea": 0.0, "hist2": 0.0}, initial)
        latest = calculate(bars, bars[-1]["day"])["macd"]
        expected_dif = 2 * (2 / 13 - 2 / 27)
        self.assertAlmostEqual(expected_dif, latest["dif"], places=12)
        self.assertAlmostEqual(expected_dif * .2, latest["dea"], places=12)
        self.assertAlmostEqual(2 * expected_dif * .8, latest["hist2"], places=12)

    def test_flat_bars_keep_neutral_kdj_and_zero_width(self):
        bars = bars_for([10] * 160)
        for row in bars:
            row.update(high=10, low=10)
        indicators = calculate(bars, bars[-1]["day"])
        self.assertEqual({"k": 50.0, "d": 50.0, "j": 50.0}, indicators["kdj"])
        self.assertEqual(0, indicators["boll"]["width"])
        self.assertEqual(.5, indicators["band_position"])
        result = rank_candidate({"name": "测试公司"}, indicators, CONFIG)
        self.assertFalse(result["eligible"])
        self.assertIn("one_price_bar", result["reasons"])

    def test_one_below_mid_day_differs_from_two_completed_days(self):
        one = bars_for([100 + i * .1 for i in range(159)] + [111])
        two = bars_for([100 + i * .1 for i in range(158)] + [112, 111])
        single = calculate(one, one[-1]["day"])
        double = calculate(two, two[-1]["day"])
        self.assertFalse(single["below_mid_last_two"])
        self.assertTrue(double["below_mid_last_two"])
        result = rank_candidate({"name": "测试公司"}, double, CONFIG)
        self.assertFalse(result["eligible"])
        self.assertIn("below_middle_two_completed_sessions", result["reasons"])

    def test_liquidity_is_a_disclosed_close_times_shares_proxy(self):
        bars = bars_for([100 + i * .1 for i in range(160)], amount=1)
        indicators = calculate(bars, bars[-1]["day"])
        expected = statistics.median(row["close"] * row["volume"] for row in bars[-20:])
        self.assertEqual(expected, indicators["estimated_turnover_20d_median"])
        self.assertNotEqual(1, indicators["estimated_turnover_20d_median"])
        self.assertIn("estimate", indicators["turnover_proxy_note"])
        self.assertIn("not exchange-reported", indicators["turnover_proxy_note"])


class CandidateGateTests(unittest.TestCase):
    def test_159_bars_never_rank_even_with_otherwise_good_setup(self):
        bars = bars_for([100 + i * .1 for i in range(159)])
        indicators = calculate(bars, bars[-1]["day"])
        self.assertTrue(indicators["patterns"])
        result = rank_candidate({"name": "测试公司"}, indicators, CONFIG)
        self.assertFalse(result["eligible"])
        self.assertIsNone(result["score"])
        self.assertIn("insufficient_history", result["reasons"])

    def test_160_good_bars_rank_as_research_queue_not_probability(self):
        bars = bars_for([100 + i * .1 for i in range(160)])
        result = rank_candidate({"name": "测试公司"}, calculate(bars, bars[-1]["day"]), CONFIG)
        self.assertTrue(result["eligible"])
        self.assertGreater(result["score"], 0)
        self.assertLessEqual(result["components"]["kdj_macd_max10"], 10)
        self.assertIn("not backtested probability", result["score_meaning"])
        self.assertIn("review_required", result["review_status"])

    def test_risk_name_liquidity_and_no_volume_gates(self):
        bars = bars_for([100 + i * .1 for i in range(160)])
        indicators = calculate(bars, bars[-1]["day"])
        for name in ("*ST测试", "ST 测试", "测试退"):
            with self.subTest(name=name):
                result = rank_candidate({"name": name}, indicators, CONFIG)
                self.assertFalse(result["eligible"])
                self.assertIn("risk_warning_name", result["reasons"])
        thin = deepcopy(indicators)
        thin["estimated_turnover_20d_median"] = 49_999_999
        result = rank_candidate({"name": "测试公司"}, thin, CONFIG)
        self.assertIn("low_liquidity_proxy", result["reasons"])
        no_trades = deepcopy(indicators)
        no_trades["last_bar"]["volume"] = 0
        result = rank_candidate({"name": "测试公司"}, no_trades, CONFIG)
        self.assertIn("no_target_day_volume", result["reasons"])


if __name__ == "__main__":
    unittest.main()
