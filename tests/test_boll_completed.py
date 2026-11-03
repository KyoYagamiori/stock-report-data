from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from market_screen.completed import reuse_completed_exclusions
from market_screen.completed_source import retain_completed_no_trade, verify_no_trade
from market_screen.history import write_json
from market_screen.quotes import parse_sina_quotes
from market_screen.technicals import PARAMETERS
from tests.test_boll_quotes import quote_bytes


class CompletedExclusionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.day = "2026-10-30"
        self.now = datetime.fromisoformat("2026-11-02T12:20:00+08:00")
        self.directory = self.root / "output/boll/archive/2026-10-30/accepted-close"
        self.raw_path = self.directory / "quote_sources/zero.raw"
        self.raw_path.parent.mkdir(parents=True)
        self.raw = quote_bytes("sh601326", day=self.day, stamp="15:35:00",
                               open_=0, close=0, high=0, low=0, volume=0, amount=0)
        self.raw_path.write_bytes(self.raw)
        quote = parse_sina_quotes(self.raw)["601326"]
        quote["raw_file"] = "/old/runner/location/" + self.raw_path.relative_to(self.root).as_posix()
        old = {"code": "601326", "market_date": self.day, "status": "excluded",
               "reasons": ["no_trades_on_target_session"], "quote": quote, "ranking": {"eligible": False}}
        self.shard = self.directory / "records/601326-601326.json"
        write_json(self.shard, {"records": [old]})
        self.screen = self.directory / "screen.json"
        write_json(self.screen, {"market_date": self.day, "published_at": self.day + "T22:30:00+08:00",
            "technical_screen_complete": True, "universe_current": True, "all_codes_accounted_for": True,
            "unresolved_count": 0, "universe_count": 1, "status_counts": {"excluded": 1}, "parameters": PARAMETERS,
            "record_shards": [{"file": self.shard.relative_to(self.root).as_posix(), "count": 1,
                                "sha256": hashlib.sha256(self.shard.read_bytes()).hexdigest()}]})
        write_json(self.root / "output/boll/latest/manifest.json", {"latest_complete_screen": {
            "market_date": self.day, "selected_file": self.screen.relative_to(self.root).as_posix(),
            "sha256": hashlib.sha256(self.screen.read_bytes()).hexdigest()}})
        self.row = {"code": "601326", "market_date": self.day, "status": "unresolved", "reasons": ["missing_target_session_bar"]}

    def reuse(self, row=None, target=None):
        return reuse_completed_exclusions(self.root, [row or self.row], target or self.day, self.now)[0]

    def test_matching_completed_session_reuses_hashed_original_zero_activity(self):
        out = self.reuse()
        self.assertEqual("excluded", out["status"])
        self.assertEqual(self.day, out["market_date"])
        self.assertEqual(self.day, out["quote"]["date"])
        self.assertEqual("15:35:00", out["quote"]["time"])
        self.assertEqual("verified_same_session_no_trade_reuse", out["update_method"])
        self.assertIn("not a claim about today's suspension", out["completed_session_exclusion_evidence"]["scope_note"])

    def test_linked_completed_proof_is_verified_and_retained_in_new_version(self):
        row = self.reuse()
        directory = self.root / "output/boll/archive" / self.day / "republished"
        verify_no_trade(self.root, directory, row, self.day, self.now)
        retained = retain_completed_no_trade(self.root, directory, [row], self.day, self.now)[0]
        self.assertEqual("excluded", retained["status"])
        self.assertEqual(row["quote"]["time"], retained["quote"]["time"])
        self.assertEqual(row["quote"]["retrieved_at"], retained["quote"]["retrieved_at"])
        self.assertTrue((self.root / retained["quote"]["raw_file"]).is_relative_to(directory / "quote_sources"))
        verify_no_trade(self.root, directory, retained, self.day, self.now)

    def test_linked_proof_cannot_borrow_a_different_date_or_ignore_tampering(self):
        directory = self.root / "output/boll/archive" / self.day / "republished"
        row = self.reuse()
        row["completed_session_exclusion_evidence"]["market_date"] = "2026-10-29"
        out = retain_completed_no_trade(self.root, directory, [row], self.day, self.now)[0]
        self.assertEqual("unresolved", out["status"])
        row = self.reuse()
        self.shard.write_bytes(self.shard.read_bytes() + b" ")
        out = retain_completed_no_trade(self.root, directory, [row], self.day, self.now)[0]
        self.assertEqual("unresolved", out["status"])
        self.assertIn("sha256_mismatch", out["completed_exclusion_reuse_error"])

    def test_another_market_date_cannot_borrow_old_exclusion(self):
        row = {**self.row, "market_date": "2026-11-02"}
        self.assertEqual("unresolved", self.reuse(row, "2026-11-02")["status"])

    def test_current_valid_history_and_other_error_types_are_not_overwritten(self):
        for change in ({"status": "screened", "reasons": []}, {"reasons": ["history_request_failed"]}):
            row = {**self.row, **change}
            self.assertEqual(row, self.reuse(row))

    def test_tampered_screen_or_shard_fails_closed(self):
        for path in (self.screen, self.shard):
            before = path.read_bytes()
            path.write_bytes(before + b" ")
            out = self.reuse()
            self.assertEqual("unresolved", out["status"])
            self.assertIn("sha256_mismatch", out["completed_exclusion_reuse_error"])
            path.write_bytes(before)

    def test_missing_or_changed_original_quote_fails_closed(self):
        self.raw_path.write_bytes(b"changed")
        self.assertEqual("unresolved", self.reuse()["status"])
        self.raw_path.unlink()
        self.assertEqual("unresolved", self.reuse()["status"])

    def test_positive_activity_in_raw_proof_cannot_be_reused_as_no_trade(self):
        self.raw_path.write_bytes(quote_bytes("sh601326", day=self.day, stamp="15:00:00"))
        # Even a hash-consistent rewritten chain cannot certify a zero-activity
        # record whose original provider fields show actual trades.
        rows = json.loads(self.shard.read_text())
        rows["records"][0]["quote"]["raw_sha256"] = hashlib.sha256(self.raw_path.read_bytes()).hexdigest()
        write_json(self.shard, rows)
        screen = json.loads(self.screen.read_text())
        screen["record_shards"][0]["sha256"] = hashlib.sha256(self.shard.read_bytes()).hexdigest()
        write_json(self.screen, screen)
        manifest_path = self.root / "output/boll/latest/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["latest_complete_screen"]["sha256"] = hashlib.sha256(self.screen.read_bytes()).hexdigest()
        write_json(manifest_path, manifest)
        out = self.reuse()
        self.assertEqual("unresolved", out["status"])
        self.assertIn("raw_fields_mismatch", out["completed_exclusion_reuse_error"])
