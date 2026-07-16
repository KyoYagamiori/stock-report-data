from __future__ import annotations

import unittest

from pipeline.schedule import SCHEDULES, resolve_schedule


class ScheduleTests(unittest.TestCase):
    def test_all_approved_schedule_nodes_are_present(self) -> None:
        self.assertEqual(17, len(SCHEDULES))
        planned = {params.planned_at for params in SCHEDULES.values()}
        self.assertEqual(
            {
                "08:40",
                "08:55",
                "09:35",
                "10:05",
                "10:35",
                "11:05",
                "11:35",
                "12:05",
                "12:25",
                "13:05",
                "13:35",
                "14:05",
                "14:35",
                "15:05",
                "15:20",
                "20:35",
                "20:50",
            },
            planned,
        )

    def test_daily_non_trading_nodes_use_daily_cron(self) -> None:
        self.assertEqual("early", SCHEDULES["40 0 * * *"].snapshot_type)
        self.assertEqual("noon", SCHEDULES["5 4 * * *"].snapshot_type)
        self.assertEqual("evening", SCHEDULES["35 12 * * *"].snapshot_type)

    def test_manual_parameters_are_validated(self) -> None:
        params = resolve_schedule(
            "workflow_dispatch",
            manual={
                "snapshot_type": "close",
                "mode": "full",
                "planned_at": "15:20",
                "attempt_role": "manual-repair",
                "report_date": "2026-07-16",
            },
        )
        self.assertEqual("2026-07-16", params.report_date)
        with self.assertRaises(ValueError):
            resolve_schedule(
                "workflow_dispatch",
                manual={"snapshot_type": "wrong", "mode": "full", "planned_at": "15:20"},
            )

    def test_unknown_schedule_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_schedule("schedule", "0 0 * * *")


if __name__ == "__main__":
    unittest.main()
