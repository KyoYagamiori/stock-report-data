from __future__ import annotations

import unittest

import pandas as pd

from ma5_system.config import load_strategy_config
from ma5_system.scoring import apply_direction_context, build_technical_record, score_stock


def trending_history(code: str = "600001", periods: int = 70) -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-07-16", periods=periods)
    closes = [10 + index * 0.05 for index in range(periods)]
    records = []
    for index, (day, close) in enumerate(zip(dates, closes)):
        records.append(
            {
                "date": day.date().isoformat(),
                "code": code,
                "name": "Alpha",
                "industry": "Semiconductor",
                "open": close * 0.998,
                "high": close * (1.15 if index == periods - 10 else 1.01),
                "low": close * 0.995,
                "close": close,
                "volume": 10_000_000,
                "amount": 250_000_000,
                "turnover": 3.0,
            }
        )
    return pd.DataFrame(records)


class MA5ScoringTests(unittest.TestCase):
    def test_high_quality_reclaim_can_be_a_plus(self) -> None:
        config = load_strategy_config()
        history = trending_history()
        latest = float(history.iloc[-1]["close"] * 1.004)
        quote = {
            "code": "600001",
            "name": "Alpha",
            "industry": "Semiconductor",
            "latest": latest,
            "pct_change": 1.2,
            "open": latest * 0.995,
            "high": latest * 1.01,
            "low": latest * 0.995,
            "volume": 12_000_000,
            "amount": 300_000_000,
            "turnover": 3.2,
            "valid_quote": True,
            "one_price_limit": False,
            "is_st": False,
            "suspended": False,
            "listing_date": "2020-01-01",
        }
        technical = build_technical_record(quote, history, "2026-07-17", "preclose", config)
        technical.update({"data_grade": "A", "major_data_gap": False, "event_risk": False})
        technical = apply_direction_context(
            technical,
            {"rank": 1, "strength": 8.0, "median_pct_change": 1.2, "positive_ratio": 0.7},
        )
        result = score_stock(technical, 1, config)
        self.assertTrue(result.eligible, result.failures)
        self.assertTrue(result.card["a_plus"], result.card)
        self.assertGreaterEqual(result.card["reward_risk"], 2)

    def test_risk_over_five_percent_is_hard_failure(self) -> None:
        config = load_strategy_config()
        record = {"history_days": 70, "listing_date": "2020-01-01", "market_date": "2026-07-17", "median_amount_20": 200_000_000, "ma5_rising": True, "ma5": 10, "ma10": 9, "ma20": 8, "latest": 10, "distance_to_ma5_pct": 0, "touched_ma5_recently": True, "reclaimed_ma5": True, "planned_risk_pct": 5.1, "pct_change": 1, "amount_ratio_20": 1, "turnover": 2, "data_grade": "A"}
        result = score_stock(record, 1, config)
        self.assertIn("planned_risk_over_5pct", result.failures)
        self.assertFalse(result.card["a_plus"])

    def test_retreating_direction_cannot_be_a_plus(self) -> None:
        config = load_strategy_config()
        history = trending_history()
        latest = float(history.iloc[-1]["close"] * 1.004)
        technical = build_technical_record(
            {
                "code": "600001",
                "name": "Alpha",
                "industry": "Semiconductor",
                "latest": latest,
                "pct_change": 1.2,
                "open": latest * 0.995,
                "high": latest * 1.01,
                "low": latest * 0.995,
                "amount": 300_000_000,
                "turnover": 3.0,
                "listing_date": "2020-01-01",
            },
            history,
            "2026-07-17",
            "preclose",
            config,
        )
        technical.update({"data_grade": "A", "major_data_gap": False})
        technical = apply_direction_context(
            technical,
            {"rank": 1, "strength": 2.0, "median_pct_change": -0.2, "positive_ratio": 0.45},
        )
        result = score_stock(technical, 1, config)
        self.assertFalse(result.card["a_plus"])


if __name__ == "__main__":
    unittest.main()
