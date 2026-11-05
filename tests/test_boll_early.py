from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_screen.early import build, classify, evaluate, project
from market_screen.early_runtime import hydrate_states, run, update_observations
from market_screen.technicals import calculate, rank_candidate
from tests.test_boll_runner import CONFIG, history, stock, TARGET, TZ

NOW = datetime(2026, 10, 15, 10, 0, tzinfo=TZ)
DATES = {"phase": "intraday", "market_date": TARGET, "report_date": "2026-10-15"}


def record(code="600000"):
    bars = history()["bars"]
    for b in bars:
        b.update(open=10., high=10.2, low=9.8, close=10.)
    bars[-1].update(close=9.99)
    i = calculate(bars, TARGET)
    return {**stock(code), "status": "screened", "market_date": TARGET, "source": {},
            "indicators": i, "ranking": rank_candidate(stock(code), i, CONFIG)}


def quote(code="600000", **changes):
    return {"code": code, "name": "测试股份", "status": "valid", "date": "2026-10-15", "time": "10:00:00",
            "open": 10., "high": 10.1, "low": 9.98, "close": 10.05, "prev_close": 9.99,
            "volume": 1000000., "amount": 10000000., **changes}


def point(n, **changes):
    return {"day": f"2026-10-{n:02}", "open": 10., "high": 10.8, "low": 9.9, "close": 9.9,
            "mid": 10., "upper": 10.5, "lower": 9.5, "width": .1, "atr20": 1.,
            "mid_slope_5d_atr": .01, "width_percentile": .5, "contraction_origin": None, **changes}


