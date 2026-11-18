from datetime import date, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research_system.history_qlib import FIELDS, QlibRelease
from research_system.history_source import digest, select_cohort
from research_system.vcp_cohort_training import additional_codes, stock_samples
from tests.test_research_history_qlib import archive_fixture


class VcpCohortTrainingTests(unittest.TestCase):
    def test_append_only_historical_membership_has_original_seed_order(self):
        mainboard = [f"sh.{code}" for code in range(600000, 601000)]
        mainboard += [f"sz.{code:06}" for code in range(600)]
        members = [{"code": code} for code in mainboard + ["sh.688001", "sz.300001"]]
        seed = "origin"
        original = select_cohort(members, 512, seed)
        added = additional_codes(members, original, seed, 2)
        expected = sorted(mainboard, key=lambda code: digest(f"{seed}:{code}".encode()))[:1536]
        self.assertEqual(expected, original + added)
        self.assertEqual(1536, len(set(original + added)))
        with self.assertRaisesRegex(ValueError, "original_membership_mismatch"):
            additional_codes(members, list(reversed(original)), seed, 2)

    def test_public_release_expansion_extracts_only_supplied_cohort_and_benchmark(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive, _, config, _ = archive_fixture(root, extra=True)

            def selector(members):
                self.assertIn({"code": "sh.600001"}, members)
                return ["sh.600001"]

            with QlibRelease(root, config, archive=archive, cohort_selector=selector) as release:
                self.assertEqual({(symbol, field) for symbol in ("sh600001", "sh000300") for field in FIELDS},
                                 set(release.binary))

    def test_added_cohort_keeps_first_observation_and_seals_future_prices(self):
        config_file = Path(__file__).resolve().parents[1] / "config/vcp_trigger_training.json"
        config = json.loads(config_file.read_bytes())
        start = date(2025, 1, 1)
        calendar = [(start + timedelta(days=i)).isoformat() for i in range(167)]
        code = "sz.000001"
        source = [{"date": day, "code": code, "open": 9.8, "close": 9.8, "high": 10.4, "low": 9.4,
                   "volume": 100, "amount": 50_000_000, "preclose": 9.8, "tradestatus": "1",
                   "isST": "unknown", "adjustflag": "3"} for day in calendar]
        source[162].update(close=10.2, volume=180)
        source[-1]["close"] = "invalid_future_data"
        config["exclude_reviewed_from"] = calendar[-1]

        def observation(bars):
            return {"matched": True, "stage": "near_pivot", "origin": calendar[152],
                    "base_asof": bars[-2]["day"], "pivot": 10., "invalidation_below": 9.,
                    "atr20": 1., "reference_volume": 100., "contraction_count": 2,
                    "tight5_range_pct": 3., "risk_from_pivot_pct": 10., "distance_to_pivot_atr": .2}

        with patch("research_system.vcp_cohort_training.vcp.analyze", side_effect=observation):
            rows, audits, counts = stock_samples(code, source, "hash", (calendar[0], calendar[-1]),
                                                 calendar[0], calendar[:-1], {}, config)
        self.assertEqual(166, counts["pre_cutoff_bars"])
        self.assertEqual(6, counts["repeated_origin_suppressed"])
        self.assertEqual(1, len(rows))
        self.assertEqual(1, len(audits))
        self.assertEqual(calendar[159], rows[0]["date"])
        self.assertEqual(calendar[161], rows[0]["label_end_date"])
        self.assertEqual("expired_without_confirmation", rows[0]["execution_state"])
        self.assertEqual(audits[0]["sha256"], rows[0]["execution_audit_sha256"])


if __name__ == "__main__":
    unittest.main()
