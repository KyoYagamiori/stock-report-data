from __future__ import annotations

import unittest

from pipeline.schedule import SCHEDULES, resolve_schedule


class ScheduleTests(unittest.TestCase):
    def test_all_approved_schedule_nodes_are_present(self) -> None:
        self.assertEqual(8, len(SCHEDULES))
        planned = {params.planned_at for params in SCHEDULES.values()}
        self.assertEqual(
            {
                "08:17",
                "08:43",
                "11:37",
                "12:07",
                "14:35",
                "15:20",
                "20:17",
                "20:41",
            },
            planned,
        )

    def test_daily_non_trading_nodes_use_daily_cron(self) -> None:
        self.assertEqual("early", SCHEDULES["17 0 * * 1-5"].snapshot_type)
        self.assertEqual("noon", SCHEDULES["7 4 * * 1-5"].snapshot_type)
        self.assertEqual("evening", SCHEDULES["17 12 * * *"].snapshot_type)

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
