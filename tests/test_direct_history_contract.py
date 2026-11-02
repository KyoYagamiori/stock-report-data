import unittest
from unittest.mock import patch
import pandas as pd

from pipeline.adapters.direct_quotes import daily_indicators


class DirectHistoryTests(unittest.TestCase):
    def frame(self, count, end="2026-11-02"):
        return pd.DataFrame({"日期": pd.date_range(end=end, periods=count),
                             "open": [10.0] * count, "最高": [11.0] * count, "最低": [9.0] * count,
                             "收盘": [10.0] * count, "volume": [1000.0] * count})

    def test_intraday_live_bar_is_excluded_before_exact_160_calculation(self):
        with patch("pipeline.adapters.direct_quotes.fetch_daily_frame", return_value=self.frame(161)):
            out = daily_indicators("600000", "2026-11-02", "2026-11-02T11:30:00+08:00")
        self.assertEqual(160, out["indicator_history_rows"])
        self.assertEqual("ready", out["indicator_status"])
        self.assertEqual("2026-11-01", out["indicator_asof"])

    def test_provider_60_rows_cannot_claim_160_bar_indicators(self):
        with patch("pipeline.adapters.direct_quotes.fetch_daily_frame", return_value=self.frame(60)):
            out = daily_indicators("600000", "2026-11-02", "2026-11-02T11:30:00+08:00")
        self.assertEqual("insufficient_history", out["indicator_status"])
        self.assertEqual(59, out["indicator_history_rows"])
        self.assertNotIn("kdj_j", out)

    def test_completed_close_uses_last160_of_larger_frame(self):
        with patch("pipeline.adapters.direct_quotes.fetch_daily_frame", return_value=self.frame(180)):
            out = daily_indicators("600000", "2026-11-02", "2026-11-02T15:00:00+08:00")
        self.assertEqual(160, out["indicator_history_rows"])
        self.assertEqual("2026-11-02", out["indicator_asof"])
