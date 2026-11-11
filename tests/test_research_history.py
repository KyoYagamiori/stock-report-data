from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import subprocess
import textwrap
import unittest

from research_system.early_model import run_registered, validate
from research_system.history_dataset import causal_adjust, entry_rejection, labels, normalize, points_for
from research_system.history_source import capture, read_capture, select_cohort, write
from research_system.history_training import run, verify_completed
from tests.test_research_early_model import early_dataset


def bars(n=250):
    import math
    day, out = date(2020, 1, 2), []
    while len(out) < n:
        if day.weekday() < 5:
            i = len(out)
            price = 10 + .001 * i + .4 * math.sin(i / 9)
            out.append({"day": day.isoformat(), "code": "sh.600000", "open": price - .01,
                "high": price + .1, "low": price - .1, "close": price, "volume": 10000000.,
                "amount": 100000000., "preclose": out[-1]["close"] if out else price,
                "tradestatus": "1", "isST": "0"})
        day += timedelta(days=1)
    return out


class HistoricalTrainingTests(unittest.TestCase):
    def test_rebased_model_commit_is_actually_pushed_even_with_clean_index(self):
        def git(cwd, *args):
            return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.STDOUT)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, producer, concurrent = root / "remote.git", root / "producer", root / "concurrent"
            git(root, "init", "--bare", "--initial-branch=main", str(remote))
            git(root, "clone", str(remote), str(producer))
            git(producer, "config", "user.name", "test")
            git(producer, "config", "user.email", "test@example.invalid")
            write(producer / "output/research/latest/history_pilot_status.json", {"model_status": "not_trained"})
            write(producer / "output/history_pilot/source.json", {"source": "fixture"})
            git(producer, "add", ".")
            git(producer, "commit", "-m", "initial")
            git(producer, "push", "origin", "HEAD:main")
            git(root, "clone", str(remote), str(concurrent))
            git(concurrent, "config", "user.name", "test")
            git(concurrent, "config", "user.email", "test@example.invalid")
            (concurrent / "unrelated.txt").write_text("concurrent public report")
            git(concurrent, "add", ".")
            git(concurrent, "commit", "-m", "concurrent update")
            git(concurrent, "push", "origin", "HEAD:main")
            write(producer / "output/research/latest/history_pilot_status.json", {"model_status": "trained_pilot_only"})
            write(producer / "output/history_pilot/model.json", {"kind": "fixture_model"})
            workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/history-training.yml").read_text()
            block = workflow.split("      - name: Preserve historical evidence", 1)[1].split("        run: |\n", 1)[1].split("\n      - name:", 1)[0]
            completed = subprocess.run(["bash", "-euo", "pipefail", "-c", textwrap.dedent(block)],
                                       cwd=producer, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(0, completed.returncode, completed.stdout)
            actual = json.loads(git(root, "--git-dir=" + str(remote), "show", "main:output/research/latest/history_pilot_status.json"))
            self.assertEqual("trained_pilot_only", actual["model_status"])
            self.assertIn("fixture_model", git(root, "--git-dir=" + str(remote), "show", "main:output/history_pilot/model.json"))
            self.assertIn("concurrent public report", git(root, "--git-dir=" + str(remote), "show", "main:unrelated.txt"))

    def test_selection_is_historical_and_independent_of_current_status_and_row_order(self):
        source = [{"code": c, "status": "0"} for c in ("sh.600001", "sh.600002", "sz.000001", "sz.002001", "sh.000300")]
        original = select_cohort(source, 3, "fixed")
        changed = [{**r, "status": "1", "code_name": "new name"} for r in reversed(source)]
        self.assertEqual(original, select_cohort(changed, 3, "fixed"))
        self.assertNotIn("sh.000300", original)
        with self.assertRaises(ValueError): select_cohort(source + [source[0]], 3, "fixed")

    def test_source_hashes_are_checked_on_actual_compressed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ref = capture(root, {"method": "query_all_stock", "kwargs": {"day": "2018-01-02"}}, [{"code": "sh.600000"}])
            self.assertEqual(1, len(read_capture(root, ref)["rows"]))
            path = root / ref["file"]
            path.write_bytes(path.read_bytes() + b"tamper")
            with self.assertRaises(ValueError): read_capture(root, ref)

    def test_future_prices_and_future_corporate_action_cannot_change_earlier_features(self):
        source = bars()
        old = points_for(causal_adjust(source))
        changed = deepcopy(source)
        for row in changed[210:]:
            row["preclose"] /= 2
            for key in ("open", "high", "low", "close"): row[key] /= 2
        new = points_for(causal_adjust(changed))
        self.assertEqual(old[:210], new[:210])

    def test_causal_points_match_live_completed_boll_and_atr(self):
        from market_screen.technicals import calculate
        data = causal_adjust(bars())
        p = points_for(data)[-1]
        live = calculate(data[-160:], data[-1]["day"])
        for key in ("mid", "upper", "lower", "width"):
            self.assertAlmostEqual(live["boll"][key], p[key], places=10)
        self.assertAlmostEqual(live["early_state"]["points"][-1]["atr20"], p["atr20"], places=10)

    def test_no_fill_is_cash_and_never_silently_delayed_to_a_later_buy(self):
        rows = bars(30)
        calendar = [r["day"] for r in rows]
        rows[11].update(tradestatus="0", volume=0.)
        raw = {r["day"]: r for r in rows}
        adjusted = {r["day"]: r for r in causal_adjust(rows)}
        target, audit = labels(calendar[10], raw, adjusted, calendar, raw, 20)
        self.assertEqual({1: 0., 3: 0., 5: 0.}, target)
        self.assertEqual("unfilled_cash_zero", audit["state"])
        self.assertEqual(calendar[11], audit["entry_date"])

    def test_costs_and_t_plus_one_use_an_exit_after_entry(self):
        rows = bars(30)
        calendar = [r["day"] for r in rows]
        raw = {r["day"]: r for r in rows}
        adjusted = {r["day"]: r for r in causal_adjust(rows)}
        target, audit = labels(calendar[10], raw, adjusted, calendar, raw, 20)
        self.assertAlmostEqual(-.2, target[3], places=10)
        self.assertGreater(audit["scheduled_exit_dates"][1], audit["entry_date"])
        self.assertEqual(calendar[16], audit["label_end_date"])

    def test_unverifiable_exit_is_censored_and_not_fabricated_as_zero_return(self):
        rows = bars(30)
        calendar = [r["day"] for r in rows]
        raw = {r["day"]: r for r in rows}
        del raw[calendar[14]]
        adjusted = {r["day"]: r for r in causal_adjust(rows)}
        target, audit = labels(calendar[10], raw, adjusted, calendar, raw, 20)
        self.assertIsNone(target)
        self.assertEqual("censored_exit", audit["state"])

    def test_pilot_cannot_enter_formal_training_by_default(self):
        data = early_dataset(30)
        data["metadata"].update(scope="pilot", universe_basis="fixed_historical_origin_cohort",
            benchmark_basis="provider_index_not_independently_verified",
            corporate_actions_basis="causal_preclose_chain_raw_execution_retained",
            entry_policy="simulated_next_session_open_no_wait",
            execution_limits_basis="conservative_daily_proxy_not_official_limit_tape")
        self.assertTrue(validate(data, scope="pilot"))
        with self.assertRaises(ValueError): validate(data)

    def test_source_failure_is_persisted_as_a_specific_blocker(self):
        class Unavailable:
            def __enter__(self): raise RuntimeError("test_source_unavailable")
            def __exit__(self, *args): pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = json.loads((Path(__file__).resolve().parents[1] / "config/history_training.json").read_text())
            write(root / "config/history_training.json", config)
            result = run(root, client_factory=Unavailable)
            self.assertEqual("blocked_source_or_dataset", result["status"])
            self.assertIn("test_source_unavailable", result["reason"])
            self.assertEqual("not_trained", result["model_status"])
            self.assertFalse(result["production_activation"])

    def test_pilot_status_does_not_change_formal_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "output/research/latest/history_pilot_status.json", {"model_status": "trained_pilot_only", "status": "pilot_results_not_production_qualified", "reason": "source_detail_retained"})
            result = run_registered(root)
            self.assertEqual("not_trained", result["model_status"])
            self.assertEqual("trained_pilot_only", result["historical_pilot"]["model_status"])
            self.assertEqual("source_detail_retained", result["historical_pilot"]["reason"])
            self.assertFalse(result["production_activation"])

    def test_complete_source_to_dataset_pipeline_keeps_short_history_blocked(self):
        source = bars(360)
        calendar_rows = [{"calendar_date": r["day"], "is_trading_day": "1"} for r in source]
        class FixtureSource:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def query(self, request):
                if request["method"] == "query_all_stock":
                    return [{"code": "sh.600000"}, {"code": "sz.000001"}]
                if request["method"] == "query_trade_dates": return calendar_rows
                code = request["kwargs"]["code"]
                return [{**{k: str(v) for k, v in r.items() if k not in {"day", "code"}},
                    "date": r["day"], "code": code, "adjustflag": "3"} for r in source]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = json.loads((Path(__file__).resolve().parents[1] / "config/history_training.json").read_text())
            config.update(history_start=source[0]["day"], history_end=source[-1]["day"],
                cohort_date=source[20]["day"], sample_size=2)
            write(root / "config/history_training.json", config)
            result = run(root, client_factory=FixtureSource)
            self.assertEqual({}, result.get("source_failures"))
            self.assertGreater(result["training_rows"], 0)
            self.assertEqual("blocked_insufficient_qualified_history", result["status"])
            self.assertEqual("not_trained", result["model_status"])
            self.assertTrue((root / result["dataset_file"]).exists())
            self.assertFalse((root / "config/early_model_dataset.json").exists())
            verify_completed(root, result)
            dataset_file = root / result["dataset_file"]
            dataset_file.write_bytes(dataset_file.read_bytes() + b"tampered")
            with self.assertRaises(ValueError): verify_completed(root, result)


if __name__ == "__main__":
    unittest.main()
