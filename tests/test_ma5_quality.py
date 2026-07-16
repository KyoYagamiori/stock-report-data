from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from ma5_system.config import load_strategy_config
from ma5_system.quality import REQUIRED_CARD_FIELDS, assess_quality


TIMEZONE = ZoneInfo("Asia/Shanghai")


class MA5QualityTests(unittest.TestCase):
    def test_action_requires_grade_a_and_arrival_before_1452(self) -> None:
        card = {field: 1 for field in REQUIRED_CARD_FIELDS}
        card.update({"minute_vwap": 1, "local_tail_high": 1, "minute_quote_time": "2026-07-17 14:45:00", "intraday_data_complete": True, "event_data_complete": True, "daily_history_refreshed": True})
        result = assess_quality(5000, 5000, 5000, 5000, "2026-07-17T14:45:00+08:00", [card], "preclose", datetime(2026, 7, 17, 14, 49, tzinfo=TIMEZONE), load_strategy_config())
        self.assertEqual("A", result["grade"])
        self.assertTrue(result["actionable"])
        late = assess_quality(5000, 5000, 5000, 5000, "2026-07-17T14:50:00+08:00", [card], "preclose", datetime(2026, 7, 17, 14, 53, tzinfo=TIMEZONE), load_strategy_config())
        self.assertFalse(late["actionable"])
        self.assertTrue(late["next_day_reference_only"])

    def test_unverified_calendar_blocks_action(self) -> None:
        card = {field: 1 for field in REQUIRED_CARD_FIELDS}
        card.update({"minute_vwap": 1, "local_tail_high": 1, "minute_quote_time": "2026-07-17 14:45:00", "intraday_data_complete": True, "event_data_complete": True, "daily_history_refreshed": True})
        result = assess_quality(
            5000,
            5000,
            5000,
            5000,
            "2026-07-17T14:45:00+08:00",
            [card],
            "preclose",
            datetime(2026, 7, 17, 14, 49, tzinfo=TIMEZONE),
            load_strategy_config(),
            calendar_valid=False,
        )
        self.assertEqual("F", result["grade"])
        self.assertFalse(result["actionable"])


if __name__ == "__main__":
    unittest.main()
