from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ma5_system.publisher import publish_screen, verify_manifest_pointer


def screen() -> dict:
    return {
        "schema_version": "1.0.0",
        "strategy_id": "ma5_concentrated_v1",
        "scan_id": "2026-07-17-preclose-144500-test",
        "phase": "preclose",
        "report_date": "2026-07-17",
        "market_date": "2026-07-17",
        "planned_at": "2026-07-17T14:45:00+08:00",
        "started_at": "2026-07-17T14:45:00+08:00",
        "completed_at": "2026-07-17T14:49:00+08:00",
        "quality": {"grade": "A", "report_readiness": "ready_a", "actionable": True, "universe_coverage": 1, "history_coverage": 1, "industry_coverage": 1, "quote_age_minutes": 4, "top10_complete": True, "reasons": []},
        "market_environment": {"score": 75, "regime": "strong", "maximum_position_pct": 100, "components": {}},
        "directions": [],
        "top10": [],
        "primary_candidate": None,
        "cash_required": True,
        "close_confirmation_checks": [],
        "signal_shards": [],
    }


class MA5PublisherTests(unittest.TestCase):
    def test_manifest_points_to_immutable_hash_verified_screen(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = publish_screen(screen(), [{"code": "600001", "name": "A"}], root)
            self.assertIn("output\\ma5\\archive", str(result.archive_file))
            loaded = verify_manifest_pointer(root, "preclose")
            self.assertEqual(screen()["scan_id"], loaded["scan_id"])
            manifest = json.loads(result.manifest_file.read_text(encoding="utf-8"))
            self.assertEqual("ready_a", manifest["report_readiness"]["preclose"]["status"])
            pointer = manifest["scans"]["preclose"]
            self.assertEqual(75, pointer["market_score"])
            self.assertIn("top10", pointer)
            self.assertEqual(1, pointer["signal_shards"][0]["count"])
            result.archive_file.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_manifest_pointer(root, "preclose")

    def test_late_non_actionable_retry_cannot_replace_actionable_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = publish_screen(screen(), [], root)
            retry = screen()
            retry["scan_id"] = "2026-07-17-preclose-145300-test"
            retry["completed_at"] = "2026-07-17T14:53:00+08:00"
            retry["quality"] = {**retry["quality"], "actionable": False, "next_day_reference_only": True}
            second = publish_screen(retry, [], root)
            self.assertTrue(first.selected)
            self.assertFalse(second.selected)
            selected = verify_manifest_pointer(root, "preclose")
            self.assertEqual(first.archive_file.parent.name, selected["scan_id"])

    def test_signal_shard_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = publish_screen(screen(), [{"code": "600001", "name": "A"}], root)
            manifest = json.loads(result.manifest_file.read_text(encoding="utf-8"))
            shard = root / manifest["scans"]["preclose"]["signal_shards"][0]["file"]
            shard.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_manifest_pointer(root, "preclose")


if __name__ == "__main__":
    unittest.main()
