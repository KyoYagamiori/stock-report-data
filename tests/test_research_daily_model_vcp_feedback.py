import gzip
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from market_screen.history import canonical_bytes, write_json
from research_system.daily_model_report_feedback import READER as REPORT_READER, STATE as REPORT_STATE, normalize_plan
from research_system.daily_model_vcp_feedback import (PRICES, STATE, check_conditions, market_time,
    minute_day, price_events, run)


DAY = "2026-11-20"
NEXT = "2026-11-23"
CODE = "600970"


def tape():
    starts = (("09:31", 120), ("13:01", 117), ("15:00", 1))
    return [{"day": (market_time(DAY, start) + timedelta(minutes=i)).isoformat(),
             "open": 8, "high": 8, "low": 8, "close": 8, "volume": 100}
            for start, length in starts for i in range(length)]


def aggregate(rows):
    return {"day": DAY, "open": rows[0]["open"], "close": rows[-1]["close"],
            "high": max(row["high"] for row in rows), "low": min(row["low"] for row in rows),
            "volume": sum(row["volume"] for row in rows)}


class VcpMinuteFeedbackTests(unittest.TestCase):
    def setUp(self):
        workspace = TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        self.rows = tape()
        self.plan = normalize_plan({"action": "wait", "valid_until": f"{NEXT}T15:00:00+08:00",
            "buy_low": 8.1, "buy_high": 8.2, "reduce_low": 8.3, "reduce_high": 8.4, "stop": 7.8,
            "vcp_checks": {"daily_breakout": {"pivot": 8.09, "min_volume_shares": 10_000},
                           "stop_below_15m": True, "reduce_after_band_below_15m": True}},
            market_time(DAY, "09:40"))

    def change_prices(self, clock, **prices):
        row = next(row for row in self.rows if row["day"][11:16] == clock)
        row.update(**prices)

    def setup_run(self, *, late=False):
        write_json(self.root / "output/cache/trade_calendar.json",
                   {"source": "verified_fixture", "trade_dates": ["2026-11-19", DAY, NEXT, "2026-11-24"]})
        daily = [aggregate(self.rows)]
        payload = {"code": CODE, "adjustment": "unadjusted", "bars": daily,
                   "history_sha256": hashlib.sha256(canonical_bytes(daily)).hexdigest()}
        compressed = gzip.compress(canonical_bytes(payload) + b"\n", mtime=0)
        path = self.root / "output/boll/bootstrap"
        write_json(path / "manifest.json", {"adjustment": "unadjusted", "market_date": DAY, "record_count": 1,
                                          "sha256": hashlib.sha256(compressed).hexdigest()})
        (path / "history.jsonl.gz").write_bytes(compressed)
        calls = {}
        for phase, issued, seen in (("manual", "09:40", "15:06" if late else "10:00"), ("noon", "12:45", "12:49")):
            calls[phase] = {"signal_id": phase, "code": CODE, "roles": ["vcp"], "phase": phase,
                            "check_day": DAY, "issued_at": market_time(DAY, issued).isoformat(),
                            "seen_at": market_time(DAY, seen).isoformat(), "plan": self.plan,
                            "source": f"reports/forecasts/2026/11/20/{phase}.json", "source_sha256": "a" * 64}
        write_json(self.root / REPORT_STATE, {"calls": calls, "sources": {}})
        write_json(self.root / REPORT_READER, {"version": "existing_close_feedback"})

    def provider(self, code):
        self.assertEqual(CODE, code)
        return b"var data=(" + json.dumps(self.rows).encode() + b");", market_time(DAY, "15:06")

    def test_daily_reconciliation_and_incomplete_minute_rejection(self):
        daily = aggregate(self.rows)
        self.assertEqual(238, len(minute_day(self.rows, DAY, daily)))
        with self.assertRaisesRegex(ValueError, "complete_session"):
            minute_day(self.rows[:-1], DAY, daily)
        with self.assertRaisesRegex(ValueError, "reconcile"):
            minute_day(self.rows, DAY, {**daily, "volume": daily["volume"] + 1})

    def test_respects_publication_boundaries_and_later_completed_close(self):
        self.change_prices("09:31", **{key: 8.15 for key in PRICES})
        self.change_prices("10:01", high=8.31)
        self.change_prices("10:15", **{key: 8.15 for key in PRICES})
        self.change_prices("13:15", **{key: 7.75 for key in PRICES})
        bars = minute_day(self.rows, DAY, aggregate(self.rows))
        events = price_events([bars], self.plan, market_time(DAY, "09:29"), market_time(DAY, "14:45"))
        self.assertEqual("10:15", events["buy_band_price"]["at"][11:16])
        self.assertEqual("10:01", events["reduce_band_price"]["at"][11:16])
        self.assertEqual("13:15", events["completed_15m_close_below_stop"]["at"][11:16])
        checks = check_conditions(self.plan, events, aggregate(self.rows), {})
        self.assertEqual("observed", checks["reduce_after_band_below_15m"]["state"])
        self.assertEqual("not_met", checks["daily_breakout"]["state"])
        events["first_completed_15m_close_after_reduce_band"]["at"] = events["reduce_band_price"]["at"]
        checks = check_conditions(self.plan, events, aggregate(self.rows), {})
        self.assertEqual("order_unverified_within_bar", checks["reduce_after_band_below_15m"]["state"])

    def test_reuses_one_verified_source_for_two_forward_windows(self):
        self.change_prices("10:35", high=8.33)
        self.change_prices("13:15", **{key: 7.75 for key in PRICES})
        self.setup_run()
        codes = []

        def fetch(code):
            codes.append(code)
            return self.provider(code)

        pending = run(self.root, market_time(DAY, "14:50"), fetcher=fetch)
        self.assertEqual({"waiting_for_close": 2}, pending["statuses"])
        self.assertEqual([], codes)
        reader = run(self.root, market_time(DAY, "15:15"), fetcher=fetch)
        self.assertEqual([CODE], codes)
        self.assertEqual(1, reader["verified_security_sessions"])
        self.assertEqual({"window_open": 2}, reader["statuses"])
        by_phase = {row["phase"]: row for row in reader["recent_calls"]}
        self.assertIn("reduce_band_price", by_phase["manual"]["price_events"])
        self.assertNotIn("reduce_band_price", by_phase["noon"]["price_events"])
        self.assertEqual([NEXT], by_phase["noon"]["pending_days"])
        self.assertEqual(0, reader["formal_training_rows"])
        again = run(self.root, market_time(DAY, "16:00"), fetcher=fetch)
        self.assertEqual([CODE], codes)
        self.assertEqual(by_phase, {row["phase"]: row for row in again["recent_calls"]})
        self.assertIn("vcp_minute_feedback", json.loads((self.root / REPORT_READER).read_text()))

    def test_failed_source_retries_with_no_post_close_backdating(self):
        self.setup_run(late=True)
        calls = []

        def missing(code):
            calls.append(code)
            raise OSError("temporary minute gap")

        first = run(self.root, market_time(DAY, "15:06"), fetcher=missing)
        self.assertEqual({"data_gap": 1, "publication_window_unverified": 1}, first["statuses"])
        run(self.root, market_time(DAY, "15:15"), fetcher=missing)
        self.assertEqual([CODE], calls)
        recovered = run(self.root, market_time(DAY, "16:00"), fetcher=self.provider)
        self.assertEqual({"window_open": 1, "publication_window_unverified": 1}, recovered["statuses"])
        self.assertEqual({}, json.loads((self.root / STATE).read_text())["attempts"])


if __name__ == "__main__":
    unittest.main()
