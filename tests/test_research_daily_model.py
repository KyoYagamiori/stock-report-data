from copy import deepcopy
from datetime import datetime, timedelta
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_screen.history import canonical_bytes, write_json
from market_screen.vcp import FEATURES as VCP_FEATURES
from research_system.daily_model import (FEATURES, VERSION, candidates, ensure_models, immutable,
    load_calendar, load_queue, register, score_rows, verify_predictions, validate_completed_screen)
from research_system.daily_model_data import (checked, feedback, load_bars, next_entry, price_outcome,
    settle, summarize)

NOW = datetime.fromisoformat("2026-11-17T10:40:00+08:00")
CALENDAR = ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20",
            "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26", "2026-11-27", "2026-11-30"]


def sample(code="600000"):
    return {"code": code, "name": "公开样本", "date": "2026-11-16", "setup": "fresh_mid_reclaim",
        "origin": "2026-11-16", "features": {f: .1 for f in FEATURES}, "price": 10,
        "price_asof": "2026-11-16T15:00:00+08:00", "stage": "fresh", "vcp_stage": "no_vcp_setup",
        "exit_plan": {"initial_defense_price": 9.5}, "target_t3_net_excess_pct": 0}


def bar(day, close=10, volume=1e6):
    return {"day": day, "open": 10, "high": max(close, 10) + .2, "low": min(close, 10) - .2,
            "close": close, "volume": volume}


class DailyModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = json.loads((Path(__file__).resolve().parents[1] / "config/daily_model.json").read_text())

    def test_prediction_opportunity_is_frozen_across_reruns_and_expiry(self):
        row = sample()
        row.update(scores={"lightgbm": .2, "ridge": -.1}, ranks={"lightgbm": 1, "ridge": 1, "early_rule": 1}, selected_by=["lightgbm", "ridge", "early_rule"])
        state, model, source = {}, {"sha256": "a" * 64}, {"sha256": "b" * 64}
        first = register(self.root, [row], state, model, source, CALENDAR, NOW, self.config)
        original = deepcopy(state)
        modified = deepcopy(row)
        modified["scores"]["lightgbm"] = 999
        second = register(self.root, [modified], state, model, source, CALENDAR, NOW + timedelta(days=1), self.config)
        self.assertEqual(1, len(first))
        self.assertEqual([], second)
        self.assertEqual(original, state)
        self.assertEqual(.2, modified["original_scores"]["lightgbm"])
        self.assertEqual("2026-11-18", modified["original_prediction"]["entry_date"])

    def test_new_model_version_creates_separate_predictions_without_replacing_old(self):
        row = sample()
        row.update(scores={"lightgbm": 0}, ranks={}, selected_by=[])
        state = {}
        for digest in ("a" * 64, "c" * 64):
            register(self.root, [deepcopy(row)], state, {"sha256": digest}, {"sha256": "b" * 64}, CALENDAR, NOW, self.config)
        self.assertEqual(2, len(state["episodes"]))

    def test_next_open_is_strictly_future_with_publication_margin(self):
        self.assertEqual("2026-11-18", next_entry(CALENDAR, NOW, 30))
        self.assertEqual("2026-11-18", next_entry(CALENDAR, NOW.replace(hour=9, minute=5), 30))
        self.assertEqual("2026-11-17", next_entry(CALENDAR, NOW.replace(hour=8), 30))

    def test_future_dates_and_unknown_calendar_are_rejected(self):
        write_json(self.root / "output/cache/trade_calendar.json", {"trade_dates": CALENDAR, "source": "weekday_fallback"})
        with self.assertRaisesRegex(ValueError, "calendar_unverified"):
            load_calendar(self.root, NOW)

    def test_completed_daily_evidence_accepts_early_producer_but_not_noon_overlay(self):
        screen = {"market_date": "2026-11-16", "market_cutoff": "2026-11-16T15:00:00+08:00",
            "published_at": "2026-11-16T16:10:00+08:00", "phase": "early",
            "technical_screen_complete": True, "unresolved_count": 0, "all_codes_accounted_for": True}
        validate_completed_screen(screen, NOW)
        for change in ({"phase": "noon"}, {"phase": "intraday"}, {"unresolved_count": 1},
                {"market_cutoff": "2026-11-16T11:30:00+08:00"}, {"all_codes_accounted_for": False},
                {"published_at": "2026-11-16T14:59:00+08:00"},
                {"published_at": "2026-11-17T16:10:00+08:00"}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "completed_verified_daily"):
                validate_completed_screen({**screen, **change}, NOW)

    def test_source_reader_rejects_mixed_dates_before_rebuilding_candidates(self):
        day = "2026-11-16"
        directory = self.root / "output/boll/archive" / day / "test"
        queue = {"market_date": day, "phase": "early", "published_at": day + "T16:10:00+08:00",
            "pool_codes": {"fresh_mid_reclaim": ["600000"]}}
        qref = immutable(self.root, directory / "early_queue.json", queue)
        record = {"code": "600000", "market_date": day, "indicators": {"bar_date": day,
            "last_bar": {"day": day}, "history_current": True,
            "early_state": {"asof": day, "points": [{"day": "2026-11-13"}]}}}
        rref = immutable(self.root, directory / "records/600000-600000.json", {"records": [record]})
        screen = {"market_date": day, "market_cutoff": day + "T15:00:00+08:00", "phase": "early",
            "published_at": queue["published_at"], "all_codes_accounted_for": True,
            "technical_screen_complete": True, "unresolved_count": 0,
            "early_signals": {"reader_file": qref["file"], "reader_sha256": qref["sha256"]},
            "record_shards": [{**rref, "count": 1}]}
        sref = immutable(self.root, directory / "screen.json", screen)
        write_json(self.root / "output/boll/latest/manifest.json", {"latest_complete_screen": {
            "selected_file": sref["file"], "sha256": sref["sha256"]}})
        with self.assertRaisesRegex(ValueError, "candidate_daily_date_mismatch"):
            load_queue(self.root, NOW, CALENDAR)

    def test_source_byte_hash_and_path_are_verified(self):
        path = self.root / "output/research/daily_model/models/test.json"
        ref = immutable(self.root, path, {"public": True})
        self.assertTrue(checked(self.root, ref, "output/research/daily_model/models"))
        path.write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "hash_mismatch"):
            checked(self.root, ref, "output/research/daily_model/models")
        with self.assertRaisesRegex(ValueError, "source_path_invalid"):
            checked(self.root, {"file": "../outside", "sha256": "a" * 64}, "output/research")

    def test_own_seed_checks_each_code_hash_and_keeps_real_date_range(self):
        bars = [bar("2026-11-16")]
        payload = {"code": "600000", "adjustment": "unadjusted", "bars": bars,
                   "history_sha256": hashlib.sha256(canonical_bytes(bars)).hexdigest()}
        directory = self.root / "output/boll/bootstrap"
        directory.mkdir(parents=True)
        raw = gzip.compress(canonical_bytes(payload) + b"\n", mtime=0)
        (directory / "history.jsonl.gz").write_bytes(raw)
        write_json(directory / "manifest.json", {"adjustment": "unadjusted", "market_date": "2026-11-16",
            "record_count": 1, "sha256": hashlib.sha256(raw).hexdigest()})
        loaded, receipt = load_bars(self.root, {"600000"}, NOW)
        self.assertEqual("2026-11-16", receipt["earliest_bar"])
        self.assertEqual(10, loaded["600000"]["2026-11-16"]["close"])
        payload["bars"][0]["close"] = 10.1
        raw = gzip.compress(canonical_bytes(payload) + b"\n", mtime=0)
        (directory / "history.jsonl.gz").write_bytes(raw)
        write_json(directory / "manifest.json", {"adjustment": "unadjusted", "market_date": "2026-11-16",
            "record_count": 1, "sha256": hashlib.sha256(raw).hexdigest()})
        with self.assertRaisesRegex(ValueError, "bar_hash_mismatch"):
            load_bars(self.root, {"600000"}, NOW)

    def test_no_same_day_exit_or_outcome_before_completed_close(self):
        ep = {"entry_date": "2026-11-18"}
        tape = {d: bar(d) for d in CALENDAR}
        self.assertEqual("pending", price_outcome(ep, tape, CALENDAR, 1,
            datetime.fromisoformat("2026-11-18T16:00:00+08:00"), 20)["state"])
        result = price_outcome(ep, tape, CALENDAR, 1, datetime.fromisoformat("2026-11-19T15:06:00+08:00"), 20)
        self.assertEqual("2026-11-19", result["exit_date"])
        self.assertAlmostEqual(-.2, result["price_net_return_pct"])
        self.assertIsNone(result["net_excess_pct"])

    def test_missing_entry_exit_or_path_never_becomes_cash_zero(self):
        ep = {"entry_date": "2026-11-18"}
        tape = {d: bar(d) for d in CALENDAR}
        later = datetime.fromisoformat("2026-11-30T16:00:00+08:00")
        for missing, expected in (("2026-11-18", "unresolved_entry"), ("2026-11-23", "unresolved_exit"),
                                  ("2026-11-19", "unresolved_path_gap")):
            changed = {d: b for d, b in tape.items() if d != missing}
            result = price_outcome(ep, changed, CALENDAR, 3, later, 20)
            self.assertEqual(expected, result["state"])
            self.assertNotIn("price_net_return_pct", result)

    def test_matured_feedback_cannot_claim_verified_trades_or_excess_training(self):
        ep = {**sample(), "signal_id": "public", "model_sha256": "a" * 64, "feature_date": "2026-11-16",
            "entry_date": "2026-11-18", "prediction_registered_at": NOW.isoformat(),
            "public_available_by": NOW.isoformat(), "outcomes": {}}
        tape = {d: bar(d) for d in CALENDAR}
        later = datetime.fromisoformat("2026-11-30T16:00:00+08:00")
        settle({"public": ep}, {ep["code"]: tape}, CALENDAR, later, self.config, {"sha256": "b" * 64})
        rows = feedback({"public": ep})
        self.assertEqual(1, len(rows))
        self.assertFalse(rows[0]["eligible_for_formal_training"])
        self.assertIsNone(rows[0]["target_t3_net_excess_pct"])
        frozen = deepcopy(ep["outcomes"])
        tape["2026-11-23"]["close"] = 20
        settle({"public": ep}, {ep["code"]: tape}, CALENDAR, later, self.config, {})
        self.assertEqual(frozen, ep["outcomes"])

    def test_publication_after_entry_is_excluded_instead_of_backdated(self):
        ep = {**sample(), "signal_id": "public", "entry_date": "2026-11-18", "outcomes": {},
              "public_available_by": "2026-11-18T10:00:00+08:00"}
        settle({"public": ep}, {}, CALENDAR, NOW + timedelta(days=1), self.config, {})
        self.assertEqual("excluded_publication_not_verified_before_entry", ep["outcomes"]["3"]["state"])
        self.assertNotIn("price_net_return_pct", ep["outcomes"]["3"])

    def test_mutating_state_cannot_rewrite_original_prediction(self):
        row = sample()
        row.update(scores={"lightgbm": .2}, ranks={}, selected_by=[])
        state = {}
        register(self.root, [row], state, {"sha256": "a" * 64}, {"sha256": "b" * 64}, CALENDAR, NOW, self.config)
        next(iter(state["episodes"].values()))["reference_price"] = 99
        with self.assertRaisesRegex(ValueError, "prediction_was_modified"):
            verify_predictions(self.root, state["episodes"], NOW)

    def test_out_of_domain_and_intraday_rows_are_not_scored_as_daily(self):
        source = sample()
        source.update(band_status="completed", structure_eligible=True,
            setups=[{"pool": source["setup"], "origin": source["origin"], "signal_age_sessions": 0}],
            vcp_shadow={"available": True, "stage": "no_vcp_setup"})
        alternate = deepcopy(source)
        alternate["code"] = "688700"
        unfinished = deepcopy(source)
        unfinished.update(code="600001", band_status="provisional")
        rows, gaps, count = candidates({"market_date": "2026-11-16", "pools": {source["setup"]: [source, alternate, unfinished]}}, self.config)
        self.assertEqual(["600000"], [r["code"] for r in rows])
        self.assertEqual(3, count)
        self.assertEqual(2, sum(gaps.values()))

    def test_incompatible_relative_market_and_scale_sensitive_alpha_excluded(self):
        self.assertNotIn("relative_market_5d_pct", FEATURES)
        self.assertNotIn("relative_market_20d_pct", FEATURES)
        self.assertNotIn("alpha101_101", FEATURES)
        self.assertTrue(set(VCP_FEATURES).issubset(FEATURES))

    def test_empty_trials_never_report_success_rate_or_promote(self):
        summary = summarize({})
        self.assertFalse(summary["production_activation"])
        self.assertNotIn("win_rate", summary)
        self.assertIsNone(summary["horizons"]["3"]["groups"]["lightgbm"]["date_balanced_price_net_return_pct"])

    def test_incomplete_different_setup_choices_cannot_form_paired_improvement(self):
        base = {"cohort_id": "same", "prediction_registered_at": NOW.isoformat(),
                "outcomes": {"3": {"state": "matured_price_proxy", "price_net_return_pct": 1}}}
        episodes = {"a": {**base, "setup": "fresh_mid_reclaim", "selected_by": ["lightgbm"]},
                    "b": {**base, "setup": "squeeze_prepare", "selected_by": ["early_rule"]}}
        result = summarize(episodes)["horizons"]["3"]
        self.assertEqual(0, result["paired_complete_cohorts"])
        self.assertIsNone(result["paired_model_minus_rule_price_proxy_pct"])

    @unittest.skipUnless(importlib.util.find_spec("lightgbm"), "optional training dependency is exercised by the daily-model workflow")
    def test_real_fit_purges_reviewed_and_future_labels(self):
        from tests.test_research_history_review import review_data
        data, policy = review_data()
        for row in data["rows"]:
            row["features"].update({name: .1 for name in VCP_FEATURES})
        config = deepcopy(self.config)
        config["exclude_reviewed_from"] = policy["previously_reviewed_start_date"]
        path = self.root / "output/history_pilot/experiments/test/dataset.json.gz"
        path.parent.mkdir(parents=True)
        raw = gzip.compress(canonical_bytes(data), mtime=0)
        path.write_bytes(raw)
        config["training_dataset"] = {"file": path.relative_to(self.root).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}
        _, artifact = ensure_models(self.root, config, NOW)
        self.assertLess(artifact["training_label_end"], artifact["validation_feature_start"])
        self.assertLess(artifact["validation_label_end"], config["exclude_reviewed_from"])
        self.assertEqual(list(FEATURES), artifact["models"]["lightgbm"]["features"])
        first = deepcopy(artifact)
        _, second = ensure_models(self.root, config, NOW + timedelta(days=1))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
