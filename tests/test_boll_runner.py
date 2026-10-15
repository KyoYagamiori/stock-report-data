"""Regression tests for completed sessions, exclusion evidence and publication."""
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from market_screen import runner


TZ = ZoneInfo("Asia/Shanghai")
TARGET = "2026-10-14"


def sessions_ending(target=TARGET, count=180):
    day = date.fromisoformat(target)
    days = []
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    return sorted(days)


def stock(code="600000", exchange="SH", **updates):
    out = {"code": code, "name": "测试股份", "exchange": exchange,
           "board": "main", "listing_date": "2000-01-01", "industry": "制造业"}
    out.update(updates)
    return out


def history(days=None, **updates):
    days = days if days is not None else sessions_ending()
    bars = []
    for index, day in enumerate(days):
        price = 10 + index * .01
        bars.append({"day": day, "open": price, "high": price + .2,
                     "low": price - .2, "close": price, "volume": 10000000})
    out = {"fetch_status": "success", "bars": bars, "source": {"method": "test_fixture"},
           "update_method": "fixture", "history_sha256": "fixture"}
    out.update(updates)
    return out


CONFIG = {
    "minimum_history_bars": 160,
    "maximum_extension_above_upper_pct": 3,
    "minimum_estimated_turnover_20d_median_cny": 50000000,
    "candidate_count": 20,
}


class CompletedSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write_calendar(["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15",
                             "2026-10-16", "2026-10-19", "2026-10-20"])

    def write_calendar(self, dates, source="verified_exchange_test_fixture"):
        path = self.root / "output/cache/trade_calendar.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"trade_dates": dates, "source": source}))

    def test_morning_and_midday_use_last_completed_session(self):
        for clock in ("10:15:48", "11:40:00", "15:09:59"):
            with self.subTest(clock=clock):
                moment = datetime.fromisoformat("2026-10-15T" + clock).replace(tzinfo=TZ)
                dates = runner.resolve_dates(self.root, moment, "auto")
                self.assertEqual(dates["market_date"], "2026-10-14")
                self.assertEqual(dates["previous_session"], "2026-10-13")

    def test_explicit_same_day_rejected_before_close_even_for_close_phase(self):
        moment = datetime(2026, 10, 15, 10, 15, tzinfo=TZ)
        with self.assertRaisesRegex(ValueError, "not_a_completed"):
            runner.resolve_dates(self.root, moment, "close", "2026-10-15")

    def test_post_close_grace_boundary_accepts_today(self):
        moment = datetime(2026, 10, 15, 15, 10, tzinfo=TZ)
        dates = runner.resolve_dates(self.root, moment, "auto")
        self.assertEqual(dates["market_date"], "2026-10-15")
        self.assertEqual(dates["phase"], "close")

    def test_weekend_uses_friday_and_cannot_make_weekend_a_session(self):
        moment = datetime(2026, 10, 17, 21, 0, tzinfo=TZ)
        dates = runner.resolve_dates(self.root, moment, "close")
        self.assertEqual(dates["market_date"], "2026-10-16")
        self.assertFalse(dates["is_trading_day"])
        with self.assertRaisesRegex(ValueError, "not_a_completed"):
            runner.resolve_dates(self.root, moment, "close", "2026-10-17")

    def test_unverified_calendar_and_out_of_range_are_rejected(self):
        moment = datetime(2026, 10, 15, 10, 0, tzinfo=TZ)
        self.write_calendar(["2026-10-14", "2026-10-15", "2026-10-16"], source="fallback_weekdays")
        with self.assertRaisesRegex(ValueError, "verified_trade_calendar_missing"):
            runner.resolve_dates(self.root, moment, "auto")
        self.write_calendar(["2026-10-12", "2026-10-13", "2026-10-14"])
        with self.assertRaisesRegex(ValueError, "out_of_range"):
            runner.resolve_dates(self.root, moment, "auto")


