from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.catchup import catch_up_noon
from pipeline.calendar import CalendarInfo
from pipeline.publisher import publish_snapshot
from pipeline.runner import RunResult
from tests.helpers import valid_snapshot


TIMEZONE = ZoneInfo("Asia/Shanghai")


def trading_calendar(moment, root):
    del root
    return CalendarInfo(moment.date().isoformat(), True, "2026-07-15", "2026-07-17", "test", True)


class CatchupTests(unittest.TestCase):
    def test_first_late_workflow_requests_missing_noon_cycle(self) -> None:
        calls = []

        def runner(options, root):
            calls.append((options, root))
            return RunResult("B", True, "published", "noon-id", root / "health.json")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = catch_up_noon(
                root,
                datetime(2026, 7, 17, 11, 50, tzinfo=TIMEZONE),
                runner=runner,
                calendar_resolver=trading_calendar,
            )
            self.assertIsNotNone(result)
            self.assertEqual("noon", calls[0][0].snapshot_type)
            self.assertEqual("11:35", calls[0][0].planned_at)
            self.assertEqual("automatic-delayed-catchup", calls[0][0].attempt_role)

    def test_ready_same_day_noon_is_not_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot = valid_snapshot()
            snapshot["quality_grade"] = "B"
            calendar = trading_calendar(datetime(2026, 7, 16, tzinfo=TIMEZONE), root).as_manifest()
            publish_snapshot(snapshot, root, calendar)
            result = catch_up_noon(
                root,
                datetime(2026, 7, 16, 14, 0, tzinfo=TIMEZONE),
                runner=lambda *_: self.fail("runner should not be called"),
                calendar_resolver=trading_calendar,
            )
            self.assertIsNone(result)

    def test_corrupt_same_day_snapshot_is_recovered(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            now = datetime(2026, 7, 16, 14, 0, tzinfo=TIMEZONE)
            publication = publish_snapshot(valid_snapshot(), root, trading_calendar(now, root).as_manifest())
            publication.archive_path.write_text("corrupt")
            calls = []
            def runner(options, folder):
                calls.append(options)
                return RunResult("B", True, "published", "recovered", folder / "health.json")
            result = catch_up_noon(root, now, runner, trading_calendar)
            self.assertTrue(result.published)
            self.assertEqual("noon", calls[0].snapshot_type)

    def test_holiday_and_pre_noon_do_not_request_recovery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runner = lambda *_: self.fail("no recovery should be requested")
            self.assertIsNone(catch_up_noon(root, datetime(2026, 7, 16, 10, tzinfo=TIMEZONE), runner,
                                          lambda *_: self.fail("calendar is unnecessary before noon")))
            holiday = lambda moment, _: CalendarInfo(moment.date().isoformat(), False, "2026-07-17",
                                                    "2026-07-20", "test", True)
            self.assertIsNone(catch_up_noon(root, datetime(2026, 7, 18, 14, tzinfo=TIMEZONE), runner, holiday))

    def test_unverified_calendar_is_rejected(self):
        from pipeline.contracts import ContractError
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid = lambda moment, _: CalendarInfo(moment.date().isoformat(), True, "2026-07-15",
                                                    "2026-07-17", "weekday-fallback-unverified", False)
            with self.assertRaises(ContractError):
                catch_up_noon(Path(temp_dir), datetime(2026, 7, 16, 14, tzinfo=TIMEZONE),
                              lambda *_: self.fail("unverified calendar cannot recover"), invalid)

    def test_cli_reports_failed_recovery_as_nonzero_exit(self):
        import argparse
        import contextlib
        import io
        from unittest.mock import patch
        from pipeline.catchup import main
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            failure = RunResult("F", False, "quality gate failed", "failed", root / "health.json")
            with patch("pipeline.catchup.parse_args", return_value=argparse.Namespace(root=str(root))), \
                 patch("pipeline.catchup.catch_up_noon", return_value=failure), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    main()
            self.assertEqual(1, result.exception.code)


if __name__ == "__main__":
    unittest.main()
