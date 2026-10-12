import json
import io
import os
import tempfile
import unittest
from copy import deepcopy
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.close_verification import verify_completed_close
from pipeline.publisher import publish_snapshot, refresh_manifest, verify_pointer
from pipeline.quality import evaluate_quality
from pipeline.runner import RunOptions, _snapshot_id, run_pipeline
from pipeline.calendar import CalendarInfo
from pipeline.schedule import resolve_schedule
from pipeline.run import main as run_cli
from tests.helpers import valid_snapshot
from tests.test_publisher import calendar
from tests.test_runner import stock_collector_for, full_market_collector

TZ = ZoneInfo("Asia/Shanghai")


def completed_quote(price, stamp="2026-07-16T16:29:30+08:00"):
    row = {"latest_price": price, "today_open": price + .1,
           "today_high": price + 1, "today_low": price - 1, "quote_time": stamp}
    bar = {"date": "2026-07-16", "open": price + .1,
           "high": price + 1, "low": price - 1, "close": price}
    return {**row, **verify_completed_close(row, bar, "2026-07-16")}


def verified_market(spot, source, moment):
    result = full_market_collector(spot, source, moment)
    for row in result.data["indices"]:
        row.update(completed_quote(row["latest"], "2026-07-16T16:19:55+08:00"))
    return result


def verified_stocks(root, moment, market_date, mode):
    result, frame = stock_collector_for("2026-07-16T16:29:30+08:00")(root, moment, market_date, mode)
    for row in result.data["stocks"]:
        row.update(completed_quote(row["latest_price"]))
        row["latest_trade_date"] = "2026-07-16"
    result.data["completed_close_verified"] = True
    return result, frame