class EarlyDiscoveryTests(unittest.TestCase):
    def test_dynamic_band_matches_direct_calculation_without_mutating_daily(self):
        r = record()
        baseline = deepcopy(r)
        q = quote()
        points = project(r["indicators"]["early_state"], q)
        bars = history()["bars"]
        for b in bars: b.update(open=10., high=10.2, low=9.8, close=10.)
        bars[-1]["close"] = 9.99
        bars.append({"day": q["date"], **{k: q[k] for k in ("open", "high", "low", "close", "volume", "amount")}})
        direct = calculate(bars, q["date"])
        for k in ("mid", "upper", "lower", "width"):
            self.assertAlmostEqual(direct["boll"][k], points[-1][k], places=12)
        self.assertAlmostEqual(direct["research_features"]["atr20"], points[-1]["atr20"])
        self.assertEqual(baseline, r)

    def test_today_new_reclaim_can_enter_when_yesterdays_v1_did_not(self):
        r = record()
        self.assertFalse(r["ranking"]["eligible"])
        out = evaluate(r, DATES, NOW, CONFIG, quote())
        self.assertTrue(out["structure_eligible"])
        self.assertEqual("initial_reclaim", out["stage"])
        self.assertEqual(0, out["setups"][0]["signal_age_sessions"])
        self.assertFalse(out["entry_qualified"])
        self.assertEqual("provisional", out["band_status"])
        self.assertIn("completed_5_15_minute_confirmation_unavailable", out["evidence_gaps"])

    def test_old_reclaim_is_not_relabelled_as_fresh_opportunity(self):
        points = [point(n) for n in range(1, 7)]
        for p in points[2:]: p["close"] = 10.2
        setups, stage, _ = classify(points)
        self.assertFalse(setups)
        self.assertEqual("mature_extension", stage)

    def test_first_retest_qualifies_but_second_retest_does_not(self):
        points = [point(1), point(2, close=10.2), point(3, close=11., low=10.5),
                  point(4, close=10.4, low=10.38), point(5, close=10.5, low=10.1)]
        self.assertIn("first_mid_retest", [s["pool"] for s in classify(points)[0]])
        points[3]["low"] = 10.1
        self.assertNotIn("first_mid_retest", [s["pool"] for s in classify(points)[0]])

    def test_basing_before_advancement_is_not_a_prior_retest(self):
        points = [point(1), point(2, close=10.2), point(3, close=10.25, low=10.05),
                  point(4, close=11., low=10.6), point(5, open=10.2, close=10.5, low=10.1)]
        self.assertLess(points[-1]["close"], points[-2]["close"])
        self.assertIn("first_mid_retest", [s["pool"] for s in classify(points)[0]])

    def test_prepare_has_no_direction_confirmation(self):
        points = [point(1, width=.09), point(2, width=.08),
                  point(3, width=.07, width_percentile=.2, contraction_origin="2026-10-01")]
        setups, stage, _ = classify(points)
        self.assertEqual("preparing", stage)
        self.assertEqual("squeeze_prepare", setups[0]["pool"])

    def test_first_expansion_accepts_lower_rail_down_and_rejects_next_day(self):
        points = [point(1, width=.06, width_percentile=.1), point(2, close=10.1, upper=10.25, width=.04, width_percentile=.1),
                  point(3, close=10.36, upper=10.35, lower=9.4, width=.05, width_percentile=.3)]
        self.assertIn("first_expansion", [s["pool"] for s in classify(points)[0]])
        points.append(point(4, close=10.45, upper=10.5, lower=9.3, width=.06))
        self.assertNotIn("first_expansion", [s["pool"] for s in classify(points)[0]])

    def test_stale_future_and_afternoon_as_noon_are_rejected(self):
        for q, d in ((quote(time="09:55:00"), DATES), (quote(time="10:01:00"), DATES),
                     (quote(time="13:00:00"), {**DATES, "phase": "noon"})):
            self.assertFalse(evaluate(record(), d, NOW, CONFIG, q)["structure_eligible"])

    def test_known_basis_conflict_is_a_hard_gate(self):
        for source in (True, False):
            r, q = record(), quote()
            if source: r["source"]["corporate_action_basis_change"] = True
            else: q["prev_close"] = 9.5
            self.assertFalse(evaluate(r, DATES, NOW, CONFIG, q)["structure_eligible"])

    def test_mid_turn_threshold_is_an_algebraic_condition(self):
        state = record()["indicators"]["early_state"]
        threshold = state["closes"][-20]
        old_mid = state["points"][-1]["mid"]
        self.assertGreater(project(state, quote(close=threshold + .1))[-1]["mid"], old_mid)
        self.assertLess(project(state, quote(close=threshold - .1))[-1]["mid"], old_mid)

    def test_duplicate_codes_rejected_and_untrained_status_is_explicit(self):
        r = record()
        with self.assertRaises(ValueError): build([r, r], DATES, NOW, CONFIG)
        data = build([r], DATES, NOW, CONFIG, {r["code"]: quote()})
        self.assertEqual([r["code"]], [x["code"] for x in data["shortlist"]])
        self.assertFalse(data["probabilities_enabled"])

    def test_original_window_does_not_reset_on_repeated_reports_or_expiry(self):
        data = build([record()], DATES, NOW, CONFIG, {"600000": quote()})
        calendar = ["2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"]
        state = update_observations(data, {}, calendar, NOW)
        original = deepcopy(next(iter(state["episodes"].values())))
        repeated = build([record()], DATES, NOW, CONFIG, {"600000": quote()})
        update_observations(repeated, state, calendar, NOW + timedelta(hours=2))
        ep = next(iter(state["episodes"].values()))
        self.assertEqual(original["first_seen_at"], ep["first_seen_at"])
        self.assertEqual(original["valid_until"], ep["valid_until"])
        expired = build([record()], DATES, NOW, CONFIG, {"600000": quote()})
        update_observations(expired, state, calendar, NOW + timedelta(days=8))
        self.assertFalse(expired["shortlist"])
        self.assertEqual(1, len(state["episodes"]))

    def test_legacy_state_without_raw_evidence_stays_unavailable(self):
        r = record()
        del r["indicators"]["early_state"]
        with tempfile.TemporaryDirectory() as d:
            out = hydrate_states(Path(d), [r], TARGET)
        self.assertEqual(1, out["unavailable"])
        self.assertNotIn("early_state", r["indicators"])

    def test_live_runtime_freezes_hash_bound_queue_and_discloses_partial_quotes(self):
        for stale in (False, True):
            with self.subTest(stale=stale), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / "config").mkdir()
                (root / "output/cache").mkdir(parents=True)
                (root / "config/boll_screen.json").write_text(json.dumps(CONFIG))
                (root / "config/early_signals.json").write_text('{"target_refresh_seconds":300}')
                dates = ["2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"]
                (root / "output/cache/trade_calendar.json").write_text(json.dumps({"source":"test_fixture","trade_dates":dates}))
                q = quote(time="09:55:00") if stale else quote()
                with patch("market_screen.completed_source.load_completed_records", return_value=({"600000":record()}, {"accepted":True}, None)), \
                     patch("market_screen.membership.read_frozen_universe", return_value=([stock()], {})):
                    result = run(root, NOW, quote_collector=lambda *a, **k:
                        ({"600000": q}, {"fixture":True, "large_audit":["x"*1000]*20}))
                self.assertEqual("partial" if stale else "complete", result["status"])
                raw = (root / result["selected_file"]).read_bytes()
                self.assertEqual(result["sha256"], hashlib.sha256(raw).hexdigest())
                data = json.loads(raw)
                self.assertLess(len(json.dumps(data["quote_source"])), 1000)
                audit = (root / data["quote_source"]["file"]).read_bytes()
                self.assertEqual(data["quote_source"]["sha256"], hashlib.sha256(audit).hexdigest())
                self.assertEqual(20, len(json.loads(audit)["large_audit"]))
                self.assertEqual(0 if stale else 1, len(data["shortlist"]))
                self.assertEqual(1 if stale else 0, result["coverage"]["quote_gaps"])


if __name__ == "__main__":
    unittest.main()