class RecordClassificationTests(unittest.TestCase):
    def assemble(self, listing=None, evidence=None, quote=None):
        return runner.assemble_record(listing or stock(), evidence or history(), TARGET,
                                      CONFIG, sessions_ending(), quote)

    def test_new_ipo_not_listed_at_target_excluded_even_if_history_request_failed(self):
        result = self.assemble(stock("301569", "SZ", board="chinext", name="N联亚药业",
                                     listing_date="2026-10-15"),
                               {"fetch_status": "failed", "bars": [], "errors": ["no_history_yet"]})
        self.assertEqual(result["status"], "excluded")
        self.assertEqual(result["reasons"], ["not_listed_at_target_date"])
        self.assertFalse(result["ranking"]["eligible"])

    def test_st_exclusion_does_not_depend_on_history_endpoint_success(self):
        result = self.assemble(stock(name="*ST测试"), {"fetch_status": "failed", "bars": []})
        self.assertEqual(result["status"], "excluded")
        self.assertEqual(result["reasons"], ["risk_warning_name"])

    def test_stale_history_without_target_quote_remains_unresolved(self):
        evidence = history(sessions_ending("2026-10-13"))
        result = self.assemble(evidence=evidence)
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["reasons"], ["missing_target_session_bar"])
        self.assertNotIn("suspension", " ".join(result["reasons"]))

    def test_todays_no_trade_quote_cannot_prove_previous_day_was_suspended(self):
        evidence = history(sessions_ending("2026-10-13"))
        result = self.assemble(evidence=evidence,
                               quote={"date": "2026-10-15", "status": "no_trades"})
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["reasons"], ["missing_target_session_bar"])

    def test_exact_target_no_trade_evidence_is_explicit_exclusion(self):
        result = self.assemble(evidence=history(sessions_ending("2026-10-13")),
                               quote={"date": TARGET, "status": "no_trades"})
        self.assertEqual(result["status"], "excluded")
        self.assertEqual(result["reasons"], ["no_trades_on_target_session"])

    def test_short_history_for_old_stock_is_unexplained_gap(self):
        result = self.assemble(evidence=history(sessions_ending(count=40)))
        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["reasons"], ["truncated_history_unexplained"])

    def test_short_history_is_allowed_only_for_provably_new_listing(self):
        days = sessions_ending(count=40)
        result = self.assemble(stock(listing_date=days[0]), history(days))
        self.assertEqual(result["status"], "excluded")
        self.assertEqual(result["reasons"], ["new_listing_insufficient_completed_history"])

    def test_detected_corporate_action_never_enters_candidate_queue(self):
        result = self.assemble(evidence=history(source={"corporate_action_basis_change": True}))
        self.assertEqual(result["status"], "screened")
        self.assertFalse(result["ranking"]["eligible"])
        self.assertEqual(result["ranking"]["reasons"], ["corporate_action_price_basis_review_required"])


class PublicationAccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.universe = [stock(), stock("000001", "SZ")]
        self.records = [{"code": s["code"], "name": s["name"], "exchange": s["exchange"],
                         "status": "screened", "ranking": {"eligible": False},
                         "update_method": "fixture"} for s in self.universe]

    def publish(self, run_id, *, market_date=TARGET, records=None, fresh=True):
        run_dir = self.root / "output/boll/archive" / market_date / run_id
        run_dir.mkdir(parents=True)
        return runner.publish(
            self.root, run_dir, self.records if records is None else records, self.universe,
            {"fresh": fresh, "version_date": "2026-10-15"},
            {"market_date": market_date, "report_date": "2026-10-15", "phase": "early",
             "is_trading_day": True}, {}, {}, "2026-10-15T10:15:00+08:00", 1.0, CONFIG)

    def manifest(self):
        return json.loads((self.root / "output/boll/latest/manifest.json").read_text())

    def test_exact_codes_and_counts_allow_complete_screen(self):
        summary = self.publish("complete")
        self.assertTrue(summary["all_codes_accounted_for"])
        self.assertTrue(summary["technical_screen_complete"])
        manifest = self.manifest()
        path = self.root / manifest["latest_screen"]["selected_file"]
        self.assertEqual(manifest["latest_screen"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_missing_substituted_or_duplicate_codes_cannot_pass_accounting(self):
        substituted = deepcopy(self.records)
        substituted[1]["code"] = "000002"
        cases = [self.records[:1], substituted, self.records + self.records[:1],
                 [deepcopy(self.records[0]), deepcopy(self.records[0])]]
        for index, rows in enumerate(cases):
            with self.subTest(index=index):
                summary = self.publish(f"bad-accounting-{index}", records=rows)
                self.assertFalse(summary["all_codes_accounted_for"])
                self.assertFalse(summary["technical_screen_complete"])

    def test_unrefreshed_universe_cannot_claim_complete_even_with_all_codes(self):
        summary = self.publish("stale-universe", fresh=False)
        self.assertTrue(summary["all_codes_accounted_for"])
        self.assertFalse(summary["technical_screen_complete"])

    def test_later_incomplete_same_date_preserves_accepted_complete(self):
        self.publish("20261015T100000-early")
        incomplete = deepcopy(self.records)
        incomplete[1].update(status="unresolved", reasons=["timeout"])
        summary = self.publish("20261015T101000-early", records=incomplete)
        self.assertFalse(summary["technical_screen_complete"])
        manifest = self.manifest()
        self.assertEqual(manifest["latest_screen"]["run_id"], "20261015T100000-early")
        self.assertEqual(manifest["latest_complete_screen"]["run_id"], "20261015T100000-early")
        self.assertEqual(manifest["last_attempt"]["run_id"], "20261015T101000-early")

    def test_older_market_date_cannot_replace_newer_complete_screen(self):
        self.publish("newer-complete", market_date="2026-10-15")
        self.publish("older-attempt", market_date=TARGET, records=self.records[:1])
        manifest = self.manifest()
        self.assertEqual(manifest["latest_screen"]["run_id"], "newer-complete")
        self.assertEqual(manifest["latest_complete_screen"]["run_id"], "newer-complete")
        self.assertEqual(manifest["last_attempt"]["run_id"], "older-attempt")

    def test_new_date_partial_advances_latest_but_retains_prior_complete(self):
        self.publish("prior-complete", market_date=TARGET)
        self.publish("new-date-partial", market_date="2026-10-15", records=self.records[:1])
        manifest = self.manifest()
        self.assertEqual(manifest["latest_screen"]["run_id"], "new-date-partial")
        self.assertEqual(manifest["latest_complete_screen"]["run_id"], "prior-complete")


if __name__ == "__main__":
    unittest.main()
