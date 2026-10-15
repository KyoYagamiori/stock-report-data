from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError
from zoneinfo import ZoneInfo

from market_screen.quotes import fetch_quotes, parse_sina_quotes, validate_quote


TZ = ZoneInfo("Asia/Shanghai")


def quote_bytes(symbol="sh600938", *, name="中国海油", day="2026-10-15", stamp="10:07:00",
                open_=35.2, prev_close=35.1, close=35.5, high=35.8, low=35.0,
                volume=123456, amount=4382688, **overrides):
    fields = ["0"] * 33
    for index, value in {0: name, 1: open_, 2: prev_close, 3: close, 4: high, 5: low,
                         8: volume, 9: amount, 30: day, 31: stamp, 32: "00"}.items():
        fields[index] = str(value)
    for index, value in overrides.items():
        fields[int(index)] = str(value)
    return f'var hq_str_{symbol}="{",".join(fields)}";\n'.encode("gb18030")


def parsed_quote(**kwargs):
    return next(iter(parse_sina_quotes(quote_bytes(**kwargs)).values()))


class FakeResponse:
    status = 200

    def __init__(self, raw):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.raw


class QuoteParserTests(unittest.TestCase):
    def test_units_name_and_raw_digest_are_retained(self):
        raw = quote_bytes()
        row = parse_sina_quotes(raw)["600938"]
        self.assertEqual("中国海油", row["name"])
        self.assertEqual("valid", row["status"])
        self.assertEqual(123456, row["volume"])
        self.assertEqual(4382688, row["amount"])
        self.assertEqual("2026-10-15", row["date"])
        self.assertEqual("10:07:00", row["time"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), row["raw_sha256"])
        self.assertIsNone(row["retrieved_at"])

    def test_no_trades_is_not_labeled_suspension(self):
        row = parsed_quote(open_=0, close=0, high=0, low=0, volume=0, amount=0)
        self.assertEqual("no_trades", row["status"])
        self.assertIn("does not establish suspension", row["trade_state_note"])
        self.assertIn("no_trades", validate_quote(row, "2026-10-15", "intraday",
                                                 now=datetime(2026, 10, 15, 10, 8, tzinfo=TZ)))

    def test_empty_malformed_and_omitted_quotes_are_distinct(self):
        raw = b'var hq_str_sh600938="";\nvar hq_str_sz000001="malformed";'
        rows = parse_sina_quotes(raw)
        self.assertEqual("missing", rows["600938"]["status"])
        self.assertEqual("invalid", rows["000001"]["status"])
        self.assertNotIn("300001", rows)

    def test_nonfinite_negative_and_incoherent_ohlc_fail(self):
        for kwargs in ({"close": "nan"}, {"volume": -1}, {"high": 35.3},
                       {"low": 35.7}, {"volume": 0}, {"amount": 0}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual("invalid", parsed_quote(**kwargs)["status"])

    def test_bad_dates_times_and_duplicate_codes_fail(self):
        for kwargs in ({"day": "2026-02-30"}, {"stamp": "25:00:00"}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual("invalid", parsed_quote(**kwargs)["status"])
        duplicated = parse_sina_quotes(quote_bytes() + quote_bytes(close=35.6))["600938"]
        self.assertEqual("invalid", duplicated["status"])
        self.assertIn("duplicate_code", duplicated["parse_errors"])


class QuoteTimeGateTests(unittest.TestCase):
    def test_exact_date_required_for_every_phase(self):
        for phase, stamp in (("close", "15:00:00"), ("noon", "11:30:00"),
                             ("intraday", "10:07:00")):
            row = parsed_quote(day="2026-10-14", stamp=stamp)
            with self.subTest(phase=phase):
                self.assertIn("date_mismatch", validate_quote(row, "2026-10-15", phase,
                    now=datetime(2026, 10, 15, 16, tzinfo=TZ)))
                self.assertEqual("2026-10-14", row["date"])

    def test_close_requires_at_least_1500(self):
        for stamp, accepted in (("14:59:59", False), ("15:00:00", True), ("15:12:00", True)):
            with self.subTest(stamp=stamp):
                reasons = validate_quote(parsed_quote(stamp=stamp), "2026-10-15", "close")
                self.assertEqual(accepted, not reasons)

    def test_noon_rejects_lunch_or_outside_cutoff_stamp(self):
        for stamp, accepted in (("11:28:59", False), ("11:29:00", True),
                                ("11:30:00", True), ("11:30:59", True),
                                ("11:31:00", False), ("12:00:00", False)):
            with self.subTest(stamp=stamp):
                reasons = validate_quote(parsed_quote(stamp=stamp), "2026-10-15", "noon")
                self.assertEqual(accepted, not reasons)

    def test_intraday_enforces_sessions_and_future_time(self):
        for stamp, accepted in (("09:29:59", False), ("09:30:00", True),
                                ("11:30:00", True), ("12:00:00", False),
                                ("13:00:00", True), ("15:01:00", False)):
            with self.subTest(stamp=stamp):
                reasons = validate_quote(parsed_quote(stamp=stamp), "2026-10-15", "intraday",
                    now=datetime(2026, 10, 15, 16, tzinfo=TZ))
                self.assertEqual(accepted, not reasons)
        future = parsed_quote(stamp="10:08:00")
        self.assertIn("future_timestamp", validate_quote(future, "2026-10-15", "intraday",
            now=datetime(2026, 10, 15, 10, 7, 59, tzinfo=TZ)))

    def test_reference_clock_is_required_and_can_be_utc(self):
        row = parsed_quote()
        self.assertIn("clock_unavailable", validate_quote(row, "2026-10-15", "intraday"))
        row["retrieved_at"] = "2026-10-15T02:07:01+00:00"
        self.assertEqual([], validate_quote(row, "2026-10-15", "intraday"))
        row["retrieved_at"] = "2026-10-15T02:06:59+00:00"
        self.assertIn("future_timestamp", validate_quote(row, "2026-10-15", "intraday"))
        row["retrieved_at"] = "invalid"
        self.assertIn("invalid_clock", validate_quote(row, "2026-10-15", "intraday"))

    def test_bad_configuration_and_missing_row_fail_explicitly(self):
        with self.assertRaises(ValueError):
            validate_quote(parsed_quote(), "2026-10-15", "lunch")
        with self.assertRaises(ValueError):
            validate_quote(parsed_quote(), "2026-02-30", "intraday")
        self.assertEqual(["missing"], validate_quote({"status": "missing"}, "2026-10-15", "close"))


class QuoteCollectorTests(unittest.TestCase):
    def test_archives_actual_bytes_and_retains_all_requested_codes(self):
        raw = quote_bytes() + b'var hq_str_sz000001="";\n'
        universe = [{"code": "600938", "name": "海油", "exchange": "SH"},
                    {"code": "000001", "name": "平安银行", "exchange": "SZ"},
                    {"code": "300001", "name": "特锐德", "exchange": "SZ"}]
        with tempfile.TemporaryDirectory() as directory:
            with patch("market_screen.quotes.urlopen", return_value=FakeResponse(raw)) as mocked:
                rows, meta = fetch_quotes(universe, Path(directory))
            self.assertEqual({"600938", "000001", "300001"}, set(rows))
            self.assertEqual("valid", rows["600938"]["status"])
            self.assertEqual("missing", rows["000001"]["status"])
            self.assertEqual("missing", rows["300001"]["status"])
            self.assertEqual(1, mocked.call_count)
            self.assertEqual(3, meta["requested_count"])
            self.assertEqual({"valid": 1, "no_trades": 0, "invalid": 0, "missing": 2}, meta["status_counts"])
            for row in rows.values():
                self.assertEqual(raw, Path(row["raw_file"]).read_bytes())
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row["raw_sha256"])
                self.assertIn("sh600938,sz000001,sz300001", row["source_url"])
                self.assertIsNotNone(datetime.fromisoformat(row["retrieved_at"]).tzinfo)
            sidecars = list((Path(directory) / "quote_sources").glob("*.json"))
            self.assertEqual(1, len(sidecars))
            self.assertEqual(len(raw), json.loads(sidecars[0].read_text())["bytes"])

    def test_network_retries_at_most_once_and_preserves_failure_rows(self):
        universe = [{"code": "600938", "name": "中国海油", "exchange": "SH"}]
        with tempfile.TemporaryDirectory() as directory:
            with patch("market_screen.quotes.urlopen", side_effect=URLError("offline")) as mocked:
                rows, meta = fetch_quotes(universe, Path(directory))
            self.assertEqual(2, mocked.call_count)
            self.assertEqual("missing", rows["600938"]["status"])
            self.assertIsNone(rows["600938"]["raw_sha256"])
            self.assertIn("offline", rows["600938"]["fetch_error"])
            self.assertEqual(1, meta["failed_batches"])
            self.assertEqual(2, len(meta["errors"]))

    def test_retry_success_and_empty_bytes_are_archived(self):
        universe = [{"code": "600938", "name": "中国海油"}]
        with tempfile.TemporaryDirectory() as directory:
            with patch("market_screen.quotes.urlopen", side_effect=[FakeResponse(b""), FakeResponse(quote_bytes())]):
                rows, meta = fetch_quotes(universe, Path(directory))
            self.assertEqual("valid", rows["600938"]["status"])
            self.assertEqual(0, meta["failed_batches"])
            self.assertEqual("empty_response", meta["errors"][0]["error"])
            raws = list((Path(directory) / "quote_sources").glob("*.raw"))
            self.assertEqual(2, len(raws))
            self.assertIn(b"", [path.read_bytes() for path in raws])

    def test_batch_size_worker_limit_and_unexpected_symbols(self):
        universe = [{"code": f"{number:06d}", "exchange": "SZ"} for number in range(1, 206)]
        urls = []

        def respond(request, timeout):
            urls.append(request.full_url)
            symbols = request.full_url.split("list=", 1)[1].split(",")
            return FakeResponse(b"".join(quote_bytes(symbol, name="测试") for symbol in symbols)
                                + quote_bytes("sh600938"))

        with tempfile.TemporaryDirectory() as directory:
            with patch("market_screen.quotes.urlopen", side_effect=respond):
                rows, meta = fetch_quotes(universe, Path(directory), workers=99)
            self.assertEqual(205, len(rows))
            self.assertNotIn("600938", rows)
            self.assertEqual([5, 100, 100], sorted(len(url.split("list=")[1].split(",")) for url in urls))
            self.assertEqual(6, meta["workers"])
            self.assertEqual(205, meta["status_counts"]["valid"])

    def test_repeated_runs_do_not_overwrite_raw_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("market_screen.quotes.urlopen", return_value=FakeResponse(quote_bytes())):
                first, _ = fetch_quotes([{"code": "600938"}], Path(directory))
                second, _ = fetch_quotes([{"code": "600938"}], Path(directory))
            self.assertNotEqual(first["600938"]["raw_file"], second["600938"]["raw_file"])
            self.assertTrue(Path(first["600938"]["raw_file"]).exists())

    def test_invalid_inputs_fail_before_network_and_empty_universe_is_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("market_screen.quotes.urlopen") as mocked:
                with self.assertRaises(ValueError):
                    fetch_quotes([{"code": "123"}], Path(directory))
                with self.assertRaises(ValueError):
                    fetch_quotes([{"code": "600938"}, {"code": "600938"}], Path(directory))
                with self.assertRaises(ValueError):
                    fetch_quotes([{"code": "600938"}], Path(directory), timeout=0)
                with self.assertRaises(ValueError):
                    fetch_quotes([{"code": "600938"}], Path(directory), workers=0)
                rows, meta = fetch_quotes([], Path(directory))
            mocked.assert_not_called()
            self.assertEqual({}, rows)
            self.assertEqual(0, meta["batch_count"])
            self.assertEqual(0, meta["returned_count"])


if __name__ == "__main__":
    unittest.main()
