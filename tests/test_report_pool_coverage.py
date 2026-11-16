"""A legacy 25-symbol success must not hide five missing active-report symbols."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.contracts import load_report_pools, report_quote_gaps
from pipeline.catchup import _same_day_noon_ready
from pipeline.publisher import publish_snapshot
from pipeline.quality import evaluate_quality
from market_screen.noon import audit_missed_noon
from tests.helpers import valid_snapshot


def current_snapshot():
    snapshot = json.loads(json.dumps(valid_snapshot()).replace("2026-07-16", "2026-11-16")
                          .replace("20260716", "20261116"))
    pools = load_report_pools()
    snapshot["stocks"] = [dict(row, pool=group, valid_quote=True)
                          for group in ("core", "watch", "supplemental") for row in pools[group]]
    return snapshot


class ReportUniverseTests(unittest.TestCase):
    def test_all_eight_report_symbols_are_in_actual_collection_configuration(self):
        pools = load_report_pools()
        codes = [r["code"] for group in ("core", "watch", "supplemental") for r in pools[group]]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue({"688700", "301071", "600172", "300476", "600967", "001965", "003816", "002746"} <= set(codes))
        self.assertEqual(["688700"], [r["code"] for group in ("core", "watch", "supplemental")
                                    for r in pools[group] if r.get("locked")])

    def test_legacy_pool_is_not_grade_a_or_an_accepted_catchup_result(self):
        snapshot = current_snapshot()
        snapshot["stocks"] = [row for row in snapshot["stocks"] if row["pool"] != "supplemental"]
        self.assertEqual(["001965", "002746", "003816", "301071", "600967"], report_quote_gaps(snapshot))
        self.assertEqual("B", evaluate_quality(snapshot, "trading_noon").grade)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            publish_snapshot(snapshot, root, {"date": "2026-11-16", "is_trading_day": True,
                                             "latest_completed_trading_day": "2026-11-13",
                                             "next_trading_day": "2026-11-17", "source": "test"})
            self.assertFalse(_same_day_noon_ready(root, "2026-11-16"))

    def test_complete_active_pool_and_older_reports_remain_valid(self):
        snapshot = current_snapshot()
        self.assertEqual([], report_quote_gaps(snapshot))
        self.assertEqual("A", evaluate_quality(snapshot, "trading_noon").grade)
        self.assertEqual([], report_quote_gaps(valid_snapshot()))
        self.assertEqual("A", evaluate_quality(valid_snapshot(), "trading_noon").grade)


class MissedWindowTests(unittest.TestCase):
    def test_late_membership_run_records_today_without_any_market_request(self):
        now = datetime.fromisoformat("2026-11-16T14:27:10+08:00")
        dates = {"report_date": "2026-11-16", "market_date": "2026-11-13", "is_trading_day": True}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            latest = root / "output/boll/latest/noon_update.json"
            latest.parent.mkdir(parents=True)
            old = {"report_date": "2026-11-13", "accepted": False, "valid_quotes": 5215}
            latest.write_text(json.dumps(old))
            with patch("market_screen.noon.resolve_dates", return_value=dates), \
                 patch("market_screen.noon.collect_noon", side_effect=AssertionError("late quotes forbidden")), \
                 patch("market_screen.noon._collect_snapshot", side_effect=AssertionError("late collection forbidden")):
                result = audit_missed_noon(root, moment=now)
            self.assertEqual("outside_collection_window", result["status"])
            self.assertFalse(result["accepted"])
            self.assertEqual("2026-11-16", json.loads(latest.read_text())["report_date"])
            self.assertEqual([], result["attempts"])
            self.assertTrue((root / result["audit_file"]).is_file())

    def test_current_successful_or_failed_audit_is_not_overwritten(self):
        now = datetime.fromisoformat("2026-11-16T14:27:10+08:00")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            latest = root / "output/boll/latest/noon_update.json"
            latest.parent.mkdir(parents=True)
            for accepted in (False, True):
                raw = json.dumps({"report_date": "2026-11-16", "accepted": accepted})
                latest.write_text(raw)
                with patch("market_screen.noon.resolve_dates", return_value={"report_date": "2026-11-16", "is_trading_day": True}), \
                     patch("market_screen.noon.ensure_noon", side_effect=AssertionError("preserve original audit")):
                    self.assertEqual(accepted, audit_missed_noon(root, moment=now)["accepted"])
                self.assertEqual(raw, latest.read_text())

    def test_audit_does_not_run_before_deadline(self):
        with patch("market_screen.noon.resolve_dates", side_effect=AssertionError("not yet due")):
            self.assertIsNone(audit_missed_noon(Path("."), moment=datetime.fromisoformat("2026-11-16T11:50:00+08:00")))


if __name__ == "__main__":
    unittest.main()
