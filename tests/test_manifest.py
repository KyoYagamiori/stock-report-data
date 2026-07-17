from __future__ import annotations

import unittest

from pipeline.manifest import update_report_readiness
from tests.helpers import valid_manifest


class ManifestReadinessTests(unittest.TestCase):
    def test_prior_day_pointer_is_not_ready_for_new_calendar_date(self) -> None:
        manifest = valid_manifest()
        manifest["calendar"]["date"] = "2026-07-17"

        update_report_readiness(manifest)

        readiness = manifest["report_readiness"]["noon"]
        self.assertEqual("not_ready", readiness["status"])
        self.assertIsNone(readiness["selected_snapshot_id"])
        self.assertIn("stale report cycle", readiness["reasons"][0])

    def test_same_day_pointer_remains_ready(self) -> None:
        manifest = valid_manifest()

        update_report_readiness(manifest)

        self.assertEqual("ready_a", manifest["report_readiness"]["noon"]["status"])


if __name__ == "__main__":
    unittest.main()
