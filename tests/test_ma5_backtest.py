from __future__ import annotations

import unittest

import pandas as pd

from ma5_system.backtest import run_backtest


def panel() -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-02", periods=90)
    records = []
    codes = ["600001", "600002", "600003", "000001", "000002", "000003"]
    for code_index, code in enumerate(codes):
        industry = "Leader" if code_index < 3 else "Other"
        for index, day in enumerate(dates):
            growth = 0.04 if industry == "Leader" else 0.005
            close = 10 + index * growth + code_index * 0.01
            records.append(
                {
                    "date": day.date().isoformat(), "code": code, "name": f"Stock {code}", "industry": industry,
                    "open": close * 0.998, "high": close * 1.08, "low": close * 0.995, "close": close,
                    "volume": 10_000_000, "amount": 300_000_000 if industry == "Leader" else 150_000_000, "turnover": 3.0,
                }
            )
    return pd.DataFrame(records)


class MA5BacktestTests(unittest.TestCase):
    def test_close_signal_is_never_bought_on_same_day(self) -> None:
        result = run_backtest(panel())
        buys = [item for item in result["trades"] if item["side"] == "buy"]
        self.assertTrue(result["future_returns"]["signals"])
        self.assertTrue(buys)
        self.assertEqual(0, buys[0]["shares"] % 100)
        first_signal = result["future_returns"]["signals"][0]
        self.assertGreater(buys[0]["date"], first_signal["date"])
        self.assertFalse(result["validation"]["minimum_three_years_met"])
        self.assertIn("out_of_sample_metrics", result["validation"])


if __name__ == "__main__":
    unittest.main()
