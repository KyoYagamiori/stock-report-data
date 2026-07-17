from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.adapters import AdapterResult
from pipeline.adapters.point_in_time import recover_fixed_point_in_time


TIMEZONE = ZoneInfo("Asia/Shanghai")


class FakeAk:
    def stock_zh_a_minute(self, symbol: str, period: str, adjust: str) -> pd.DataFrame:
        del symbol, period, adjust
        return pd.DataFrame(
            [
                {"day": "2026-07-15 15:00:00", "open": 9.8, "high": 9.9, "low": 9.7, "close": 9.8, "volume": 90, "amount": 900},
                {"day": "2026-07-16 15:00:00", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 100, "amount": 1000},
                {"day": "2026-07-17 09:30:00", "open": 10.5, "high": 10.6, "low": 10.4, "close": 10.5, "volume": 100, "amount": 1000},
                {"day": "2026-07-17 11:30:00", "open": 10.5, "high": 11.1, "low": 10.5, "close": 11.0, "volume": 200, "amount": 2200},
                {"day": "2026-07-17 14:30:00", "open": 11.0, "high": 11.0, "low": 8.0, "close": 8.0, "volume": 300, "amount": 2400},
            ]
        )

    def stock_zh_a_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str,
    ) -> pd.DataFrame:
        del symbol, start_date, end_date, adjust
        dates = pd.bdate_range(end="2026-07-17", periods=70)
        return pd.DataFrame(
            {
                "date": dates,
                "open": [9.8] * len(dates),
                "high": [10.2] * len(dates),
                "low": [9.7] * len(dates),
                "close": [10.0] * len(dates),
                "volume": [1000.0] * len(dates),
                "amount": [10000.0] * len(dates),
                "outstanding_share": [100000.0] * len(dates),
                "turnover": [0.01] * len(dates),
            }
        )


class PointInTimeRecoveryTests(unittest.TestCase):
    def test_noon_recovery_uses_1130_and_never_afternoon_quote(self) -> None:
        moment = datetime(2026, 7, 17, 14, 32, tzinfo=TIMEZONE)
        stock_result = AdapterResult(
            status="success",
            source="late-live",
            data={
                "stocks": [
                    {
                        "code": "600584",
                        "name": "长电科技",
                        "pool": "core",
                        "valid_quote": True,
                        "quote_time": "2026-07-17T14:30:00+08:00",
                        "latest_price": 8.0,
                        "warnings": [],
                        "errors": [],
                    }
                ]
            },
            started_at=moment,
            finished_at=moment,
            records_expected=1,
            records_valid=1,
        )
        market_result = AdapterResult(
            status="success",
            source="late-market",
            data={},
            started_at=moment,
            finished_at=moment,
        )

        recovered_stocks, recovered_market = recover_fixed_point_in_time(
            stock_result,
            market_result,
            "trading_noon",
            "2026-07-17",
            "2026-07-17",
            moment,
            ak_module=FakeAk(),
        )

        stock = recovered_stocks.data["stocks"][0]
        self.assertEqual(11.0, stock["latest_price"])
        self.assertAlmostEqual(10.0, stock["pct_change"])
        self.assertEqual(3200.0, stock["amount"])
        self.assertEqual("2026-07-17T11:30:00+08:00", stock["quote_time"])
        self.assertTrue(stock["point_in_time_recovered"])
        self.assertIsNotNone(stock["ma5"])
        self.assertEqual(3, len(recovered_market.data["indices"]))
        self.assertTrue(recovered_market.data["turnover_valid"])
        self.assertEqual({}, recovered_market.data["breadth"])
        self.assertEqual([], recovered_market.data["sectors_top"])

    def test_early_recovery_uses_previous_completed_close(self) -> None:
        moment = datetime(2026, 7, 17, 11, 50, tzinfo=TIMEZONE)
        stock_result = AdapterResult(
            status="partial",
            source="late-live",
            data={"stocks": [{"code": "600584", "name": "长电科技", "pool": "core", "valid_quote": False, "warnings": [], "errors": []}]},
            started_at=moment,
            finished_at=moment,
        )
        market_result = AdapterResult(
            status="partial",
            source="late-market",
            data={},
            started_at=moment,
            finished_at=moment,
        )
        recovered_stocks, _ = recover_fixed_point_in_time(
            stock_result,
            market_result,
            "trading_preopen",
            "2026-07-17",
            "2026-07-16",
            moment,
            ak_module=FakeAk(),
        )
        stock = recovered_stocks.data["stocks"][0]
        self.assertEqual(10.0, stock["latest_price"])
        self.assertAlmostEqual((10 / 9.8 - 1) * 100, stock["pct_change"])
        self.assertEqual("2026-07-16T15:00:00+08:00", stock["quote_time"])


if __name__ == "__main__":
    unittest.main()
