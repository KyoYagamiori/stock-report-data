from __future__ import annotations

from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from market_screen.history import (
    append_completed_quote,
    canonical_bytes,
    fetch_history,
    import_seed,
    load_cache,
    preserve_bootstrap,
    save_cache,
)


CODE = "600938"
TARGET = "2026-10-15"
PREVIOUS = "2026-10-14"


def bar(day=PREVIOUS, close=40):
    return {"day": day, "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": 1_000_000, "amount": close * 1_000_000}


def completed_quote(**overrides):
    return {
        "code": CODE, "name": "测试公司", "status": "valid",
        "open": 40.1, "prev_close": 40, "close": 40.5, "high": 41,
        "low": 39.8, "volume": 2_000_000, "amount": 81_000_000,
        "date": TARGET, "time": "15:00:00",
        "source_url": "https://hq.sinajs.cn/list=sh600938",
        "raw_sha256": hashlib.sha256(b"quote fixture").hexdigest(),
        "retrieved_at": "2026-10-15T15:01:00+08:00", **overrides,
    }


def cached_history():
    return {"code": CODE, "adjustment": "unadjusted", "bars": [bar()],
            "source": {"method": "fixture", "source_url": "https://example.invalid/history",
                       "retrieved_at": "2026-10-14T15:10:00+08:00"}}


class FakeResponse:
    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.raw


def write_payload(path, payload):
    path.write_bytes(gzip.compress(json.dumps(payload, allow_nan=True).encode(), mtime=0))


class HistoryCacheTests(unittest.TestCase):
    def test_bootstrap_advances_daily_even_when_stock_count_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "output/boll/state/history" / f"{CODE}.json.gz"
            save_cache(cache, CODE, [bar()], {"method": "fixture"})
            first = preserve_bootstrap(root, [{"code": CODE}], PREVIOUS)
            save_cache(cache, CODE, [bar(), bar(TARGET, 41)], {"method": "fixture"})
            second = preserve_bootstrap(root, [{"code": CODE}], TARGET)
            self.assertEqual(TARGET, second["market_date"])
            self.assertEqual(1, second["current_history_count"])
            self.assertNotEqual(first["sha256"], second["sha256"])

    def test_newer_verified_seed_replaces_older_existing_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            save_cache(cache / f"{CODE}.json.gz", CODE, [bar()], {"method": "older"})
            seed_payload = save_cache(root / "new.json.gz", CODE, [bar(), bar(TARGET, 41)], {"method": "newer"})
            seed = root / "seed.jsonl.gz"
            with gzip.open(seed, "wt", encoding="utf-8") as handle:
                handle.write(json.dumps(seed_payload) + "\n")
            self.assertEqual(1, import_seed(seed, cache, TARGET))
            self.assertEqual(TARGET, load_cache(cache / f"{CODE}.json.gz", CODE, TARGET)["bars"][-1]["day"])
            self.assertEqual(0, import_seed(seed, cache, TARGET))

    def test_completed_same_day_rebuilds_a_partial_restart_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "output/boll/state/history" / f"{CODE}.json.gz"
            save_cache(path, CODE, [bar()], {})
            preserve_bootstrap(root, [{"code": CODE}], TARGET)
            save_cache(path, CODE, [bar(), bar(TARGET, 41)], {})
            result = preserve_bootstrap(root, [{"code": CODE}], TARGET, complete=True)
            self.assertTrue(result["technical_screen_complete"])
            self.assertEqual(1, result["current_history_count"])

    def test_round_trip_checks_code_adjustment_and_actual_content_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{CODE}.json.gz"
            saved = save_cache(path, CODE, [bar()], {"method": "fixture"})
            restored = load_cache(path, CODE, PREVIOUS)
            self.assertEqual(saved["bars"], restored["bars"])
            self.assertEqual(hashlib.sha256(canonical_bytes(restored["bars"])).hexdigest(),
                             restored["history_sha256"])
            self.assertIsNone(load_cache(path, "688700", PREVIOUS))
            tampered = deepcopy(saved)
            tampered["bars"][0]["close"] = 40.5
            write_payload(path, tampered)
            self.assertIsNone(load_cache(path, CODE, PREVIOUS))
            tampered = {**saved, "adjustment": "qfq"}
            write_payload(path, tampered)
            self.assertIsNone(load_cache(path, CODE, PREVIOUS))

    def test_nonfinite_and_invalid_ohlcv_with_matching_hash_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{CODE}.json.gz"
            for bars in ([bar(close=0)], [{**bar(), "volume": -1}], [bar(), bar()],
                         [{**bar(), "high": 39}]):
                with self.subTest(bars=bars):
                    payload = {"code": CODE, "adjustment": "unadjusted", "bars": bars,
                               "source": {}, "history_sha256": hashlib.sha256(canonical_bytes(bars)).hexdigest()}
                    write_payload(path, payload)
                    self.assertIsNone(load_cache(path, CODE, PREVIOUS))
            payload = {"code": CODE, "adjustment": "unadjusted", "bars": [{**bar(), "close": float("nan")}],
                       "source": {}, "history_sha256": "anything"}
            write_payload(path, payload)
            self.assertIsNone(load_cache(path, CODE, PREVIOUS))

    def test_missing_and_malformed_cache_are_safe_misses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{CODE}.json.gz"
            self.assertIsNone(load_cache(path, CODE, PREVIOUS))
            malformed = [b"not gzip", gzip.compress(b"{not JSON}"),
                         gzip.compress(b"{}")[:-5], gzip.compress(b"[]"),
                         gzip.compress(b"null")]
            for raw in malformed:
                with self.subTest(raw=raw[:30]):
                    path.write_bytes(raw)
                    self.assertIsNone(load_cache(path, CODE, PREVIOUS))

    def test_non_object_bar_is_a_safe_cache_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{CODE}.json.gz"
            bars = [123]
            write_payload(path, {"code": CODE, "adjustment": "unadjusted", "bars": bars,
                                 "history_sha256": hashlib.sha256(canonical_bytes(bars)).hexdigest()})
            self.assertIsNone(load_cache(path, CODE, PREVIOUS))

    def test_loaded_view_hash_still_matches_when_future_bars_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{CODE}.json.gz"
            save_cache(path, CODE, [bar(), bar(TARGET, 41)], {})
            restored = load_cache(path, CODE, PREVIOUS)
            if restored is not None:
                self.assertEqual(PREVIOUS, restored["bars"][-1]["day"])
                self.assertEqual(hashlib.sha256(canonical_bytes(restored["bars"])).hexdigest(),
                                 restored["history_sha256"])

    def test_seed_hash_mismatch_or_adjusted_basis_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed.jsonl.gz"
            for changes, error in (({"history_sha256": "bad"}, "seed_history_hash_mismatch"),
                                    ({"adjustment": "qfq"}, "seed_adjustment_mismatch")):
                payload = {"code": CODE, "bars": [bar()], "source": {}, "adjustment": "unadjusted",
                           "history_sha256": hashlib.sha256(canonical_bytes([bar()])).hexdigest(), **changes}
                with gzip.open(seed, "wt", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload) + "\n")
                with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, error):
                    import_seed(seed, root / "cache", PREVIOUS)
                self.assertFalse((root / "cache" / f"{CODE}.json.gz").exists())


