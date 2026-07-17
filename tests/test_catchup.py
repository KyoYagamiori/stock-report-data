from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.catchup import catch_up_noon
from pipeline.runner import RunResult


TIMEZONE = ZoneInfo("Asia/Shanghai")


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
            )
            self.assertIsNotNone(result)
            self.assertEqual("noon", calls[0][0].snapshot_type)
            self.assertEqual("11:35", calls[0][0].planned_at)
            self.assertEqual("automatic-delayed-catchup", calls[0][0].attempt_role)

    def test_ready_same_day_noon_is_not_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "output/latest/manifest.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "snapshots": {
                            "noon": {
                                "report_cycle": "2026-07-17-noon",
                                "quality_grade": "B",
                                "selected_file": "output/archive/noon.json",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            result = catch_up_noon(
                root,
                datetime(2026, 7, 17, 14, 0, tzinfo=TIMEZONE),
                runner=lambda *_: self.fail("runner should not be called"),
            )
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
