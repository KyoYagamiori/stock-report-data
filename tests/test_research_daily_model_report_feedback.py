from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from research_system.daily_model_report_feedback import INPUT, due_codes, fit, register, settle
from research_system.ledger import stamp


DAY = "2026-11-20"
CALENDAR = ["2026-11-19", DAY, "2026-11-23"]


def at(clock):
    return stamp(f"{DAY}T{clock}:00+08:00")


class ReportForecastFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.git("init", "-q")
        self.state = {"sources": {}, "calls": {}}

    def git(self, *args):
        subprocess.run(["git", "-c", "user.name=Forecast Test", "-c", "user.email=test@example.invalid", *args],
                       cwd=self.root, check=True, capture_output=True)

    def publish(self, phase, issued, relation="below"):
        path = self.root / INPUT / "2026/11/20" / f"{phase}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "issued_at": at(issued).isoformat(), "calls": [
            {"code": "600970", "roles": ["vcp"], "check_day": DAY, "relation": relation, "price": 8.10,
             "reference_price": 7.92, "quote_asof": "2026-11-19T15:00:00+08:00", "etf_context": "mixed",
             "plan": {"action": "wait", "valid_until": "2026-11-23T15:00:00+08:00", "stop": 7.69,
                      "buy_low": 8.11, "buy_high": 8.21, "entry_rule": "日线收盘放量越过枢纽"}}]}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.git("add", path.relative_to(self.root).as_posix())
        self.git("commit", "-qm", "publish forecast")
        return path

    def test_forward_close_counts_and_revisions_do_not_duplicate_training(self):
        self.publish("early", "09:05")
        self.assertEqual(register(self.root, at("09:10"), CALENDAR, self.state), [])
        self.publish("noon", "12:45", relation="above")
        self.assertEqual(register(self.root, at("12:49"), CALENDAR, self.state), [])
        self.assertEqual(due_codes(self.state, at("14:55")), set())
        self.assertEqual(due_codes(self.state, at("15:05")), {"600970"})
        tape = {"600970": {DAY: {"day": DAY, "close": 7.97, "volume": 1000}}}
        settle(self.state, tape, {"sha256": "test-source"}, at("15:05"))
        calls = list(self.state["calls"].values())
        self.assertEqual([call["outcome"]["status"] for call in calls], ["hit", "miss"])
        self.assertEqual(fit(calls)["rows"], 1)
        self.assertEqual(fit(calls)["groups"]["below:mixed"]["dates"], 1)
        self.assertEqual(calls[0]["plan"]["buy_high"], 8.21)

    def test_past_closes_and_mutations_cannot_become_training_data(self):
        path = self.publish("early", "09:05")
        self.assertEqual(register(self.root, at("15:05"), CALENDAR, self.state), [])
        path.write_text("{}", encoding="utf-8")
        rejected = register(self.root, at("15:10"), CALENDAR, self.state)
        self.assertEqual(rejected[0]["reason"], "forecast_file_revised_after_registration")
        settle(self.state, {"600970": {DAY: {"day": DAY, "close": 7.97, "volume": 1000}}}, {}, at("15:10"))
        calls = list(self.state["calls"].values())
        self.assertEqual(calls[0]["outcome"], {"status": "publication_unverified_before_close"})
        self.assertEqual(fit(calls)["rows"], 0)

    def test_unavailable_close_can_resolve_later_without_assuming_a_fill(self):
        self.publish("early", "09:05")
        register(self.root, at("09:10"), CALENDAR, self.state)
        settle(self.state, {}, None, at("15:10"))
        call = next(iter(self.state["calls"].values()))
        self.assertNotIn("outcome", call)
        settle(self.state, {"600970": {DAY: {"day": DAY, "close": 8.10, "volume": 1000}}}, {}, at("16:00"))
        self.assertEqual(call["outcome"]["status"], "miss")
        self.assertNotIn("fill_price", call["outcome"])
