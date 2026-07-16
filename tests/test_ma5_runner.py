from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from ma5_system.config import load_strategy_config
from ma5_system.data import HistoryStore
from ma5_system.runner import RunOptions, _is_long_holiday_gap, _turnover_ratio, run_scan
from tests.test_ma5_scoring import trending_history


TIMEZONE = ZoneInfo("Asia/Shanghai")


class MA5RunnerTests(unittest.TestCase):
    def test_long_holiday_gap_is_distinct_from_normal_weekend(self) -> None:
        self.assertFalse(_is_long_holiday_gap("2026-07-17", "2026-07-20"))
        self.assertTrue(_is_long_holiday_gap("2026-09-30", "2026-10-09"))

    def test_turnover_ratio_ignores_same_day_history_on_retry(self) -> None:
        spot = pd.DataFrame([{"amount": 200.0}])
        history = pd.DataFrame(
            [
                {"date": "2026-07-16", "amount": 100.0},
                {"date": "2026-07-17", "amount": 200.0},
            ]
        )
        self.assertEqual(2.0, _turnover_ratio(spot, history, "2026-07-17"))

    def test_preclose_pipeline_publishes_unique_a_plus_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codes = ["600001", "600002", "600003", "000001", "000002", "000003"]
            histories = []
            spot_rows = []
            for index, code in enumerate(codes):
                history = trending_history(code)
                history["name"] = f"Stock {code}"
                history["industry"] = "Leader" if index < 3 else "Reserve"
                histories.append(history)
                latest = float(history.iloc[-1]["close"] * 1.004)
                spot_rows.append(
                    {
                        "code": code,
                        "name": f"Stock {code}",
                        "latest": latest,
                        "pct_change": 1.2 if index < 3 else 0.5,
                        "open": latest * 0.995,
                        "high": latest * 1.01,
                        "low": latest * 0.995,
                        "prev_close": history.iloc[-1]["close"],
                        "volume": 12_000_000,
                        "amount": 300_000_000 if index < 3 else 200_000_000,
                        "turnover": 3.0,
                        "quote_time": "14:45:01",
                        "industry": "Leader" if index < 3 else "Reserve",
                    }
                )
            store = HistoryStore(root / "output" / "ma5" / "state" / "daily_history.csv.gz")
            store.save(pd.concat(histories, ignore_index=True))
            raw = pd.DataFrame(spot_rows)
            config = deepcopy(load_strategy_config())
            config["universe"]["expected_min_stocks"] = 6

            def spot_fetcher():
                return raw, "test-all-a", []

            def market_collector(frame, source, moment):
                del frame, source, moment
                return SimpleNamespace(
                    data={
                        "indices": [
                            {"code": "000001", "latest": 4000, "pct_change": 1.0},
                            {"code": "399001", "latest": 13000, "pct_change": 1.2},
                            {"code": "399006", "latest": 3000, "pct_change": 1.5},
                        ]
                    },
                    errors=[],
                )

            def index_enricher(indices, moment):
                del moment
                return [{**item, "trend_points": 10} for item in indices], []

            result = run_scan(
                RunOptions("preclose", "14:45", moment=datetime(2026, 7, 17, 14, 46, tzinfo=TIMEZONE)),
                root,
                spot_fetcher=spot_fetcher,
                market_collector=market_collector,
                index_enricher=index_enricher,
                event_provider=lambda codes, day: ({code: [] for code in codes}, []),
                history_provider=lambda codes, moment: (
                    pd.concat([frame for frame in histories if frame.iloc[0]["code"] in codes], ignore_index=True),
                    [],
                ),
                minute_provider=lambda codes, moment: (
                    {
                        code: {
                            "minute_source": "test-5m",
                            "minute_quote_time": "2026-07-17 14:45:00",
                            "minute_bars": 60,
                            "minute_vwap": float(raw.loc[raw["code"] == code, "latest"].iloc[0] * 0.998),
                            "local_tail_high": float(raw.loc[raw["code"] == code, "latest"].iloc[0] * 0.999),
                            "reclaimed_vwap": True,
                            "intraday_data_complete": True,
                        }
                        for code in codes
                    },
                    [],
                ),
                calendar_resolver=lambda moment, path: SimpleNamespace(
                    date="2026-07-17",
                    is_trading_day=True,
                    latest_completed_trading_day="2026-07-16",
                    next_trading_day="2026-07-20",
                    source="test-calendar",
                    valid=True,
                    warning=None,
                ),
                config=config,
            )
            self.assertEqual("A", result.screen["quality"]["grade"])
            self.assertTrue(result.screen["quality"]["actionable"])
            self.assertIsNotNone(result.screen["primary_candidate"])
            self.assertTrue(result.screen["primary_candidate"]["a_plus"])
            manifest = json.loads((root / "output/ma5/latest/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(result.screen["scan_id"], manifest["scans"]["preclose"]["scan_id"])
            self.assertIn("output/ma5/archive", manifest["scans"]["preclose"]["selected_file"])

    def test_non_trading_day_cannot_be_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = pd.DataFrame(
                [
                    {
                        "code": "600001",
                        "name": "Alpha",
                        "latest": 10.0,
                        "pct_change": 0.0,
                        "open": 10.0,
                        "high": 10.0,
                        "low": 10.0,
                        "volume": 1_000_000,
                        "amount": 200_000_000,
                        "turnover": 1.0,
                        "quote_time": "14:45:00",
                        "industry": "Leader",
                    }
                ]
            )
            config = deepcopy(load_strategy_config())
            config["universe"]["expected_min_stocks"] = 1
            result = run_scan(
                RunOptions("preclose", "14:45", moment=datetime(2026, 7, 18, 14, 46, tzinfo=TIMEZONE)),
                root,
                spot_fetcher=lambda: (raw, "test", []),
                market_collector=lambda frame, source, moment: SimpleNamespace(data={"indices": []}, errors=[]),
                index_enricher=lambda indices, moment: (indices, []),
                event_provider=lambda codes, day: ({code: [] for code in codes}, []),
                minute_provider=lambda codes, moment: ({}, []),
                calendar_resolver=lambda moment, path: SimpleNamespace(
                    date="2026-07-18",
                    is_trading_day=False,
                    latest_completed_trading_day="2026-07-17",
                    next_trading_day="2026-07-20",
                    source="test-calendar",
                    valid=True,
                    warning=None,
                ),
                config=config,
            )
            self.assertEqual("2026-07-17", result.screen["market_date"])
            self.assertEqual("F", result.screen["quality"]["grade"])
            self.assertFalse(result.screen["quality"]["actionable"])


if __name__ == "__main__":
    unittest.main()
