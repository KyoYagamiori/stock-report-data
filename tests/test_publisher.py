from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from pipeline.contracts import ContractError, sha256_file
from pipeline.publisher import publish_snapshot, should_publish_fixed, should_publish_intraday, verify_pointer
from tests.helpers import coverage, valid_snapshot


def calendar() -> dict[str, object]:
    return {
        "date": "2026-07-16",
        "is_trading_day": True,
        "latest_completed_trading_day": "2026-07-15",
        "next_trading_day": "2026-07-17",
        "source": "test-calendar",
    }


class PublisherComparatorTests(unittest.TestCase):
    def test_fixed_same_cycle_a_is_not_replaced_by_b(self) -> None:
        current = valid_snapshot()
        candidate = deepcopy(current)
        candidate["quality_grade"] = "B"
        candidate["published_at"] = "2026-07-16T12:25:00+08:00"
        self.assertFalse(should_publish_fixed(candidate, current))

    def test_fixed_new_cycle_b_replaces_old_cycle_a(self) -> None:
        current = valid_snapshot()
        current["report_date"] = "2026-07-15"
        current["report_cycle"] = "2026-07-15-noon"
        current["market_date"] = "2026-07-15"
        candidate = valid_snapshot()
        candidate["quality_grade"] = "B"
        self.assertTrue(should_publish_fixed(candidate, current))

    def test_fixed_rejects_cross_type_candidate(self) -> None:
        current = valid_snapshot()
        candidate = valid_snapshot()
        candidate["snapshot_type"] = "early"
        self.assertFalse(should_publish_fixed(candidate, current))

    def test_intraday_newer_b_replaces_older_a(self) -> None:
        current = valid_snapshot()
        current.update({"snapshot_type": "intraday", "quality_grade": "A"})
        current["quote_time_max"] = "2026-07-16T10:05:00+08:00"
        candidate = deepcopy(current)
        candidate["quality_grade"] = "B"
        candidate["quote_time_max"] = "2026-07-16T10:35:00+08:00"
        self.assertTrue(should_publish_intraday(candidate, current))

    def test_intraday_never_publishes_f(self) -> None:
        candidate = valid_snapshot()
        candidate.update({"snapshot_type": "intraday", "quality_grade": "F"})
        self.assertFalse(should_publish_intraday(candidate, None))


class PublisherIntegrationTests(unittest.TestCase):
    def test_publish_creates_archive_latest_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot = valid_snapshot()
            result = publish_snapshot(snapshot, root, calendar())
            self.assertTrue(result.published)
            self.assertTrue(result.archive_path.exists())
            latest = root / "output/latest/noon/report_data_compact.json"
            self.assertTrue(latest.exists())
            self.assertTrue(latest.with_suffix(".md").exists())
            self.assertTrue(result.archive_path.with_suffix(".md").exists())
            self.assertTrue((root / "output/latest/report_data.json").exists())
            self.assertTrue((root / "output/latest/report_data.md").exists())
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(result.manifest_path.with_suffix(".md").exists())
            pointer = manifest["snapshots"]["noon"]
            self.assertEqual(snapshot["snapshot_id"], pointer["selected_snapshot_id"])
            self.assertEqual(sha256_file(result.archive_path), pointer["sha256"])
            verify_pointer(root, pointer)

    def test_same_cycle_b_is_archived_but_does_not_replace_a(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            grade_a = valid_snapshot()
            self.assertTrue(publish_snapshot(grade_a, root, calendar()).published)

            grade_b = deepcopy(grade_a)
            grade_b["snapshot_id"] = "20260716-1225-noon-full-run456"
            grade_b["workflow_run_id"] = "run456"
            grade_b["quality_grade"] = "B"
            grade_b["published_at"] = "2026-07-16T12:25:00+08:00"
            grade_b["coverage"]["core"] = coverage(7, 10)
            result = publish_snapshot(grade_b, root, calendar())
            self.assertFalse(result.published)
            self.assertTrue(result.archive_path.exists())
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(grade_a["snapshot_id"], manifest["snapshots"]["noon"]["selected_snapshot_id"])

    def test_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = publish_snapshot(valid_snapshot(), root, calendar())
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            pointer = manifest["snapshots"]["noon"]
            pointer["sha256"] = "0" * 64
            with self.assertRaises(ContractError):
                verify_pointer(root, pointer)


if __name__ == "__main__":
    unittest.main()
