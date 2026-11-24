from datetime import date, timedelta
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_screen.history import write_json
from research_system import daily_model_retraining as training
from research_system.daily_model import FEATURES
from research_system.daily_model_data import checked, immutable
from research_system.ledger import stamp


class AutomaticRetrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {"automatic_retraining": True, "primary_model": "lightgbm", "round_trip_cost_bps": 20}
        start = date(2026, 1, 5)
        self.days = [(start + timedelta(days=i)).isoformat() for i in range(120)
                     if (start + timedelta(days=i)).weekday() < 5]
        self.now = stamp(self.days[69] + "T20:00:00+08:00")
        write_json(self.root / "config/model_release_policy.json",
                   {"minimum_forward_sessions": 60, "minimum_matured_signals": 100, "minimum_matured_signal_dates": 30})
        self.active = immutable(self.root, self.root / training.DATA / "models/current.json",
                                {"feature_names": list(FEATURES)})
        write_json(self.root / training.DATA / "active_model.json", self.active)

    def check(self, episodes):
        return training.run(self.root, self.config, episodes, self.days, self.now, proxy_rows=120)

    def add_qualifying_audits(self):
        refs = {kind: immutable(self.root, self.root / training.AUDITS / "sources" / (kind + ".json"),
                                {"fixture": kind}) for kind in training.EVIDENCE}
        episodes = {}
        for i, day in enumerate(self.days[:30]):
            for j in range(4):
                signal = f"{i}-{j}"
                code = f"60000{j}"
                registered = day + "T17:00:00+08:00"
                entry_day, exit_day = self.days[i + 1], self.days[i + 4]
                episode = {"signal_id": signal, "code": code, "model_sha256": self.active["sha256"],
                           "prediction_registered_at": registered, "public_available_by": registered,
                           "entry_date": entry_day, "cohort_id": day, "setup": "fresh_mid_reclaim",
                           "features": {k: (i + (j + 1) / 10) for k in FEATURES},
                           "scores": {"lightgbm": -j}, "prediction_file": {"sha256": "a" * 64}}
                episodes[signal] = episode
                write_json(self.root / training.AUDITS / (signal + ".json"),
                           {"schema_version": 1, "signal_id": signal, "prediction_sha256": "a" * 64,
                            "entry_date": entry_day, "exit_date": exit_day,
                            "label_known_at": exit_day + "T15:30:00+08:00",
                            "scope": "audited_public_market_execution", "round_trip_cost_bps": 20,
                            "benchmark_code": "000300", "gross_adjusted_stock_return_pct": (i % 5) + j / 10,
                            "gross_benchmark_return_pct": .2, "evidence": refs})
        return episodes, refs

    def test_price_proxies_do_not_count_towards_retraining(self):
        status = self.check({})
        self.assertEqual("waiting_for_qualified_feedback", status["status"])
        self.assertEqual(120, status["matured_price_proxy_rows"])
        self.assertEqual(0, status["qualified_rows"])
        self.assertNotIn("candidate", status)

    def test_corrupt_sources_prevent_labels_from_counting(self):
        episodes, refs = self.add_qualifying_audits()
        (self.root / refs["official_benchmark"]["file"]).write_text("modified")
        status = self.check(episodes)
        self.assertEqual(0, status["qualified_rows"])
        self.assertEqual(120, status["rejected_labels"]["daily_model_source_hash_mismatch"])
        self.assertNotIn("candidate", status)

    @unittest.skipUnless(importlib.util.find_spec("lightgbm"), "LightGBM runtime unavailable")
    def test_qualified_batch_fits_once_and_leaves_the_active_version_in_place(self):
        episodes, _ = self.add_qualifying_audits()
        result = self.check(episodes)
        self.assertEqual("research_candidate_trained", result["status"], result)
        self.assertEqual(120, result["qualified_rows"])
        self.assertEqual(30, result["qualified_signal_dates"])
        self.assertEqual(69, result["forward_sessions"])
        candidate_ref = result["candidate"]
        raw = checked(self.root, candidate_ref, training.CANDIDATES)
        candidate = json.loads(raw)
        self.assertEqual(2, len(candidate["rolling_development_folds"]))
        self.assertEqual({"lightgbm", "ridge"}, set(candidate["models"]))
        self.assertFalse(candidate["production_activation"])
        retried = self.check(episodes)
        self.assertEqual("candidate_in_forward_trial", retried["status"])
        self.assertEqual(0, retried["new_qualified_rows"])
        self.assertEqual(candidate_ref, retried["candidate"])
        self.assertEqual(self.active, json.loads((self.root / training.DATA / "active_model.json").read_bytes()))
        rows = [{**episodes["0-0"], "target_t3_net_excess_pct": 0}]
        with patch.object(training, "read_published", return_value=raw):
            training.attach_shadow_scores(self.root, rows, self.active, self.now)
        self.assertEqual(candidate_ref["sha256"], rows[0]["research_candidate"]["sha256"])
