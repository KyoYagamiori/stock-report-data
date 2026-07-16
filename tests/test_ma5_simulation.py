from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ma5_system.simulation import record_simulation_day, simulation_status


class MA5SimulationTests(unittest.TestCase):
    def test_duplicate_scan_is_not_counted_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            screen = {
                "report_date": "2026-07-17",
                "phase": "close",
                "scan_id": "2026-07-17-close-test",
                "quality": {"grade": "A", "actionable": False},
                "market_environment": {"score": 70, "maximum_position_pct": 100},
                "primary_candidate": None,
            }
            record_simulation_day(screen, root)
            record_simulation_day(screen, root)
            status = simulation_status(root)
            self.assertEqual(1, status["trading_days_recorded"])
            self.assertEqual(1.0, status["grade_a_close_rate"])

    def test_preclose_timing_and_close_survival_are_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            card = {"code": "600001", "score": 90, "buy_zone_low": 9.9, "buy_zone_high": 10.1, "hard_invalidation": 9.5, "box_top": 11.0, "ma5": 10.0}
            base = {
                "report_date": "2026-07-17",
                "market_environment": {"score": 75, "maximum_position_pct": 100},
                "quality": {"grade": "A", "actionable": True, "universe_coverage": 0.98, "history_coverage": 0.97, "industry_coverage": 0.96},
                "primary_candidate": card,
                "top10": [card],
            }
            record_simulation_day(
                {**base, "phase": "preclose", "scan_id": "preclose-1", "completed_at": "2026-07-17T14:50:00+08:00"},
                root,
            )
            record_simulation_day(
                {
                    **base,
                    "phase": "close",
                    "scan_id": "close-1",
                    "completed_at": "2026-07-17T15:20:00+08:00",
                    "quality": {**base["quality"], "actionable": False},
                },
                root,
            )
            status = simulation_status(root)
            self.assertEqual(1.0, status["preclose_on_time_rate"])
            self.assertEqual(1.0, status["preclose_coverage_pass_rate"])
            self.assertEqual(1.0, status["preclose_candidate_close_survival_rate"])


if __name__ == "__main__":
    unittest.main()
