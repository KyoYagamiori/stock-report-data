from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.adapters import AdapterResult
from pipeline.calendar import CalendarInfo
from pipeline.contracts import load_report_pools
from pipeline.publisher import publish_snapshot
from pipeline.runner import RunOptions, _annotate_noon_volume, _stocks_from_previous_close, run_pipeline
from tests.helpers import valid_snapshot


TIMEZONE = ZoneInfo("Asia/Shanghai")


def trading_calendar(moment: datetime, root: Path) -> CalendarInfo:
    del root
    return CalendarInfo(
        date=moment.date().isoformat(),
        is_trading_day=True,
        latest_completed_trading_day="2026-07-15" if moment.hour < 15 else "2026-07-16",
        next_trading_day="2026-07-17",
        source="test-calendar",
        valid=True,
    )


def non_trading_calendar(moment: datetime, root: Path) -> CalendarInfo:
    del root
    return CalendarInfo(
        date=moment.date().isoformat(),
        is_trading_day=False,
        latest_completed_trading_day="2026-07-17",
        next_trading_day="2026-07-20",
        source="test-calendar",
        valid=True,
    )


def stock_collector_for(quote_time: str, valid: bool = True):
    def collect(root: Path, moment: datetime, market_date: str, mode: str):
        del root, market_date, mode
        stocks = []
        for index, entry in enumerate(load_report_pools()["core"]):
            stocks.append(
                {
                    "code": entry["code"],
                    "name": entry["name"],
                    "pool": "core",
                    "valid_quote": valid,
                    "quote_time": quote_time if valid else None,
                    "latest_price": 10.0 + index,
                }
            )
        for index, entry in enumerate(load_report_pools()["watch"]):
            stocks.append(
                {
                    "code": entry["code"],
                    "name": entry["name"],
                    "pool": "watch",
                    "valid_quote": valid,
                    "quote_time": quote_time if valid else None,
                    "latest_price": 20.0 + index,
                }
            )
        result = AdapterResult(
            status="success" if valid else "partial",
            source="test-stock-source",
            data={"stocks": stocks},
            started_at=moment,
            finished_at=moment,
            records_expected=25,
            records_valid=25 if valid else 0,
        )
        return result, pd.DataFrame()

    return collect


def full_market_collector(spot: pd.DataFrame, source: str, moment: datetime) -> AdapterResult:
    del spot, source
    data = {
        "indices": [
            {"code": "000001", "name": "上证指数", "latest": 4000.0},
            {"code": "399001", "name": "深证成指", "latest": 13000.0},
            {"code": "399006", "name": "创业板指", "latest": 3000.0},
        ],
        "total_turnover": 123456789.0,
        "turnover_valid": True,
        "breadth": {"up": 3000, "down": 2000, "flat": 100, "limit_up": 80, "limit_down": 20},
        "breadth_valid": True,
        "sectors_top": [{"name": f"Top {index}", "change_pct": index + 1} for index in range(5)],
        "sectors_bottom": [{"name": f"Bottom {index}", "change_pct": -index - 1} for index in range(5)],
    }
    return AdapterResult(
        status="success",
        source="test-market-source",
        data=data,
        started_at=moment,
        finished_at=moment,
        records_expected=15,
        records_valid=15,
    )


