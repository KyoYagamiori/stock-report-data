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
        self.assertEqual("2026-07-17T11:30:00+08:00", stock["indicator_asof_time"])
        self.assertFalse(stock["indicator_bar_complete"])
        self.assertEqual("unadjusted", stock["indicator_adjustment"])
        self.assertIsNotNone(stock["ma5"])
        self.assertEqual(3, len(recovered_market.data["indices"]))
        self.assertFalse(recovered_market.data["turnover_valid"])
        self.assertIsNone(stock["volume_change_ratio"])
        self.assertEqual({}, recovered_market.data["breadth"])
        self.assertEqual([], recovered_market.data["sectors_top"])

    def test_parallel_recovery_preserves_order_and_isolates_failures(self):
        from threading import Barrier
        from unittest.mock import patch
        barrier = Barrier(3)
        moment = datetime(2026, 7, 17, 14, 32, tzinfo=TIMEZONE)
        bases = [{"code": code, "warnings": [], "errors": []} for code in ["600584", "688700", "300476"]]
        stocks = AdapterResult(status="partial", source="fixture", data={"stocks": bases}, started_at=moment, finished_at=moment)
        market = AdapterResult(status="partial", source="fixture", data={}, started_at=moment, finished_at=moment)
        def recover(base, *args):
            barrier.wait(timeout=3)
            if base["code"] == "688700":
                raise ConnectionError("fixture outage")
            return {**base, "valid_quote": True}
        with patch("pipeline.adapters.point_in_time._recover_stock", side_effect=recover):
            result, _ = recover_fixed_point_in_time(stocks, market, "trading_noon", "2026-07-17", "2026-07-17", moment, ak_module=FakeAk())
        self.assertEqual([x["code"] for x in bases], [x["code"] for x in result.data["stocks"]])
        self.assertEqual(2, result.records_valid)
        self.assertFalse(result.data["stocks"][1]["valid_quote"])
        self.assertTrue(any("688700" in error for error in result.errors))

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

class IndicatorRegressionTests(unittest.TestCase):
    def test_flat_series_has_zero_macd_and_boll_width(self):
        from scripts.fetch_snapshot import compute_indicators
        frame = pd.DataFrame({'日期': pd.bdate_range('2026-01-01', periods=60), '收盘': [10.]*60, '最高': [10.]*60, '最低': [10.]*60})
        got = compute_indicators(frame, 'fixture', 'unadjusted')
        self.assertEqual('ready', got['indicator_status'])
        self.assertEqual(10., got['boll_upper'])
        self.assertEqual(10., got['boll_lower'])
        self.assertEqual(50., got['kdj_j'])
        self.assertEqual(0., got['macd_hist'])

    def test_daily_outage_preserves_valid_minute_quote(self):
        from pipeline.adapters.point_in_time import _recover_stock
        from datetime import time
        class NoDaily(FakeAk):
            def stock_zh_a_daily(self, **kwargs):
                raise ConnectionError('daily unavailable')
        got = _recover_stock({'code':'688700'}, '2026-07-17', time(11,30), 'trading_noon', NoDaily())
        self.assertEqual(11., got['latest_price'])
        self.assertEqual('missing', got['indicator_status'])
        self.assertIsNone(got['volume_change_ratio'])