class CloseRepairTests(unittest.TestCase):
    def close_snapshot(self):
        snapshot = valid_snapshot()
        snapshot.update(snapshot_type="close", quality_profile="trading_close",
                        report_cycle="2026-07-16-close", snapshot_id="20260716-1520-close-full-test",
                        planned_at="2026-07-16T15:20:00+08:00", started_at="2026-07-16T19:51:55+08:00",
                        published_at="2026-07-16T19:52:51+08:00", market_session="market_close",
                        quote_time_min="2026-07-16T16:19:55+08:00", quote_time_max="2026-07-16T16:29:30+08:00")
        snapshot["stocks"] = [{"code": "688700", "name": "东威科技", "pool": "core", "valid_quote": True,
                               **completed_quote(54.08)}]
        snapshot["market"] = verified_market(pd.DataFrame(), "test", datetime(2026,7,16,19,tzinfo=TZ)).data
        return snapshot

    def test_postclose_source_refresh_passes_only_with_matching_daily_bars(self):
        snapshot = self.close_snapshot()
        self.assertEqual("A", evaluate_quality(snapshot, "trading_close").grade)
        self.assertEqual("2026-07-16T16:29:30+08:00", snapshot["stocks"][0]["quote_time"])
        for mutation in ("missing_evidence", "price_mismatch", "previous_day", "changed_update_time"):
            bad = deepcopy(snapshot)
            row = bad["stocks"][0]
            if mutation == "missing_evidence":
                del row["close_verification"]
            elif mutation == "price_mismatch":
                row["latest_price"] += .1
            elif mutation == "previous_day":
                row["close_verification"]["daily_bar"]["date"] = "2026-07-15"
            else:
                row["close_verification"]["quote_time"] = "2026-07-16T16:00:00+08:00"
            with self.subTest(mutation=mutation):
                self.assertEqual("F", evaluate_quality(bad, "trading_close").grade)

    def test_late_index_also_requires_daily_close_verification(self):
        snapshot = self.close_snapshot()
        del snapshot["market"]["indices"][0]["close_verification"]
        self.assertEqual("F", evaluate_quality(snapshot, "trading_close").grade)

    def test_cross_midnight_recovers_previous_close_and_evening_then_current_early(self):
        moment = datetime(2026,7,17,0,43,21,800000,tzinfo=TZ)
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)
        def cal(*_):
            return CalendarInfo("2026-07-17",True,"2026-07-16","2026-07-20","test",True)
        with (tempfile.TemporaryDirectory() as tmp, patch("pipeline.runner.datetime", Clock),
              patch.dict(os.environ, {"GITHUB_RUN_ID": "", "GITHUB_RUN_ATTEMPT": "1"})):
            root = Path(tmp)
            result = run_pipeline(RunOptions("early","full","00:43","config-refresh",moment=moment),root,
                                  calendar_resolver=cal,stock_collector=verified_stocks,market_collector=verified_market)
            self.assertTrue(result.published)
            manifest = json.loads((root/"output/latest/manifest.json").read_text())
            self.assertEqual("2026-07-17", manifest["calendar"]["date"])
            self.assertEqual("ready_a", manifest["report_readiness"]["early"]["status"])
            self.assertEqual("not_ready", manifest["report_readiness"]["evening"]["status"])
            for kind, report_date in (("close","2026-07-16"),("evening","2026-07-16"),("early","2026-07-17")):
                payload = verify_pointer(root,manifest["snapshots"][kind])
                self.assertEqual(report_date,payload["report_date"])
                self.assertEqual("2026-07-16",payload["market_date"])
                self.assertEqual("2026-07-17T00:43:21+08:00",payload["started_at"])
            # The next fast reuse publishes within the very same second.
            retry = run_pipeline(RunOptions("early","full","00:43","manual-fast",moment=moment),root,
                                 calendar_resolver=cal,
                                 stock_collector=lambda *_: self.fail("verified close must be reused"))
            self.assertEqual("A",retry.grade)

    def test_backfill_does_not_roll_manifest_date_or_generation_time_backwards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pub = publish_snapshot(valid_snapshot(),root,calendar())
            refresh_manifest(root,dict(calendar(),date="2026-07-17"),"2026-07-17T08:21:00+08:00")
            payload = self.close_snapshot()
            payload["started_at"] = "2026-07-17T08:20:00+08:00"
            payload["published_at"] = "2026-07-17T08:20:30+08:00"
            publish_snapshot(payload,root,calendar())
            manifest = json.loads(pub.manifest_path.read_text())
            self.assertEqual("2026-07-17",manifest["calendar"]["date"])
            self.assertEqual("2026-07-17T08:21:00+08:00",manifest["generated_at"])

    def test_other_corrupt_ready_pointer_stays_blocked_when_new_type_publishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pub = publish_snapshot(valid_snapshot(),root,calendar())
            pub.archive_path.write_text("corrupt")
            publish_snapshot(self.close_snapshot(),root,calendar())
            manifest = json.loads(pub.manifest_path.read_text())
            self.assertEqual("not_ready",manifest["report_readiness"]["noon"]["status"])

    def test_workflow_rerun_gets_a_distinct_immutable_snapshot_id(self):
        options = RunOptions("close","full","15:20","manual")
        moment = datetime(2026,7,16,16,tzinfo=TZ)
        with patch.dict(os.environ,{"GITHUB_RUN_ID":"123","GITHUB_RUN_ATTEMPT":"1"}):
            first = _snapshot_id("2026-07-16",options,moment)
        with patch.dict(os.environ,{"GITHUB_RUN_ID":"123","GITHUB_RUN_ATTEMPT":"2"}):
            second = _snapshot_id("2026-07-16",options,moment)
        self.assertNotEqual(first,second)
        self.assertTrue(second.endswith("-a2"))

    def test_evening_delay_uses_actual_phase_before_runner_expiry(self):
        params = resolve_schedule("schedule","17 12 * * *",moment=datetime(2026,10,12,21,45,tzinfo=TZ))
        self.assertEqual(("evening","21:45","delayed-current-phase"),
                         (params.snapshot_type,params.planned_at,params.attempt_role))

    def test_cli_rechecks_automatic_date_after_setup_crosses_midnight(self):
        moment = datetime(2026,10,13,0,1,tzinfo=TZ)
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)
        result = SimpleNamespace(grade="B",published=True,reason="published",snapshot_id="test",health_path=Path("test"))
        args = ["pipeline.run","--snapshot-type","evening","--mode","full",
                "--planned-at","20:17","--report-date","2026-10-12"]
        for event, cron in (("schedule","17 12 * * *"),("schedule",""),("workflow_dispatch","")):
            with (self.subTest(event=event,cron=cron), patch("sys.argv",args),
                  patch("pipeline.run.datetime",Clock),
                  patch.dict(os.environ,{"GITHUB_EVENT_NAME":event,"GITHUB_EVENT_SCHEDULE":cron}),
                  patch("pipeline.run.run_pipeline",return_value=result) as execute,
                  redirect_stdout(io.StringIO())):
                run_cli()
                options = execute.call_args.args[0]
                if event == "schedule":
                    self.assertEqual(("early","00:01","2026-10-13"),
                                     (options.snapshot_type,options.planned_at,options.report_date))
                else:
                    self.assertEqual(("evening","20:17","2026-10-12"),
                                     (options.snapshot_type,options.planned_at,options.report_date))


if __name__ == "__main__":
    unittest.main()