class RunnerTests(unittest.TestCase):
    def test_noon_grade_a_publishes_authoritative_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            moment = datetime(2026, 7, 16, 11, 36, tzinfo=TIMEZONE)
            result = run_pipeline(
                RunOptions("noon", "full", "11:35", "primary", moment=moment),
                root,
                calendar_resolver=trading_calendar,
                stock_collector=stock_collector_for("2026-07-16T11:30:05+08:00"),
                market_collector=full_market_collector,
            )
            self.assertEqual("A", result.grade)
            self.assertTrue(result.published)
            manifest = json.loads((root / "output/latest/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("ready_a", manifest["report_readiness"]["noon"]["status"])
            self.assertIn("output/archive/", manifest["snapshots"]["noon"]["selected_file"])

    def test_delayed_noon_uses_point_in_time_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            moment = datetime(2026, 7, 16, 14, 32, tzinfo=TIMEZONE)

            def recover(stock_result, market_result, profile, report_date, market_date, started):
                del stock_result, market_result, report_date, market_date
                self.assertEqual("trading_noon", profile)
                return (
                    stock_collector_for("2026-07-16T11:30:00+08:00")(root, started, "2026-07-16", "full")[0],
                    full_market_collector(pd.DataFrame(), "recovered", started),
                )

            result = run_pipeline(
                RunOptions("noon", "full", "11:35", "manual-recovery", moment=moment),
                root,
                calendar_resolver=trading_calendar,
                stock_collector=stock_collector_for("2026-07-16T14:30:00+08:00"),
                market_collector=full_market_collector,
                point_in_time_recoverer=recover,
            )
            self.assertEqual("A", result.grade)
            manifest = json.loads((root / "output/latest/manifest.json").read_text(encoding="utf-8"))
            pointer = manifest["snapshots"]["noon"]
            self.assertTrue(pointer["point_in_time_recovered"])
            self.assertEqual("historical_point_in_time_recovery", pointer["collection_mode"])
            self.assertEqual(177.0, pointer["schedule_delay_minutes"])

    def test_non_trading_snapshot_is_published_as_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            moment = datetime(2026, 7, 18, 8, 40, tzinfo=TIMEZONE)
            result = run_pipeline(
                RunOptions("early", "full", "08:40", "primary", moment=moment),
                root,
                calendar_resolver=non_trading_calendar,
                stock_collector=stock_collector_for("2026-07-17T15:00:00+08:00", valid=False),
                market_collector=full_market_collector,
            )
            self.assertEqual("B", result.grade)
            self.assertTrue(result.published)
            manifest = json.loads((root / "output/latest/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("not_applicable", manifest["report_readiness"]["early"]["status"])

    def test_expired_scheduled_intraday_skips_before_fetching(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = run_pipeline(
                RunOptions("intraday", "light", "10:05", "rolling",
                           moment=datetime(2026, 7, 16, 15, 40, tzinfo=TIMEZONE)),
                root,
                stock_collector=lambda *_: self.fail("expired quote must not be fetched"),
            )
            self.assertFalse(result.published)
            self.assertEqual("skipped_expired", json.loads(result.health_path.read_text())["status"])

    def test_retry_skips_when_same_cycle_a_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_pipeline(
                RunOptions("noon", "full", "11:37", "primary",
                           moment=datetime(2026, 7, 16, 11, 38, tzinfo=TIMEZONE)),
                root, calendar_resolver=trading_calendar,
                stock_collector=stock_collector_for("2026-07-16T11:30:05+08:00"),
                market_collector=full_market_collector,
            )
            retry = run_pipeline(
                RunOptions("noon", "full", "12:07", "retry-1",
                           moment=datetime(2026, 7, 16, 12, 8, tzinfo=TIMEZONE)),
                root, calendar_resolver=trading_calendar,
                stock_collector=lambda *_: self.fail("ready A must avoid a second collection"),
            )
            self.assertEqual("skipped_ready", json.loads(retry.health_path.read_text())["status"])

    def test_previous_close_promotes_dongwei_into_core_and_flags_old_indicators(self) -> None:
        close = {"snapshot_id": "prior-close", "stocks": [
            {"code": "688700", "name": "东威科技", "pool": "supplemental",
             "valid_quote": True, "indicator_adjustment": "qfq", "indicator_status": "ready"},
        ]}
        result = _stocks_from_previous_close(close, datetime(2026, 7, 17, 8, 20, tzinfo=TIMEZONE))
        stock = result.data["stocks"][0]
        self.assertEqual("core", stock["pool"])
        self.assertEqual("missing", stock["indicator_status"])

    def test_preopen_uses_verified_previous_close_without_live_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            close = valid_snapshot()
            close.update(snapshot_type="close", snapshot_id="20260716-1520-close-full-test",
                         report_cycle="2026-07-16-close", quality_profile="trading_close",
                         market_session="market_close", planned_at="2026-07-16T15:20:00+08:00",
                         started_at="2026-07-16T15:21:00+08:00",
                         published_at="2026-07-16T15:22:00+08:00",
                         quote_time_min="2026-07-16T15:00:00+08:00",
                         quote_time_max="2026-07-16T15:00:00+08:00")
            pools = load_report_pools()
            close["stocks"] = [
                {"code": item["code"], "name": item["name"], "pool": group,
                 "valid_quote": True, "latest_trade_date": "2026-07-16",
                 "quote_time": "2026-07-16T15:00:00+08:00"}
                for group in ("core", "watch") for item in pools[group]
            ]
            close["market"] = full_market_collector(pd.DataFrame(), "test", datetime(2026, 7, 16, 15, 21, tzinfo=TIMEZONE)).data
            publish_snapshot(close, root, {"date": "2026-07-16", "is_trading_day": True,
                                           "latest_completed_trading_day": "2026-07-16",
                                           "next_trading_day": "2026-07-17", "source": "test"})

            def next_day_calendar(moment, root):
                return CalendarInfo("2026-07-17", True, "2026-07-16", "2026-07-20", "test", True)

            result = run_pipeline(
                RunOptions("early", "full", "08:17", "primary",
                           moment=datetime(2026, 7, 17, 8, 18, tzinfo=TIMEZONE)),
                root, calendar_resolver=next_day_calendar,
                stock_collector=lambda *_: self.fail("previous close should bypass live fetch"),
            )
            self.assertEqual("A", result.grade)
            payload = json.loads(result.publish_result.archive_path.read_text())
            self.assertEqual("core", next(x["pool"] for x in payload["stocks"] if x["code"] == "688700"))

    def test_noon_amount_only_compares_matching_verified_half_day(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            earlier = valid_snapshot()
            earlier["report_date"] = earlier["market_date"] = "2026-07-15"
            earlier["report_cycle"] = "2026-07-15-noon"
            earlier["snapshot_id"] = "20260715-1135-noon-full-test"
            for key in ("planned_at", "started_at", "published_at", "quote_time_min", "quote_time_max"):
                earlier[key] = earlier[key].replace("2026-07-16", "2026-07-15")
            earlier["stocks"] = [{"code": "688700", "name": "东威科技", "pool": "core",
                                   "valid_quote": True, "today_amount": 100.0,
                                   "quote_time": "2026-07-15T11:30:00+08:00"}]
            publish_snapshot(earlier, root, {"date": "2026-07-15", "is_trading_day": True,
                                              "latest_completed_trading_day": "2026-07-14",
                                              "next_trading_day": "2026-07-16", "source": "test"})
            stocks = [{"code": "688700", "previous_trade_date": "2026-07-15", "today_amount": 120.0,
                       "valid_quote": True, "latest_trade_date": "2026-07-16",
                       "quote_time": "2026-07-16T11:30:00+08:00"},
                      {"code": "600584", "previous_trade_date": "2026-07-14", "today_amount": 90.0,
                       "valid_quote": True, "latest_trade_date": "2026-07-16",
                       "quote_time": "2026-07-16T11:30:00+08:00"}]
            _annotate_noon_volume(root, stocks, "2026-07-16")
            self.assertEqual(0.2, stocks[0]["same_phase_amount_ratio"])
            self.assertIsNone(stocks[1]["same_phase_amount_ratio"])

    def test_evening_without_same_day_close_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            moment = datetime(2026, 7, 16, 20, 35, tzinfo=TIMEZONE)
            result = run_pipeline(
                RunOptions("evening", "full", "20:35", "primary", moment=moment),
                root,
                calendar_resolver=trading_calendar,
                stock_collector=stock_collector_for("2026-07-16T15:00:03+08:00", valid=False),
                market_collector=full_market_collector,
            )
            self.assertEqual("F", result.grade)
            self.assertFalse(result.published)
            self.assertIn("recovery failed", result.reason)

    def test_evening_recovers_missing_same_day_close_before_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            moment = datetime(2026, 7, 16, 20, 35, tzinfo=TIMEZONE)
            result = run_pipeline(
                RunOptions("evening", "full", "20:35", "primary", moment=moment),
                root,
                calendar_resolver=trading_calendar,
                stock_collector=stock_collector_for("2026-07-16T15:00:03+08:00"),
                market_collector=full_market_collector,
            )
            self.assertEqual("A", result.grade)
            self.assertTrue(result.published)
            manifest = json.loads((root / "output/latest/manifest.json").read_text(encoding="utf-8"))
            self.assertIsNotNone(manifest["snapshots"]["close"])
            self.assertEqual("ready_a", manifest["report_readiness"]["evening"]["status"])

    def test_evening_inherits_verified_same_day_close(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            close_moment = datetime(2026, 7, 16, 15, 21, tzinfo=TIMEZONE)
            close_result = run_pipeline(
                RunOptions("close", "full", "15:20", "primary", moment=close_moment),
                root,
                calendar_resolver=trading_calendar,
                stock_collector=stock_collector_for("2026-07-16T15:00:03+08:00"),
                market_collector=full_market_collector,
            )
            self.assertEqual("A", close_result.grade)
            self.assertTrue(close_result.published)

            evening_moment = datetime(2026, 7, 16, 20, 35, tzinfo=TIMEZONE)
            evening_result = run_pipeline(
                RunOptions("evening", "full", "20:35", "primary", moment=evening_moment),
                root,
                calendar_resolver=trading_calendar,
            )
            self.assertEqual("A", evening_result.grade)
            self.assertTrue(evening_result.published)
            manifest = json.loads((root / "output/latest/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("ready_a", manifest["report_readiness"]["evening"]["status"])
            self.assertEqual(
                close_result.snapshot_id,
                json.loads((root / manifest["snapshots"]["evening"]["selected_file"]).read_text(encoding="utf-8"))["based_on_snapshot_id"],
            )


if __name__ == "__main__":
    unittest.main()
