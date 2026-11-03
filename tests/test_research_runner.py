from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from report_support.index import sync_index, write_json
from research_system.runner import run
from tests import test_boll_noon_collection as fixtures
NOW, TODAY = fixtures.NOW, fixtures.TODAY


class ResearchIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.IndependentNoonTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        config = json.loads((Path(__file__).resolve().parents[1] / "config/research_v2.json").read_text())
        config["forward_start_date"] = "2026-10-14"
        write_json(self.root / "config/research_v2.json", config)

    def add_report(self, cycle="early", role="focus", sidecar=False):
        label = {"early": "早报", "noon": "午报"}[cycle]
        header = (f'---\nreport_date: "{TODAY}"\narchived_at: "{TODAY}T09:05:00+08:00"\n'
                  f'{role}_stock_code: "600000"\n{role}_original_window: "2026-10-15 through 2026-10-19"\n'
                  'research_method: "fixture_manual"\n---\n')
        body = header + f"# {TODAY} {label}\n\n" + "\n\n".join(f"## {i}. 标题\n公开研究内容" for i in range(1, 8)) + "\n\n本报告不构成投资建议。\n"
        path = self.root / f"reports/archive/{TODAY.replace('-', '/')}/{cycle}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        if sidecar:
            write_json(path.with_name(path.stem + "-handoff.json"), {"report_date": TODAY, "report_type": cycle,
                "body_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "available_at": TODAY + "T09:06:00+08:00",
                "research_signals": [{"code": "600000", "roles": ["technical"], "strategy": "trend_pullback",
                    "method_version": "fixture_v2", "first_issued_at": TODAY + "T09:00:00+08:00",
                    "valid_until": "2026-10-19T15:00:00+08:00", "entry_rule": "observation_only"}]})
        sync_index(self.root, moment=NOW)
        return path

    def test_two_reports_do_not_double_count_legacy_observation_or_fake_returns(self):
        self.add_report()
        self.add_report("noon", "technical")
        out = run(self.root, NOW)
        self.assertEqual(1, out["episode_count"])
        self.assertEqual(1, out["feature_sessions"])
        self.assertFalse(out["readiness"]["production_activation"])
        for role in ("technical", "comprehensive"):
            self.assertIsNone(out["role_results"][role]["positive_return_fraction"])
        second = run(self.root, NOW.replace(minute=45))
        self.assertEqual(1, second["episode_count"])

    def test_bound_signal_sidecar_is_imported_and_private_fields_are_not_copied(self):
        self.add_report(sidecar=True)
        out = run(self.root, NOW)
        self.assertEqual(1, out["report_import"]["new_contracts"])
        state = json.loads((self.root / "output/research/state/episodes.json").read_text())
        ep = next(iter(state["episodes"].values()))
        self.assertEqual("observation_only", ep["entry_rule"])
        self.assertEqual({}, ep["outcomes"])

    def test_tampered_producer_bytes_are_disclosed_not_relabelled_complete(self):
        manifest = json.loads((self.root / "output/boll/latest/manifest.json").read_text())
        path = self.root / manifest["latest_complete_screen"]["selected_file"]
        path.write_text(path.read_text() + " ")
        out = run(self.root, NOW)
        self.assertIn("sha256_mismatch", out["data_errors"][0])
        self.assertIsNone(out["screen_source"])

    def test_noon_capture_keeps_correct_clock_and_never_uses_1135_quote(self):
        self.fixture.execute(quote_collector=self.fixture.collector({"000001": "11:35:00"}))
        out = run(self.root, NOW)
        self.assertEqual(1, out["noon_baseline"]["valid_quotes"])
        self.assertFalse(out["noon_baseline"]["full_market_complete"])
        data = json.loads((self.root / "output/research/noon" / (TODAY + ".json")).read_text())
        self.assertEqual(["600000"], list(data["quotes"]))
        self.assertEqual("11:30", data["cutoff"])


if __name__ == "__main__":
    unittest.main()
