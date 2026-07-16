from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from ma5_system.config import load_strategy_config
from ma5_system.data import apply_industry_map, is_st_name, normalize_spot_frame


TIMEZONE = ZoneInfo("Asia/Shanghai")


class MA5DataTests(unittest.TestCase):
    def test_normalize_spot_filters_bse_stays_in_supported_boards(self) -> None:
        frame = pd.DataFrame(
            [
                {"代码": "600001", "名称": "Alpha", "最新价": 10, "涨跌幅": 1, "今开": 9.9, "最高": 10.1, "最低": 9.8, "成交量": 100, "成交额": 200_000_000, "换手率": 2, "时间": "14:45:01"},
                {"代码": "830001", "名称": "BSE", "最新价": 12, "涨跌幅": 2, "成交量": 100, "成交额": 20_000_000, "时间": "14:45:01"},
            ]
        )
        result = normalize_spot_frame(frame, datetime(2026, 7, 17, 14, 45, tzinfo=TIMEZONE), load_strategy_config())
        self.assertEqual(["600001"], result["code"].tolist())
        self.assertEqual("sh_main", result.iloc[0]["board"])
        self.assertTrue(result.iloc[0]["valid_quote"])
        self.assertEqual("2026-07-17T14:45:01+08:00", result.iloc[0]["quote_time"])

    def test_st_detection_does_not_match_ordinary_english_name(self) -> None:
        self.assertTrue(is_st_name("*ST测试"))
        self.assertTrue(is_st_name("ST测试"))
        self.assertFalse(is_st_name("Stock Alpha"))

    def test_nan_industry_uses_the_verified_mapping(self) -> None:
        spot = pd.DataFrame([{"code": "600001", "industry": float("nan")}])
        result = apply_industry_map(spot, {"600001": "半导体"})
        self.assertEqual("半导体", result.iloc[0]["industry"])


if __name__ == "__main__":
    unittest.main()
