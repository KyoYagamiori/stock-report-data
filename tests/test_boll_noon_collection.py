"""End-to-end noon regressions: no historical rebuild, gap merging, honest gates."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from market_screen import runner
from market_screen.history import write_json
from market_screen.membership import freeze_membership, read_frozen_universe
from market_screen.noon import accepted_noon, ensure_noon
from market_screen.noon_collection import collect_noon, compare_noon
from market_screen.quotes import parse_sina_quotes
from tests.test_boll_runner import CONFIG, history, sessions_ending, stock

TODAY, TARGET = "2026-10-15", "2026-10-14"
NOW = datetime.fromisoformat(TODAY + "T11:40:00+08:00")


def raw_quote(listing, day=TODAY, stamp="11:30:00", no_trades=False):
    fields = ["0"] * 33
    for index, value in {0: listing["name"], 1: "11.79", 2: "11.79", 3: "11.80", 4: "11.90", 5: "11.70",
                         8: "10000000", 9: "118000000", 30: day, 31: stamp}.items():
        fields[index] = value
    if no_trades:
        for index in (1, 3, 4, 5, 8, 9):
            fields[index] = "0"
    symbol = ("sh" if listing["exchange"] == "SH" else "sz") + listing["code"]
    return ('var hq_str_' + symbol + '="' + ",".join(fields) + '";').encode("gb18030")


class IndependentNoonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.universe = [stock(), stock("000001", "SZ")]
        self.sessions = sessions_ending() + [TODAY, "2026-10-16", "2026-10-19"]
        self.config = {**CONFIG, "request_timeout_seconds": 8, "retry_count": 1, "history_workers": 4}
        write_json(self.root / "config/boll_screen.json", self.config)
        write_json(self.root / "output/cache/trade_calendar.json", {"source": "verified_exchange_fixture", "trade_dates": self.sessions})
        self.publish_baseline()
        with patch("market_screen.membership.load_universe", return_value=(self.universe, self.metadata(TODAY))):
            freeze_membership(self.root, moment=NOW.replace(hour=8, minute=0))

    def metadata(self, day):
        sources = {}
        for name in ("sse_main", "sse_star", "szse_metadata", "szse_xlsx"):
            path = self.root / "output/boll/state/universe_sources" / day / (name + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps({"official_fixture": name, "date": day}).encode()
            path.write_bytes(raw)
            sources[name] = {"http_status": 200, "sha256": hashlib.sha256(raw).hexdigest(), "http_server_date": day,
                "source_version_date": day if name.startswith("szse") else None,
                "raw_file": path.relative_to(self.root).as_posix(), "retrieved_at": day + "T08:00:00+08:00"}
        return {"fresh": True, "mode": "official_live", "version_date": day, "retrieved_at": day + "T08:00:00+08:00", "sources": sources}

    def quotes(self, universe, directory, *, day=TODAY, stamps=None, no_trade=None):
        quotes = {}
        path = directory / "quote_sources" / "fixture.raw"
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = b"\n".join(raw_quote(s, day, (stamps or {}).get(s["code"], "11:30:00" if day == TODAY else "15:00:00"),
                                   s["code"] in (no_trade or [])) for s in universe)
        path.write_bytes(raw)
        for code, quote in parse_sina_quotes(raw).items():
            quote.update(raw_file=path.relative_to(self.root).as_posix(), retrieved_at=day + ("T11:35:00+08:00" if day == TODAY else "T15:30:00+08:00"))
            quotes[code] = quote
        return quotes

    def publish_baseline(self, no_trade=None):
        directory = self.root / "output/boll/archive" / TARGET / "baseline"
        directory.mkdir(parents=True, exist_ok=True)
        quotes = self.quotes(self.universe, directory, day=TARGET, no_trade=no_trade)
        records = [runner.assemble_record(s, history(), TARGET, self.config, self.sessions, quotes[s["code"]]) for s in self.universe]
        dates = {"market_date": TARGET, "report_date": TARGET, "phase": "close", "is_trading_day": True, "expected_sessions": self.sessions}
        self.baseline = runner.publish(self.root, directory, records, self.universe, self.metadata(TARGET), dates, quotes, {},
            TARGET + "T15:30:00+08:00", 1, self.config, moment=NOW.replace(day=14, hour=16))

    def collector(self, stamps=None):
        def collect(universe, directory, **kwargs):
            return self.quotes(universe, directory, stamps=stamps), {"fixture": True}
        return Mock(side_effect=collect)

    def execute(self, **kwargs):
        with patch("market_screen.noon_collection.load_universe", side_effect=AssertionError("unexpected live universe fetch in fixture")):
            return collect_noon(self.root, moment=kwargs.pop("moment", NOW), quote_collector=kwargs.pop("quote_collector", self.collector()),
                                repairer=kwargs.pop("repairer", Mock(return_value=(None, []))), **kwargs)

    def test_full_coverage_uses_completed_store_and_never_calls_history(self):
        history_fetcher = Mock(side_effect=AssertionError("history must not be fetched"))
        with patch("market_screen.noon_collection.load_universe", side_effect=AssertionError("same-day list already frozen")):
            summary = self.execute(history_fetcher=history_fetcher)
        gate = accepted_noon(self.root, NOW)
        history_fetcher.assert_not_called()
        self.assertTrue(gate["accepted"], gate)
        self.assertEqual(2, summary["collection_details"]["completed_daily"]["reused_count"])
        self.assertEqual(2, gate["full_universe_comparison"]["evaluated_count"])
        self.assertTrue(gate["official_membership_bytes_verified"])
        comparison = summary["collection_details"]["noon_comparison"]
        candidates = json.loads((self.root / comparison["candidate_file"]).read_text())
        self.assertEqual(2, candidates["eligible_count"], "Valid daily setups must survive a valid noon overlay")
        self.assertEqual({"600000", "000001"}, {r["code"] for r in candidates["candidates"]})
        for row in candidates["candidates"]:
            self.assertEqual([], row["noon_comparison"]["rejection_reasons"])
            self.assertTrue(row["noon_comparison"]["setup_reasons"])

    def test_second_attempt_requests_only_bad_quote_and_keeps_good_observation(self):
        first = self.collector({"000001": "11:35:00"})
        self.execute(quote_collector=first)
        self.assertEqual(1, accepted_noon(self.root, NOW)["missing_quotes"])
        retry = self.collector()
        self.execute(moment=NOW.replace(minute=45), quote_collector=retry)
        requested = retry.call_args.args[0]
        self.assertEqual(["000001"], [s["code"] for s in requested])
        self.assertTrue(accepted_noon(self.root, NOW.replace(minute=45))["accepted"])

    def test_excluded_short_history_with_null_boll_does_not_abort_full_comparison(self):
        directory = self.root / "output/boll/archive" / TARGET / "null-boll-comparison"
        quotes = self.quotes(self.universe, directory)
        records = [runner.assemble_record(s, history(), TARGET, self.config, self.sessions) for s in self.universe]
        records[0].update(status="excluded", reasons=["new_listing_insufficient_completed_history"], ranking={"eligible": False})
        records[0]["indicators"].update(boll=None, bar_count=1)
        dates = {"market_date": TARGET, "report_date": TODAY}
        result = compare_noon(self.root, directory, records, quotes, dates, NOW, self.config)
        table = json.loads((self.root / result["candidate_file"]).read_text())
        self.assertEqual(2, table["evaluated_count"])
        self.assertEqual(1, table["eligible_count"])
        self.assertEqual([records[1]["code"]], [r["code"] for r in table["candidates"]])
        compared = [r for ref in result["record_shards"] for r in json.loads((self.root / ref["file"]).read_text())["records"]]
        excluded = next(r for r in compared if r["code"] == records[0]["code"])
        self.assertIn("new_listing_insufficient_completed_history", excluded["rejection_reasons"])

    def test_missing_boll_on_screened_record_fails_closed_without_aborting_other_codes(self):
        directory = self.root / "output/boll/archive" / TARGET / "bad-boll-comparison"
        quotes = self.quotes(self.universe, directory)
        records = [runner.assemble_record(s, history(), TARGET, self.config, self.sessions) for s in self.universe]
        records[0]["indicators"]["boll"] = None
        result = compare_noon(self.root, directory, records, quotes, {"market_date": TARGET, "report_date": TODAY}, NOW, self.config)
        compared = [r for ref in result["record_shards"] for r in json.loads((self.root / ref["file"]).read_text())["records"]]
        broken = next(r for r in compared if r["code"] == records[0]["code"])
        self.assertFalse(broken["eligible"])
        self.assertIn("completed_daily_boll_unavailable", broken["rejection_reasons"])

    def test_resumption_today_does_not_erase_prior_completed_no_trade_exclusion(self):
        self.publish_baseline(no_trade=["600000"])
        # Keep the already frozen current list; only the completed day is replaced.
        self.execute(history_fetcher=Mock(side_effect=AssertionError("historical no-trade evidence exists")))
        gate = accepted_noon(self.root, NOW)
        self.assertTrue(gate["accepted"], gate)
        self.assertEqual(1, gate["current_screen"]["status_counts"]["excluded"])
        self.assertEqual(2, gate["valid_quotes"])
        # A retry must be able to use the self-contained newly published proof.
        self.execute(moment=NOW.replace(minute=45), quote_collector=Mock(side_effect=AssertionError("quotes already complete")))
        self.assertTrue(accepted_noon(self.root, NOW.replace(minute=45))["accepted"])

    def test_corrupt_daily_shard_preserves_quote_diagnostics_and_does_not_rebuild_all(self):
        shard = self.root / self.baseline["record_shards"][0]["file"]
        shard.write_bytes(shard.read_bytes() + b" ")
        fetcher = Mock(side_effect=AssertionError("cannot rebuild a corrupt whole store at noon"))
        self.execute(history_fetcher=fetcher)
        fetcher.assert_not_called()
        gate = accepted_noon(self.root, NOW)
        self.assertFalse(gate["accepted"])
        self.assertEqual(2, gate["valid_quotes"])
        self.assertEqual(0, gate["missing_quotes"])

    def test_missing_previous_session_never_borrows_an_older_complete_date(self):
        path = self.root / "output/boll/latest/manifest.json"
        manifest = json.loads(path.read_text())
        for key in ("latest_screen", "latest_complete_screen"):
            manifest[key]["market_date"] = "2026-10-13"
        write_json(path, manifest)
        self.execute()
        gate = accepted_noon(self.root, NOW)
        self.assertFalse(gate["accepted"])
        self.assertEqual(2, gate["valid_quotes"])
        self.assertFalse(gate["daily_baseline"]["accepted"])

    def test_a_new_listing_is_accounted_without_fabricating_160_bars(self):
        self.universe.append(stock("301999", "SZ", board="chinext", listing_date=TODAY))
        with patch("market_screen.membership.load_universe", return_value=(self.universe, self.metadata(TODAY))):
            freeze_membership(self.root, moment=NOW.replace(hour=8, minute=5))
        self.execute()
        gate = accepted_noon(self.root, NOW)
        self.assertTrue(gate["accepted"], gate)
        self.assertEqual(3, gate["universe_count"])
        self.assertEqual(1, gate["current_screen"]["status_counts"]["excluded"])

    def test_a_genuine_partial_store_repairs_only_the_unresolved_security(self):
        shard_path = self.root / self.baseline["record_shards"][0]["file"]
        shard = json.loads(shard_path.read_text())
        shard["records"][0].update(status="unresolved", reasons=["missing_target_session_bar"])
        write_json(shard_path, shard)
        screen_path = self.root / "output/boll/archive" / TARGET / "baseline/screen.json"
        screen = json.loads(screen_path.read_text())
        screen["record_shards"][0]["sha256"] = hashlib.sha256(shard_path.read_bytes()).hexdigest()
        screen.update(technical_screen_complete=False, unresolved_count=1, status_counts={"screened": 1, "unresolved": 1})
        write_json(screen_path, screen)
        manifest_path = self.root / "output/boll/latest/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        for key in ("latest_screen", "latest_complete_screen"):
            manifest[key]["sha256"] = hashlib.sha256(screen_path.read_bytes()).hexdigest()
        write_json(manifest_path, manifest)
        fetcher = Mock(return_value=history())
        self.execute(history_fetcher=fetcher)
        self.assertEqual(1, fetcher.call_count)
        self.assertEqual(shard["records"][0]["code"], fetcher.call_args.args[0]["code"])
        self.assertTrue(accepted_noon(self.root, NOW)["accepted"])

    def test_frozen_raw_proof_and_future_publication_are_rejected(self):
        manifest = json.loads((self.root / "output/boll/latest/manifest.json").read_text())
        pointer = manifest["latest_universe"]
        with self.assertRaisesRegex(ValueError, "not_yet_published"):
            read_frozen_universe(self.root, TODAY, NOW.replace(hour=7))
        universe = json.loads((self.root / pointer["universe_file"]).read_text())
        proof = self.root / universe["provenance"]["sources"]["sse_main"]["raw_file"]
        proof.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "sha256_mismatch"):
            read_frozen_universe(self.root, TODAY, NOW)

    def test_raw_quote_tamper_is_not_hidden_by_valid_json_shards(self):
        summary = self.execute()
        overlay = json.loads((self.root / summary["overlay_file"]).read_text())
        shard = json.loads((self.root / overlay["quote_shards"][0]["file"]).read_text())
        proof = self.root / shard["records"][0]["quote"]["raw_file"]
        proof.write_bytes(b"changed")
        gate = accepted_noon(self.root, NOW)
        self.assertFalse(gate["accepted"])
        self.assertIn("raw_quote_evidence_invalid", gate["quote_gaps"][0]["reasons"][0])

    def test_late_run_does_not_replace_an_existing_noon_audit(self):
        latest = self.root / "output/boll/latest/noon_update.json"
        write_json(latest, {"report_date": TODAY, "accepted": True, "checked_at": TODAY + "T12:10:00+08:00"})
        original = latest.read_bytes()
        with patch("builtins.print"):
            result = ensure_noon(self.root, moment=NOW.replace(hour=12, minute=21))
        self.assertEqual("outside_collection_window", result["status"])
        self.assertEqual(original, latest.read_bytes())

    def test_noon_collector_rejects_afternoon_start(self):
        with self.assertRaisesRegex(ValueError, "1130_to_1220"):
            self.execute(moment=NOW.replace(hour=13))

    def test_membership_failure_does_not_hide_valid_noon_quote_counts(self):
        manifest_path = self.root / "output/boll/latest/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest.pop("latest_universe")
        write_json(manifest_path, manifest)
        with patch("market_screen.noon_collection.load_universe", return_value=(self.universe, self.metadata(TARGET))):
            collect_noon(self.root, moment=NOW, quote_collector=self.collector(), repairer=Mock(return_value=(None, [])))
        gate = accepted_noon(self.root, NOW)
        self.assertFalse(gate["accepted"])
        self.assertTrue(gate["daily_baseline"]["accepted"])
        self.assertEqual(2, gate["valid_quotes"])
        self.assertEqual(0, gate["missing_quotes"])

    def test_late_real_quote_replay_does_not_rewrite_original_noon_acceptance(self):
        from market_screen.noon_probe import replay_latest_noon
        from tests.test_boll_noon_repair import Response, minute_bytes
        self.execute(quote_collector=self.collector({"000001": "11:35:00"}))
        canonical = self.root / "output/boll/latest/noon_update.json"
        write_json(canonical, {"accepted": False, "report_date": TODAY, "reason": "original_at_cutoff"})
        manifest_path = self.root / "output/boll/latest/manifest.json"
        before = canonical.read_bytes(), manifest_path.read_bytes()
        with patch("market_screen.noon_repair.urlopen", return_value=Response(minute_bytes(code="000001", market=0))):
            result = replay_latest_noon(self.root, moment=NOW.replace(hour=17))
        self.assertEqual("quote_replay_complete", result["status"])
        self.assertEqual({"valid_quotes": 2, "no_trade_quotes": 0, "missing_quotes": 0}, result["after"])
        self.assertFalse(result["historical_noon_acceptance_changed"])
        self.assertEqual(before, (canonical.read_bytes(), manifest_path.read_bytes()))


if __name__ == "__main__":
    unittest.main()

