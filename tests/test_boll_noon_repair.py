"""Historical noon recovery must preserve units, full morning, identity and proof."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_screen.noon_repair import minute_quote, recover_quote, verify_quote_evidence
from market_screen.quotes import parse_sina_quotes
from tests.test_boll_noon_collection import NOW, TODAY, raw_quote
from tests.test_boll_runner import stock


def minute_bytes(*, missing=False, duplicate=False, afternoon=True, code="600000", market=1, volume="10", pre_close=11.79):
    start = datetime.fromisoformat(TODAY + "T09:31:00")
    rows = [(start + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M") + ",11.8,11.8,11.9,11.7," + volume + ",11800,11.8" for i in range(120)]
    if missing:
        del rows[25]
    if duplicate:
        rows.append(rows[25])
    if afternoon:
        rows.append(TODAY + " 13:01,100,100,100,100,999999,99999999,100")
    data = {"code": code, "market": market, "trends": rows}
    if pre_close is not None:
        data["preClose"] = pre_close
    return json.dumps({"data": data}).encode()


class Response:
    def __init__(self, raw): self.raw = raw
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return self.raw


class NoonMinuteRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root / "output/boll/archive/2026-10-14/noon"
        self.directory.mkdir(parents=True)
        raw = raw_quote(stock(), stamp="11:35:00")
        original = self.directory / "quote_sources/original.raw"
        original.parent.mkdir()
        original.write_bytes(raw)
        self.original = parse_sina_quotes(raw)["600000"]
        self.original.update(raw_file=original.relative_to(self.root).as_posix(), retrieved_at=TODAY + "T11:36:00+08:00")

    def test_complete_morning_is_aggregated_and_afternoon_spike_is_ignored(self):
        quote = minute_quote(minute_bytes(), "eastmoney", stock(), TODAY)
        self.assertEqual(120000, quote["volume"])
        self.assertEqual(1416000, quote["amount"])
        self.assertEqual(11.8, quote["close"])
        self.assertEqual("11:30:00", quote["time"])

    def test_missing_duplicate_or_wrong_security_never_recovers(self):
        for options in ({"missing": True}, {"duplicate": True}, {"code": "000001"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                minute_quote(minute_bytes(**options), "eastmoney", stock(), TODAY)

    def test_amount_cannot_be_estimated_and_volume_units_are_checked(self):
        with self.assertRaisesRegex(ValueError, "units_inconsistent"):
            minute_quote(minute_bytes(volume="1000"), "eastmoney", stock(), TODAY)
        payload = json.loads(minute_bytes())
        payload["data"]["trends"][0] = payload["data"]["trends"][0].replace(",11800,", ",-,")
        with self.assertRaises(ValueError):
            minute_quote(json.dumps(payload).encode(), "eastmoney", stock(), TODAY)

    def test_previous_close_requires_dated_security_specific_evidence(self):
        raw = minute_bytes(pre_close=None)
        for reference in (None, {**self.original, "code": "000001"}, {**self.original, "date": "2026-10-14"}):
            with self.subTest(reference=reference), self.assertRaisesRegex(ValueError, "previous_close"):
                minute_quote(raw, "eastmoney", stock(), TODAY, reference)
        self.assertEqual(11.79, minute_quote(raw, "eastmoney", stock(), TODAY, self.original)["prev_close"])

    def test_recovery_archives_exact_bytes_and_replays_against_original_proof(self):
        raw = minute_bytes(pre_close=None)
        with patch("market_screen.noon_repair.urlopen", return_value=Response(raw)) as request:
            quote, attempts = recover_quote(stock(), self.original, self.root, self.directory, TODAY, moment=NOW)
        self.assertEqual(1, request.call_count)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), quote["raw_sha256"])
        self.assertEqual(raw, (self.root / quote["raw_file"]).read_bytes())
        self.assertTrue(verify_quote_evidence(self.root, quote, TODAY, NOW))
        self.assertEqual(["not_noon"], quote["recovery"]["original_rejection"])
        self.assertTrue(attempts[0]["accepted"])
        quote["volume"] = 1
        with self.assertRaisesRegex(ValueError, "raw_fields_mismatch"):
            verify_quote_evidence(self.root, quote, TODAY, NOW)

    def test_raw_reference_tamper_and_two_source_outages_fail_closed(self):
        (self.root / self.original["raw_file"]).write_bytes(b"tampered")
        with patch("market_screen.noon_repair.urlopen", return_value=Response(minute_bytes())) as request:
            quote, attempts = recover_quote(stock(), self.original, self.root, self.directory, TODAY, moment=NOW)
        self.assertIsNone(quote)
        self.assertEqual(2, request.call_count)
        self.assertEqual(2, len(attempts))
        with patch("market_screen.noon_repair.urlopen", side_effect=OSError("provider outage")) as request:
            quote, attempts = recover_quote(stock(), None, self.root, self.directory, TODAY, moment=NOW)
        self.assertIsNone(quote)
        self.assertEqual(2, request.call_count)

    def test_after_cutoff_historical_probe_retains_actual_recovery_time(self):
        late = NOW.replace(hour=17)
        with patch("market_screen.noon_repair.urlopen", return_value=Response(minute_bytes())):
            quote, _ = recover_quote(stock(), self.original, self.root, self.directory, TODAY, moment=late)
        self.assertEqual(late.isoformat(), quote["retrieved_at"])
        self.assertTrue(quote["recovery"]["not_available_at_cutoff"])
        self.assertEqual("11:30:00", quote["time"])


if __name__ == "__main__":
    unittest.main()
