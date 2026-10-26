"""Daily refresh must be complete for the latest session, not just exit zero."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from market_screen.daily import accepted_screen, ensure_daily
from market_screen.history import write_json
from market_screen.runner import TZ


class DailyAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime(2026, 10, 26, 18, tzinfo=TZ)
        write_json(self.root / "output/cache/trade_calendar.json", {
            "source": "verified_exchange_fixture",
            "trade_dates": ["2026-10-15", "2026-10-16", "2026-10-23", "2026-10-26", "2026-10-27", "2026-10-30", "2026-11-02"]})

    def publish(self, market_date="2026-10-26", **changes):
        directory = self.root / "output/boll/archive" / market_date / "test-close"
        directory.mkdir(parents=True, exist_ok=True)
        candidate = directory / "candidates.json"
        write_json(candidate, {"market_date": market_date, "screen_complete": True, "candidates": []})
        screen = {"market_date": market_date, "published_at": market_date + "T16:00:00+08:00",
                  "run_id": "test-close", "technical_screen_complete": True, "universe_current": True,
                  "universe_count": 5223, "status_counts": {"screened": 4968, "excluded": 255},
                  "unresolved_count": 0, "all_codes_accounted_for": True,
                  "candidate_file": candidate.relative_to(self.root).as_posix(), **changes}
        path = directory / "screen.json"
        write_json(path, screen)
        pointer = {"market_date": market_date, "selected_file": path.relative_to(self.root).as_posix(),
                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        write_json(self.root / "output/boll/latest/manifest.json", {"latest_screen": pointer, "latest_complete_screen": pointer})
        return screen

    def test_current_complete_hashed_archive_is_accepted_and_not_rerun(self):
        self.publish()
        collector = Mock()
        result = ensure_daily(self.root, moment=self.now, collector=collector)
        collector.assert_not_called()
        self.assertTrue(result["accepted"])
        self.assertEqual("already_current", result["status"])
        self.assertEqual("2026-10-26", result["market_date"])
        self.assertTrue(result["sha256_verified"])

    def test_old_complete_is_never_accepted_for_new_session(self):
        self.publish("2026-10-15")
        self.assertFalse(accepted_screen(self.root, "2026-10-26", self.now)["accepted"])

    def test_invalid_coverage_membership_and_future_time_fail_closed(self):
        for changes in ({"unresolved_count": 1}, {"universe_current": False},
                        {"technical_screen_complete": False}, {"universe_count": 5224},
                        {"all_codes_accounted_for": False},
                        {"published_at": "2026-10-27T16:00:00+08:00"}):
            with self.subTest(changes=changes):
                self.publish(**changes)
                self.assertFalse(accepted_screen(self.root, "2026-10-26", self.now)["accepted"])

    def test_tampered_archive_and_candidate_wrong_date_are_rejected(self):
        screen = self.publish()
        candidate = self.root / screen["candidate_file"]
        write_json(candidate, {"market_date": "2026-10-15", "screen_complete": True})
        self.assertFalse(accepted_screen(self.root, "2026-10-26", self.now)["accepted"])
        self.publish()
        archive = candidate.parent / "screen.json"
        archive.write_bytes(archive.read_bytes() + b" ")
        self.assertIn("screen_sha256_mismatch", accepted_screen(self.root, "2026-10-26", self.now)["reasons"])

    def test_first_failure_retries_and_only_current_complete_passes(self):
        calls = []
        def collector(root, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise OSError("transient exchange reset")
            return self.publish()
        result = ensure_daily(self.root, moment=self.now, collector=collector)
        self.assertTrue(result["accepted"])
        self.assertEqual(2, len(result["attempts"]))
        self.assertIn("transient exchange reset", result["attempts"][0]["error"])
        self.assertEqual("updated", result["status"])

    def test_repeated_partial_run_has_visible_failure_and_keeps_old_date(self):
        self.publish("2026-10-15")
        collector = Mock(return_value={"technical_screen_complete": False, "unresolved_count": 5})
        result = ensure_daily(self.root, moment=self.now, collector=collector)
        self.assertEqual(2, collector.call_count)
        self.assertFalse(result["accepted"])
        self.assertEqual("incomplete", result["status"])
        audit = json.loads((self.root / "output/boll/latest/daily_update.json").read_text())
        self.assertEqual("2026-10-26", audit["expected_market_date"])
        self.assertFalse(audit["accepted"])

    def test_nontrading_day_checks_friday_without_inventing_new_prices(self):
        self.publish("2026-10-30")
        collector = Mock()
        result = ensure_daily(self.root, moment=datetime(2026, 10, 31, 16, tzinfo=TZ), collector=collector)
        collector.assert_not_called()
        self.assertTrue(result["accepted"])
        self.assertFalse(result["is_trading_day"])
        self.assertEqual("2026-10-30", result["market_date"])
        self.assertEqual("2026-10-31", result["report_date"])

    def test_intraday_daily_close_refresh_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "completed_session"):
            ensure_daily(self.root, moment=datetime(2026, 10, 26, 14, 59, tzinfo=TZ))


if __name__ == "__main__":
    unittest.main()
