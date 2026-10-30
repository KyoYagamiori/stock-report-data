"""Noon acceptance must reject old dates, partial quotes and false success."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from market_screen.history import write_json
from market_screen.noon import accepted_noon, accepted_snapshot, ensure_noon
from market_screen import runner
from pipeline.publisher import publish_snapshot
from tests.helpers import valid_snapshot


class NoonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.today = "2026-07-16"
        self.target = "2026-07-15"
        self.now = datetime(2026, 7, 16, 11, 40, tzinfo=runner.TZ)
        write_json(self.root / "output/cache/trade_calendar.json", {
            "source": "verified_exchange_fixture", "trade_dates": [
                "2026-07-13", "2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20"]})
        self.universe = [{"code": code, "exchange": exchange, "name": "测试公司", "board": "main",
                          "listing_date": "2000-01-01", "industry": "制造业"}
                         for code, exchange in (("600000", "SH"), ("000001", "SZ"))]

    def quote(self, code, **changes):
        return {"code": code, "name": "测试公司", "date": self.today, "time": "11:30:00",
                "status": "valid", "open": 10, "prev_close": 10, "close": 10.1,
                "high": 10.2, "low": 9.9, "volume": 1000, "amount": 10100,
                "retrieved_at": self.today + "T11:35:00+08:00", **changes}

    def publish_scan(self, quotes=None, run_id="test-noon", **date_changes):
        records = [{**stock, "market_date": self.target, "status": "screened",
                    "ranking": {"eligible": False}, "update_method": "fixture",
                    "indicators": {"bar_date": self.target, "price": 10,
                                   "boll": {"upper": 11, "mid": 10}}} for stock in self.universe]
        directory = self.root / "output/boll/archive" / self.target / run_id
        directory.mkdir(parents=True)
        dates = {"market_date": self.target, "report_date": self.today, "phase": "noon",
                 "is_trading_day": True, "expected_sessions": [self.target, self.today], **date_changes}
        config = {"candidate_count": 20}
        with patch("market_screen.runner.datetime") as mock_datetime:
            mock_datetime.now.return_value = self.now
            result = runner.publish(self.root, directory, records, self.universe, {"fresh": True}, dates,
                        quotes if quotes is not None else {s["code"]: self.quote(s["code"]) for s in self.universe},
                        {}, self.today + "T11:35:00+08:00", 1, config)
        return result

    def publish_report(self, **changes):
        snapshot = {**valid_snapshot(), **changes}
        return publish_snapshot(snapshot, self.root, {
            "date": self.today, "is_trading_day": True, "latest_completed_trading_day": self.target,
            "next_trading_day": "2026-07-17", "source": "verified_exchange_fixture"})

    def test_complete_scan_and_report_skip_duplicate_collection(self):
        self.publish_scan()
        self.publish_report()
        collect, snapshot = Mock(), Mock()
        result = ensure_noon(self.root, moment=self.now, collector=collect, snapshot_collector=snapshot)
        self.assertTrue(result["accepted"])
        self.assertEqual("already_current", result["status"])
        self.assertEqual(2, result["full_market"]["valid_quotes"])
        collect.assert_not_called()
        snapshot.assert_not_called()
        audit = self.root / result["audit_file"]
        self.assertEqual(result["audit_sha256"], hashlib.sha256(audit.read_bytes()).hexdigest())

    def test_daily_complete_but_zero_noon_quotes_is_not_success(self):
        self.publish_scan(quotes={})
        gate = accepted_noon(self.root, self.now)
        self.assertTrue(gate["daily_baseline"]["accepted"])
        self.assertFalse(gate["accepted"])
        self.assertEqual(0, gate["valid_quotes"])
        self.assertEqual(2, gate["missing_quotes"])

    def test_afternoon_and_yesterday_quotes_do_not_count_as_noon(self):
        self.publish_scan(quotes={"600000": self.quote("600000", time="13:01:00"),
                                  "000001": self.quote("000001", date=self.target)})
        gate = accepted_noon(self.root, self.now)
        self.assertFalse(gate["accepted"])
        self.assertEqual(2, gate["missing_quotes"])

    def test_verified_zero_activity_is_accounted_without_claiming_suspension(self):
        self.publish_scan(quotes={"600000": self.quote("600000"), "000001": self.quote("000001",
            status="no_trades", open=0, high=0, low=0, close=0, volume=0, amount=0)})
        gate = accepted_noon(self.root, self.now)
        self.assertTrue(gate["accepted"])
        self.assertEqual(1, gate["no_trade_quotes"])

    def test_quote_shard_hash_and_security_identity_are_checked(self):
        self.publish_scan()
        manifest = json.loads((self.root / "output/boll/latest/manifest.json").read_text())
        overlay_path = self.root / manifest["latest_noon_overlay"]["selected_file"]
        overlay = json.loads(overlay_path.read_text())
        shard = self.root / overlay["quote_shards"][0]["file"]
        shard.write_bytes(shard.read_bytes() + b" ")
        self.assertIn("sha256_mismatch", accepted_noon(self.root, self.now)["reasons"][0])
        self.publish_scan(run_id="bad-security", quotes={"600000": self.quote("600000"),
                                                        "000001": self.quote("000002")})
        self.assertFalse(accepted_noon(self.root, self.now)["accepted"])

    def test_later_failed_noon_or_intraday_run_does_not_erase_noon_pointer(self):
        self.publish_scan()
        path = self.root / "output/boll/latest/manifest.json"
        original = json.loads(path.read_text())["latest_noon_overlay"]
        self.publish_scan(quotes={}, run_id="failed-noon")
        self.assertEqual(original, json.loads(path.read_text())["latest_noon_overlay"])
        self.assertTrue(accepted_noon(self.root, self.now)["accepted"])
        self.publish_scan(run_id="later-intraday", phase="intraday")
        self.assertEqual(original, json.loads(path.read_text())["latest_noon_overlay"])
        self.assertTrue(accepted_noon(self.root, self.now)["accepted"])

    def test_report_not_ready_is_independent_of_full_market_success(self):
        self.publish_scan()
        self.assertTrue(accepted_noon(self.root, self.now)["accepted"])
        self.assertFalse(accepted_snapshot(self.root, self.now)["accepted"])
        self.publish_report()
        self.assertTrue(accepted_snapshot(self.root, self.now)["accepted"])

    def test_one_retry_repairs_both_components_and_keeps_dates_separate(self):
        calls = []
        def collect(root, **kwargs):
            calls.append(kwargs)
            return self.publish_scan(quotes={} if len(calls) == 1 else None, run_id="retry-" + str(len(calls)))
        def report(root, now):
            self.publish_report()
            return SimpleNamespace(grade="A", published=True, snapshot_id="fixture")
        result = ensure_noon(self.root, moment=self.now, collector=collect, snapshot_collector=report)
        self.assertTrue(result["accepted"])
        self.assertEqual(2, len(calls))
        self.assertEqual(self.target, result["expected_market_date"])
        self.assertTrue(result["market_cutoff"].startswith(self.today))

    def test_repeated_failure_is_visible_and_bounded(self):
        collect = Mock(side_effect=OSError("provider unavailable"))
        report = Mock(side_effect=OSError("snapshot unavailable"))
        result = ensure_noon(self.root, moment=self.now, collector=collect, snapshot_collector=report)
        self.assertFalse(result["accepted"])
        self.assertEqual("incomplete", result["status"])
        self.assertEqual(2, collect.call_count)
        self.assertEqual(2, report.call_count)
        audit = json.loads((self.root / "output/boll/latest/noon_update.json").read_text())
        self.assertEqual(4, len(audit["attempts"]))

    def test_holiday_early_and_late_requests_never_collect(self):
        collect, report = Mock(), Mock()
        for moment, status in ((datetime(2026, 7, 18, 11, 40, tzinfo=runner.TZ), "not_applicable"),
                               (self.now.replace(hour=10), "outside_collection_window"),
                               (self.now.replace(hour=13), "outside_collection_window")):
            result = ensure_noon(self.root, moment=moment, collector=collect, snapshot_collector=report)
            self.assertEqual(status, result["status"])
        collect.assert_not_called()
        report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