class SafeCompletedAppendTests(unittest.TestCase):
    def test_only_next_completed_session_and_matching_previous_close_append(self):
        cached = cached_history()
        result = append_completed_quote(cached, completed_quote(), TARGET, PREVIOUS)
        self.assertEqual([PREVIOUS, TARGET], [row["day"] for row in result])
        self.assertEqual(40.5, result[-1]["close"])
        self.assertEqual(2_000_000, result[-1]["volume"])
        self.assertEqual(81_000_000, result[-1]["amount"])
        self.assertEqual([bar()], cached["bars"])
        for previous in ("2026-10-13", "2026-10-12"):
            with self.subTest(previous=previous):
                self.assertIsNone(append_completed_quote(cached, completed_quote(), TARGET, previous))

    def test_live_stale_no_trade_or_future_timestamp_quotes_cannot_append(self):
        for changes in ({"time": "14:59:59"}, {"date": PREVIOUS},
                        {"retrieved_at": "2026-10-15T14:59:59+08:00"},
                        {"status": "no_trades", "volume": 0, "amount": 0},
                        {"volume": -1}, {"close": float("nan")}):
            with self.subTest(changes=changes):
                self.assertIsNone(append_completed_quote(cached_history(), completed_quote(**changes), TARGET, PREVIOUS))

    def test_corporate_action_or_previous_close_reset_refuses_splice(self):
        for previous_close in (39, 20, 40.02):
            with self.subTest(previous_close=previous_close):
                self.assertIsNone(append_completed_quote(cached_history(),
                    completed_quote(prev_close=previous_close), TARGET, PREVIOUS))

    def test_wrong_security_quote_cannot_append(self):
        self.assertIsNone(append_completed_quote(cached_history(),
            completed_quote(code="688700"), TARGET, PREVIOUS))

    def test_reverse_or_same_date_append_is_refused(self):
        cached = cached_history()
        cached["bars"] = [bar("2026-10-16")]
        self.assertIsNone(append_completed_quote(cached, completed_quote(), TARGET, "2026-10-16"))
        cached["bars"] = [bar(TARGET)]
        self.assertIsNone(append_completed_quote(cached, completed_quote(), TARGET, TARGET))


