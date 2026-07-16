from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.adapters.market_overview import collect_market_overview
from pipeline.adapters.stock_quotes import collect_stock_quotes


TIMEZONE = ZoneInfo("Asia/Shanghai")


class FakeMarketAkshare:
    @staticmethod
    def stock_zh_index_spot_sina() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "symbol": ["sh000001", "sz399001", "sz399006"],
                "name": ["上证指数", "深证成指", "创业板指"],
                "trade": [4000.0, 13000.0, 3200.0],
                "change": [0.5, 0.8, 1.1],
                "ticktime": ["11:30:00", "11:30:00", "11:30:00"],
            }
        )

    @staticmethod
    def stock_zh_index_spot_em() -> pd.DataFrame:
        return pd.DataFrame()

    @staticmethod
    def stock_board_industry_name_em() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "板块名称": [f"行业{i}" for i in range(1, 7)],
                "涨跌幅": [6, 5, 4, -1, -2, -3],
            }
        )

    @staticmethod
    def stock_board_concept_name_em() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "板块名称": [f"概念{i}" for i in range(1, 7)],
                "涨跌幅": [3.5, 2.5, 1.5, -3.5, -4.5, -5.5],
            }
        )

    @staticmethod
    def stock_board_industry_summary_ths() -> pd.DataFrame:
        return pd.DataFrame()


class FakeFallbackMarketAkshare(FakeMarketAkshare):
    @staticmethod
    def stock_board_industry_name_em() -> pd.DataFrame:
        raise ConnectionError("Eastmoney unavailable")

    @staticmethod
    def stock_board_concept_name_em() -> pd.DataFrame:
        raise ConnectionError("Eastmoney unavailable")

    @staticmethod
    def stock_board_industry_summary_ths() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "板块": [f"同花顺行业{i}" for i in range(1, 11)],
                "涨跌幅": [5, 4, 3, 2, 1, -1, -2, -3, -4, -5],
            }
        )


class MarketOverviewTests(unittest.TestCase):
    def test_market_overview_builds_required_groups(self) -> None:
        spot = pd.DataFrame(
            {
                "代码": ["600001", "300001", "600002", "600003"],
                "名称": ["甲", "乙", "丙", "丁"],
                "涨跌幅": [10.0, -20.0, 1.0, 0.0],
                "成交额": [100.0, 200.0, 300.0, 400.0],
            }
        )
        result = collect_market_overview(
            spot,
            "fixture spot",
            datetime(2026, 7, 16, 11, 35, tzinfo=TIMEZONE),
            FakeMarketAkshare,
        )
        self.assertEqual("success", result.status)
        self.assertEqual(3, len(result.data["indices"]))
        self.assertEqual(1000.0, result.data["total_turnover"])
        self.assertEqual(1, result.data["breadth"]["limit_up"])
        self.assertEqual(1, result.data["breadth"]["limit_down"])
        self.assertEqual(5, len(result.data["sectors_top"]))
        self.assertEqual(5, len(result.data["sectors_bottom"]))

    def test_ths_industry_ranking_replaces_failed_eastmoney_boards(self) -> None:
        spot = pd.DataFrame(
            {
                "代码": ["600001", "600002"],
                "名称": ["甲", "乙"],
                "涨跌幅": [1.0, -1.0],
                "成交额": [100.0, 200.0],
            }
        )
        result = collect_market_overview(
            spot,
            "fixture spot",
            datetime(2026, 7, 16, 15, 20, tzinfo=TIMEZONE),
            FakeFallbackMarketAkshare,
        )
        self.assertEqual("success", result.status)
        self.assertEqual("同花顺行业1", result.data["sectors_top"][0]["name"])
        self.assertEqual("同花顺行业10", result.data["sectors_bottom"][0]["name"])
        self.assertIn("stock_board_industry_summary_ths", result.data["sector_source"])


class StockQuoteAdapterTests(unittest.TestCase):
    def test_missing_configured_codes_are_preserved_as_invalid_rows(self) -> None:
        payload = {
            "stocks": [
                {
                    "code": "600584",
                    "name": "长电科技",
                    "latest_trade_date": "2026-07-16",
                    "today_close": 100.0,
                    "today_pct_change": 1.0,
                    "today_amount": 1000000.0,
                    "today_turnover_rate": 2.0,
                    "realtime_quote_available": True,
                    "realtime_quote_date": "2026-07-16",
                    "realtime_quote_time": "11:30:02",
                    "warnings": [],
                    "errors": [],
                }
            ],
            "warnings": [],
            "errors": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "pipeline.adapters.stock_quotes.legacy.fetch_realtime_spot",
                return_value=(pd.DataFrame(), "fixture", []),
            ), patch(
                "pipeline.adapters.stock_quotes.legacy.collect_snapshot_payload",
                return_value=payload,
            ):
                result, _ = collect_stock_quotes(
                    Path(temp_dir),
                    datetime(2026, 7, 16, 11, 35, tzinfo=TIMEZONE),
                    "2026-07-16",
                    "full",
                )
        self.assertEqual(25, len(result.data["stocks"]))
        longi = next(item for item in result.data["stocks"] if item["code"] == "600584")
        self.assertTrue(longi["valid_quote"])
        missing = next(item for item in result.data["stocks"] if item["code"] == "002396")
        self.assertFalse(missing["valid_quote"])


if __name__ == "__main__":
    unittest.main()
