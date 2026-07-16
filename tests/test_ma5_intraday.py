from __future__ import annotations

import unittest

import pandas as pd

from ma5_system.intraday import apply_intraday_metrics, normalize_intraday_frame


class MA5IntradayTests(unittest.TestCase):
    def test_vwap_and_tail_high_raise_confirmation_level(self) -> None:
        frame = pd.DataFrame(
            [
                {"时间": "2026-07-17 14:30:00", "收盘": 10.00, "最高": 10.05, "成交量": 100},
                {"时间": "2026-07-17 14:35:00", "收盘": 10.05, "最高": 10.10, "成交量": 200},
                {"时间": "2026-07-17 14:40:00", "收盘": 10.08, "最高": 10.12, "成交量": 200},
                {"时间": "2026-07-17 14:45:00", "收盘": 10.15, "最高": 10.16, "成交量": 300},
            ]
        )
        metrics = normalize_intraday_frame(frame)
        self.assertIsNotNone(metrics)
        updated = apply_intraday_metrics({"latest": 10.15, "confirmation_price": 10.02}, metrics)
        self.assertEqual(10.12, updated["confirmation_price"])
        self.assertTrue(updated["confirmation_met"])


if __name__ == "__main__":
    unittest.main()
