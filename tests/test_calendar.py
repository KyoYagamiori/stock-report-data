from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.calendar import resolve_calendar


TIMEZONE = ZoneInfo("Asia/Shanghai")


class FakeAkshare:
    @staticmethod
    def tool_trade_date_hist_sina() -> pd.DataFrame:
        return pd.DataFrame(
            {
                "trade_date": pd.to_datetime(
                    ["2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20"]
                )
            }
        )


class CalendarTests(unittest.TestCase):
    def test_preopen_latest_completed_day_is_previous_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            moment = datetime(2026, 7, 16, 8, 40, tzinfo=TIMEZONE)
            info = resolve_calendar(moment, Path(temp_dir), FakeAkshare)
            self.assertTrue(info.is_trading_day)
            self.assertEqual("2026-07-15", info.latest_completed_trading_day)
            self.assertTrue(info.valid)

    def test_after_close_current_day_is_completed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            moment = datetime(2026, 7, 16, 15, 20, tzinfo=TIMEZONE)
            info = resolve_calendar(moment, Path(temp_dir), FakeAkshare)
            self.assertEqual("2026-07-16", info.latest_completed_trading_day)

    def test_weekend_uses_calendar_not_weekday_guess(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            moment = datetime(2026, 7, 18, 9, 0, tzinfo=TIMEZONE)
            info = resolve_calendar(moment, Path(temp_dir), FakeAkshare)
            self.assertFalse(info.is_trading_day)
            self.assertEqual("2026-07-17", info.latest_completed_trading_day)
            self.assertEqual("2026-07-20", info.next_trading_day)


if __name__ == "__main__":
    unittest.main()
