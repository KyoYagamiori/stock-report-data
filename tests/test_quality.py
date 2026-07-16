from __future__ import annotations

import unittest

from pipeline.quality import evaluate_quality
from tests.helpers import coverage, valid_snapshot


class QualityTests(unittest.TestCase):
    def test_noon_full_dataset_is_grade_a(self) -> None:
        result = evaluate_quality(valid_snapshot(), "trading_noon")
        self.assertEqual("A", result.grade)

    def test_noon_seven_of_ten_core_is_grade_b(self) -> None:
        payload = valid_snapshot()
        payload["coverage"]["core"] = coverage(7, 10)
        payload["coverage"]["indices"] = coverage(2, 3)
        payload["coverage"]["market_breadth"] = coverage(0, 5)
        payload["coverage"]["sectors_top"] = coverage(3, 5)
        payload["coverage"]["sectors_bottom"] = coverage(3, 5)
        payload["market"] = {"turnover_valid": True, "breadth_valid": False}
        result = evaluate_quality(payload, "trading_noon")
        self.assertEqual("B", result.grade)

    def test_close_delayed_source_time_and_missing_sectors_is_grade_b(self) -> None:
        snapshot = valid_snapshot()
        snapshot.update(
            {
                "snapshot_type": "close",
                "quality_profile": "trading_close",
                "report_cycle": "2026-07-16-close",
                "snapshot_id": "20260716-1520-close-full-run123",
                "market_session": "market_close",
                "quote_time_min": "2026-07-16T15:34:58+08:00",
                "quote_time_max": "2026-07-16T15:34:59+08:00",
                "suitable_reports": ["evening"],
            }
        )
        snapshot["coverage"]["sectors_top"] = coverage(0, 5)
        snapshot["coverage"]["sectors_bottom"] = coverage(0, 5)
        result = evaluate_quality(snapshot, "trading_close")
        self.assertEqual("B", result.grade)
        self.assertIn("cap capital_consistency_score at 60", result.degradation_actions)

    def test_noon_old_quote_is_grade_f(self) -> None:
        payload = valid_snapshot()
        payload["quote_time_max"] = "2026-07-16T10:30:00+08:00"
        result = evaluate_quality(payload, "trading_noon")
        self.assertEqual("F", result.grade)
        self.assertTrue(any("quote window" in reason for reason in result.blocking_reasons))

    def test_preopen_previous_close_is_not_grade_f(self) -> None:
        payload = valid_snapshot()
        payload.update(
            {
                "snapshot_id": "20260716-0840-early-full-run123",
                "snapshot_type": "early",
                "quality_profile": "trading_preopen",
                "report_cycle": "2026-07-16-early",
                "market_date": "2026-07-15",
                "market_session": "preopen",
                "quote_time_min": "2026-07-15T15:00:00+08:00",
                "quote_time_max": "2026-07-15T15:00:05+08:00",
                "realtime_expected": False,
                "realtime_available": False,
                "suitable_reports": ["early"],
            }
        )
        payload["market"] = {
            "latest_completed_trading_day": "2026-07-15",
            "turnover_valid": True,
            "breadth_valid": False,
        }
        result = evaluate_quality(payload, "trading_preopen")
        self.assertEqual("A", result.grade)

    def test_preopen_does_not_require_current_day_realtime(self) -> None:
        payload = valid_snapshot()
        payload.update(
            {
                "snapshot_id": "20260716-0840-early-full-run123",
                "snapshot_type": "early",
                "quality_profile": "trading_preopen",
                "report_cycle": "2026-07-16-early",
                "market_date": "2026-07-15",
                "market_session": "preopen",
                "realtime_expected": False,
                "realtime_available": False,
            }
        )
        payload["market"] = {"latest_completed_trading_day": "2026-07-15"}
        payload["coverage"]["core"] = coverage(7, 10)
        payload["coverage"]["indices"] = coverage(2, 3)
        result = evaluate_quality(payload, "trading_preopen")
        self.assertEqual("B", result.grade)

    def test_evening_can_use_verified_same_day_close(self) -> None:
        payload = valid_snapshot()
        payload.update(
            {
                "snapshot_id": "20260716-2035-evening-full-run123",
                "snapshot_type": "evening",
                "quality_profile": "trading_evening",
                "report_cycle": "2026-07-16-evening",
                "market_session": "evening_verified",
                "quote_time_min": "2026-07-16T15:00:00+08:00",
                "quote_time_max": "2026-07-16T15:00:05+08:00",
                "realtime_expected": False,
                "based_on_snapshot_id": "20260716-1520-close-full-run100",
                "suitable_reports": ["evening"],
            }
        )
        payload["validation"]["base_snapshot_valid"] = True
        payload["market"] = {"base_close_grade": "A"}
        result = evaluate_quality(payload, "trading_evening")
        self.assertEqual("A", result.grade)

    def test_evening_without_verified_close_is_grade_f(self) -> None:
        payload = valid_snapshot()
        payload.update(
            {
                "snapshot_type": "evening",
                "quality_profile": "trading_evening",
                "report_cycle": "2026-07-16-evening",
                "market_session": "evening_verified",
                "quote_time_max": "2026-07-16T15:00:05+08:00",
                "realtime_expected": False,
                "based_on_snapshot_id": None,
            }
        )
        result = evaluate_quality(payload, "trading_evening")
        self.assertEqual("F", result.grade)

    def test_non_trading_missing_realtime_is_not_failure(self) -> None:
        payload = valid_snapshot()
        payload.update(
            {
                "quality_profile": "non_trading",
                "market_date": "2026-07-17",
                "report_date": "2026-07-18",
                "report_cycle": "2026-07-18-noon",
                "market_session": "non_trading",
                "realtime_expected": False,
                "realtime_available": False,
                "quote_time_max": "2026-07-17T15:00:05+08:00",
            }
        )
        payload["market"] = {"latest_completed_trading_day": "2026-07-17"}
        payload["coverage"]["core"] = coverage(0, 10)
        result = evaluate_quality(payload, "non_trading")
        self.assertEqual("B", result.grade)


if __name__ == "__main__":
    unittest.main()