class HistoryFetchTests(unittest.TestCase):
    def test_fresh_unadjusted_history_and_completed_ex_date_quote_are_preserved(self):
        raw = b"var _data=(" + json.dumps([bar()]).encode() + b");"
        with tempfile.TemporaryDirectory() as directory:
            with patch("market_screen.history.urlopen", return_value=FakeResponse(raw)):
                result = fetch_history({"code": CODE, "exchange": "SH"}, TARGET, Path(directory),
                                       previous_session=PREVIOUS, quote=completed_quote(prev_close=39))
            self.assertEqual("history_fetch_and_quote_append", result["update_method"])
            self.assertEqual(40, result["bars"][0]["close"])
            self.assertEqual(40.5, result["bars"][-1]["close"])
            self.assertEqual(TARGET, result["bars"][-1]["day"])
            self.assertTrue(result["source"]["corporate_action_basis_change"])
            self.assertEqual(39, result["source"]["completed_quote"]["prev_close"])
            self.assertEqual(completed_quote()["raw_sha256"], result["source"]["completed_quote"]["raw_sha256"])

    def test_history_does_not_invent_an_unexplained_missing_session(self):
        raw = b"var _data=(" + json.dumps([bar("2026-10-12")]).encode() + b");"
        with tempfile.TemporaryDirectory() as directory:
            with patch("market_screen.history.urlopen", return_value=FakeResponse(raw)):
                result = fetch_history({"code": CODE, "exchange": "SH"}, TARGET, Path(directory),
                                       previous_session=PREVIOUS, quote=completed_quote())
            self.assertEqual("2026-10-12", result["bars"][-1]["day"])
            self.assertEqual("history_fetch", result["update_method"])

    def test_current_valid_cache_avoids_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_cache(root / f"{CODE}.json.gz", CODE, [bar(TARGET)], {"method": "fixture"})
            with patch("market_screen.history.urlopen") as mocked:
                result = fetch_history({"code": CODE, "exchange": "SH"}, TARGET, root)
            mocked.assert_not_called()
            self.assertEqual("cache_hit", result["update_method"])
            self.assertEqual("success", result["fetch_status"])

    def test_safe_quote_append_preserves_source_evidence_and_avoids_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_cache(root / f"{CODE}.json.gz", CODE, [bar()], cached_history()["source"])
            quote = completed_quote()
            with patch("market_screen.history.urlopen") as mocked:
                result = fetch_history({"code": CODE, "exchange": "SH"}, TARGET, root,
                                       previous_session=PREVIOUS, quote=quote)
            mocked.assert_not_called()
            self.assertEqual("quote_append", result["update_method"])
            self.assertEqual(quote["raw_sha256"], result["source"]["original_response_sha256"])
            self.assertEqual(quote["source_url"], result["source"]["source_url"])
            self.assertEqual(hashlib.sha256(canonical_bytes(result["bars"])).hexdigest(), result["history_sha256"])
            self.assertEqual(TARGET, load_cache(root / f"{CODE}.json.gz", CODE, TARGET)["bars"][-1]["day"])

    def test_action_gap_forces_history_fetch_and_explicit_flag(self):
        rows = [bar(), bar(TARGET, 39)]
        raw = b"var _data=(" + json.dumps(rows).encode() + b");"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_cache(root / f"{CODE}.json.gz", CODE, [bar()], cached_history()["source"])
            with patch("market_screen.history.urlopen", return_value=FakeResponse(raw)) as mocked:
                result = fetch_history({"code": CODE, "exchange": "SH"}, TARGET, root,
                    previous_session=PREVIOUS, quote=completed_quote(prev_close=39))
            self.assertEqual(1, mocked.call_count)
            self.assertEqual("history_fetch", result["update_method"])
            self.assertTrue(result["source"]["corporate_action_basis_change"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), result["source"]["original_response_sha256"])

    def test_download_never_includes_future_bars_or_fabricates_target_date(self):
        raw = b"var _data=(" + json.dumps([bar(), bar(TARGET), bar("2026-10-16")]).encode() + b");"
        with tempfile.TemporaryDirectory() as directory:
            with patch("market_screen.history.urlopen", return_value=FakeResponse(raw)):
                result = fetch_history({"code": CODE, "exchange": "SH"}, TARGET, Path(directory))
            self.assertEqual([PREVIOUS, TARGET], [row["day"] for row in result["bars"]])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), result["source"]["original_response_sha256"])

    def test_failed_refresh_is_explicit_and_retains_stale_cache_as_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_cache(root / f"{CODE}.json.gz", CODE, [bar()], cached_history()["source"])
            with patch("market_screen.history.urlopen", side_effect=URLError("offline")) as mocked:
                result = fetch_history({"code": CODE, "exchange": "SH"}, TARGET, root, retry_count=1)
            self.assertEqual(2, mocked.call_count)
            self.assertEqual("failed", result["fetch_status"])
            self.assertEqual("failed", result["update_method"])
            self.assertEqual(PREVIOUS, result["bars"][-1]["day"])
            self.assertEqual(2, len(result["errors"]))
            self.assertIn("offline", result["errors"][0])


if __name__ == "__main__":
    unittest.main()
