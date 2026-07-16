from __future__ import annotations

import unittest
from copy import deepcopy

from pipeline.contracts import ContractError, load_quality_profiles, load_report_pools, validate_manifest, validate_snapshot
from tests.helpers import valid_manifest, valid_snapshot


class ContractTests(unittest.TestCase):
    def test_snapshot_contract_accepts_valid_payload(self) -> None:
        validate_snapshot(valid_snapshot())

    def test_snapshot_contract_rejects_missing_required_field(self) -> None:
        payload = valid_snapshot()
        del payload["report_cycle"]
        with self.assertRaises(ContractError):
            validate_snapshot(payload)

    def test_snapshot_contract_rejects_timezone_free_timestamp(self) -> None:
        payload = valid_snapshot()
        payload["started_at"] = "2026-07-16T11:36:00"
        with self.assertRaises(ContractError):
            validate_snapshot(payload)

    def test_snapshot_contract_rejects_wrong_cycle(self) -> None:
        payload = valid_snapshot()
        payload["report_cycle"] = "2026-07-16-early"
        with self.assertRaises(ContractError):
            validate_snapshot(payload)

    def test_manifest_contract_accepts_immutable_pointer(self) -> None:
        validate_manifest(valid_manifest())

    def test_manifest_contract_rejects_latest_as_authoritative_file(self) -> None:
        payload = valid_manifest()
        payload["snapshots"]["noon"]["selected_file"] = "output/latest/noon/report_data_compact.json"
        with self.assertRaises(ContractError):
            validate_manifest(payload)

    def test_manifest_contract_rejects_pointer_type_mismatch(self) -> None:
        payload = valid_manifest()
        payload["snapshots"]["noon"]["snapshot_type"] = "early"
        with self.assertRaises(ContractError):
            validate_manifest(payload)

    def test_report_pool_contract_is_frozen(self) -> None:
        pools = load_report_pools()
        self.assertEqual(10, len(pools["core"]))
        self.assertEqual(14, len(pools["watch"]))
        longi = next(record for record in pools["core"] if record["code"] == "600584")
        self.assertTrue(longi["locked"])

    def test_quality_profiles_include_all_profiles(self) -> None:
        profiles = load_quality_profiles()["profiles"]
        expected = {
            "trading_preopen",
            "trading_intraday",
            "trading_noon",
            "trading_close",
            "trading_evening",
            "non_trading",
        }
        self.assertEqual(expected, set(profiles))


if __name__ == "__main__":
    unittest.main()
