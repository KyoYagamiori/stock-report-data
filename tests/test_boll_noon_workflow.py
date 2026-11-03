"""Concurrent writers must retain independent evidence and accepted pointers."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from market_screen.workflow_io import archive_directory, merge_boll_manifest, merge_report_manifest, publish_outputs, select_bootstrap_pair
from pipeline.manifest import new_manifest
from tests.helpers import valid_snapshot
from pipeline.manifest import apply_pointer, build_pointer


class PointerMergeTests(unittest.TestCase):
    def test_bootstrap_merge_keeps_verified_metadata_and_bytes_together(self):
        import hashlib
        old, new = b'old compressed evidence', b'new compressed evidence'
        first = {"adjustment": "unadjusted", "market_date": "2026-11-02", "sha256": hashlib.sha256(old).hexdigest()}
        second = {"adjustment": "unadjusted", "market_date": "2026-11-03", "sha256": hashlib.sha256(new).hexdigest()}
        self.assertEqual((second, new), select_bootstrap_pair([(first, old), (second, new)]))
        self.assertEqual((first, old), select_bootstrap_pair([(first, old), (second, old)]))
        with self.assertRaisesRegex(ValueError, "no_hash_verified"):
            select_bootstrap_pair([(second, old)])

    def test_noon_does_not_erase_a_concurrent_newer_completed_close(self):
        close = {"market_date": "2026-11-02", "published_at": "2026-11-02T16:00:00+08:00", "technical_screen_complete": True}
        universe = {"report_date": "2026-11-02", "published_at": "2026-11-02T08:30:00+08:00", "accepted": True}
        noon = {"market_date": "2026-11-02", "published_at": "2026-11-02T11:40:00+08:00", "full_market_overlay_complete": True, "valid_quotes": 5200}
        remote = {"latest_complete_screen": close, "latest_screen": close, "unrelated_existing_field": {"keep": True}}
        incoming = {"latest_complete_screen": {**close, "market_date": "2026-10-30"}, "latest_noon_overlay": noon, "latest_universe": universe}
        merged = merge_boll_manifest(remote, incoming)
        self.assertEqual(close, merged["latest_complete_screen"])
        self.assertEqual(noon, merged["latest_noon_overlay"])
        self.assertEqual(universe, merged["latest_universe"])
        self.assertTrue(merged["unrelated_existing_field"]["keep"])
        broken = merge_boll_manifest(merged, {"latest_complete_screen": {**close, "market_date": "2026-11-03", "technical_screen_complete": False}})
        self.assertEqual(close, broken["latest_complete_screen"])

    def test_same_date_partial_cannot_replace_complete_noon(self):
        ready = {"market_date": "2026-11-02", "published_at": "2026-11-02T11:40:00+08:00", "full_market_overlay_complete": True, "valid_quotes": 5219}
        partial = {**ready, "published_at": "2026-11-02T12:10:00+08:00", "full_market_overlay_complete": False, "valid_quotes": 5218}
        self.assertEqual(ready, merge_boll_manifest({"latest_noon_overlay": ready}, {"latest_noon_overlay": partial})["latest_noon_overlay"])

    def test_input_hydration_cannot_expand_to_arbitrary_paths_or_shell_patterns(self):
        self.assertEqual("/output/boll/archive/2026-11-02/run-noon/", archive_directory("output/boll/archive/2026-11-02/run-noon/screen.json"))
        for value in ("../../secret", "/output/boll/archive/a/b", "output/boll/archive/*/screen.json", "config/private.json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                archive_directory(value)

    def test_snapshot_merge_retains_other_cycles_and_stronger_grade(self):
        snap = valid_snapshot()
        calendar = {"date": snap["report_date"], "is_trading_day": True}
        remote, incoming = new_manifest(calendar, snap["published_at"]), new_manifest(calendar, snap["published_at"])
        pointer = build_pointer(snap, "output/archive/a.json", "a" * 64)
        apply_pointer(remote, pointer, snap)
        weaker = {**snap, "quality_grade": "B", "published_at": "2026-07-16T12:10:00+08:00"}
        apply_pointer(incoming, build_pointer(weaker, "output/archive/b.json", "b" * 64), weaker)
        merged = merge_report_manifest(remote, incoming)
        self.assertEqual("A", merged["snapshots"]["noon"]["quality_grade"])
        self.assertEqual("ready_a", merged["report_readiness"]["noon"]["status"])


class RealConcurrentGitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote = self.root / "remote.git"
        self.git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.a, self.b = self.root / "a", self.root / "b"
        self.git(self.root, "clone", str(self.remote), str(self.a))
        self.configure(self.a)
        self.write(self.a, "output/boll/latest/manifest.json", {"schema_version": "1.0"})
        self.git(self.a, "add", ".")
        self.git(self.a, "commit", "-m", "seed")
        self.git(self.a, "push", "origin", "main")
        self.git(self.root, "clone", str(self.remote), str(self.b))
        self.configure(self.b)

    def git(self, root, *args):
        result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout

    def configure(self, root):
        self.git(root, "config", "user.name", "fixture")
        self.git(root, "config", "user.email", "fixture@example.invalid")

    def write(self, root, path, data):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data))

    def test_two_writers_rebase_without_losing_close_or_membership(self):
        close = {"market_date": "2026-11-02", "technical_screen_complete": True, "published_at": "2026-11-02T16:00:00+08:00"}
        member = {"report_date": "2026-11-02", "accepted": True, "published_at": "2026-11-02T08:30:00+08:00"}
        self.write(self.a, "output/boll/latest/manifest.json", {"schema_version": "1.0", "latest_complete_screen": close})
        self.write(self.a, "output/boll/archive/2026-11-02/close/screen.json", close)
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}):
            self.assertTrue(publish_outputs(self.a, "close")["published"])
        self.write(self.b, "output/boll/latest/manifest.json", {"schema_version": "1.0", "latest_universe": member})
        self.write(self.b, "output/boll/archive/2026-11-02/member/universe.json", member)
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}):
            self.assertTrue(publish_outputs(self.b, "membership")["published"])
        final = json.loads((self.b / "output/boll/latest/manifest.json").read_text())
        self.assertEqual(close, final["latest_complete_screen"])
        self.assertEqual(member, final["latest_universe"])
        self.assertTrue((self.b / "output/boll/archive/2026-11-02/close/screen.json").exists())
        self.assertTrue((self.b / "output/boll/archive/2026-11-02/member/universe.json").exists())

    def test_existing_immutable_evidence_cannot_be_edited_or_deleted(self):
        path = "output/boll/archive/2026-11-02/seed/screen.json"
        self.write(self.a, path, {"immutable": True})
        self.git(self.a, "add", ".")
        self.git(self.a, "commit", "-m", "immutable fixture")
        self.write(self.a, path, {"immutable": False})
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}), self.assertRaisesRegex(ValueError, "modify_immutable"):
            publish_outputs(self.a, "noon")
        (self.a / path).unlink()
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}), self.assertRaisesRegex(ValueError, "must_not_delete"):
            publish_outputs(self.a, "noon")


if __name__ == "__main__":
    unittest.main()
