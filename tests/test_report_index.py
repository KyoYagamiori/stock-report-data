from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from report_support.index import sync_index, write_json


def report(day="2026-11-02", label="午报"):
    return f"# {day} {label}\n\n" + "\n\n".join(
        f"## {n}. 标题\n\n第{n}节内容，含公开研究条件。" for n in range(1, 8)) + "\n\n本报告不构成投资建议。\n"


class ReportIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime.fromisoformat("2026-11-02T15:00:00+08:00")

    def body(self, day="2026-11-02", cycle="noon", text=None, suffix=""):
        path = self.root / f"reports/archive/{day.replace('-', '/')}/{cycle}{suffix}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text or report(day, {"noon": "午报", "early": "早报", "evening": "晚报"}[cycle]), encoding="utf-8")
        return path

    def read(self, name="manifest"):
        return json.loads((self.root / f"reports/latest/{name}.json").read_text())

    def test_orphaned_seven_section_body_is_indexed_without_delivery_claim(self):
        path = self.body()
        out = sync_index(self.root, moment=self.now)
        self.assertEqual(1, len(out["added"]))
        entry = self.read()["latest_by_cycle"]["noon"]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])
        self.assertEqual("unverified", entry["chat_delivery_status"])
        self.assertIsNone(entry["body_archived_at"])
        self.assertIn("第7节", self.read("handoff")["latest_by_cycle"]["noon"]["carry_forward_markdown"])

    def test_preserves_all_old_metadata_and_older_late_archive_cannot_regress_pointer(self):
        self.body("2026-11-01", "evening")
        self.body("2026-11-02", "early")
        old = {"report_date": "2026-11-02", "report_type": "early",
               "selected_file": "reports/archive/2026/11/02/early.md", "custom_public_field": {"retain": True}}
        write_json(self.root / "reports/latest/manifest.json", {"reports": [old], "latest_by_cycle": {"early": old}})
        sync_index(self.root, moment=self.now)
        self.assertIn(old, self.read()["reports"])
        self.assertEqual(old, self.read()["latest_by_cycle"]["early"])
        self.assertEqual(2, len(self.read()["reports"]))

    def test_idempotent_second_run_does_not_churn_timestamps_or_files(self):
        self.body()
        sync_index(self.root, moment=self.now)
        before = (self.root / "reports/latest/handoff.json").read_bytes()
        out = sync_index(self.root, moment=self.now.replace(hour=16))
        self.assertEqual([], out["added"])
        self.assertFalse(out["manifest_changed"])
        self.assertFalse(out["handoff_changed"])
        self.assertEqual(before, (self.root / "reports/latest/handoff.json").read_bytes())

    def test_incomplete_wrong_cycle_and_future_reports_never_enter_index(self):
        self.body(text=report().replace("## 7.", "## 8."))
        self.body("2026-11-01", "early", text=report("2026-11-01", "晚报"))
        self.body("2026-11-03")
        out = sync_index(self.root, moment=self.now)
        self.assertEqual(3, len(out["rejected"]))
        self.assertEqual([], self.read()["reports"])

    def test_corrupt_history_fails_without_overwriting_it(self):
        path = self.root / "reports/latest/manifest.json"
        path.parent.mkdir(parents=True)
        path.write_text("{broken")
        with self.assertRaises(ValueError):
            sync_index(self.root, moment=self.now)
        self.assertEqual("{broken", path.read_text())

    def test_hash_bound_public_sidecar_preserves_original_windows(self):
        path = self.body()
        meta = {"report_date": "2026-11-02", "report_type": "noon",
                "body_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "focus_stock_code": "601919", "focus_status": "watch_for_trigger",
                "focus_conditions": {"original_window": {"review_by": "2026-11-03"}},
                "private_prompt": "must never copy arbitrary fields"}
        write_json(path.with_name("noon-handoff.json"), meta)
        sync_index(self.root, moment=self.now)
        entry = self.read()["latest_by_cycle"]["noon"]
        self.assertEqual(meta["focus_conditions"], entry["focus_conditions"])
        self.assertNotIn("private_prompt", entry)

    def test_bad_sidecar_hash_rejects_orphan_without_claiming_metadata(self):
        path = self.body()
        write_json(path.with_name("noon-handoff.json"), {"report_date": "2026-11-02", "report_type": "noon", "body_sha256": "bad"})
        out = sync_index(self.root, moment=self.now)
        self.assertIn("hash_mismatch", out["rejected"][0]["reason"])
        self.assertEqual([], self.read()["reports"])

    def test_indexed_body_tampering_marks_handoff_invalid(self):
        path = self.body()
        sync_index(self.root, moment=self.now)
        path.write_text(report() + "tampered")
        sync_index(self.root, moment=self.now)
        self.assertEqual("invalid", self.read("handoff")["latest_by_cycle"]["noon"]["status"])
