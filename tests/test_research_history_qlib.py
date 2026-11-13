from copy import deepcopy
import io
import json
import os
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from research_system.early_model import validate
from research_system.history_dataset import entry_rejection, normalize
from research_system.history_qlib import METADATA, FIELDS, QlibRelease, decode_binary, file_digest, safe_member, verify_archive
from tests.test_research_early_model import early_dataset


def archive_fixture(root, extra=False):
    calendar = ["2018-01-02", "2018-01-03", "2018-01-04", "2018-01-05", "2018-01-08"]
    future = calendar + ["2018-01-09"]
    members = "SH600000\t2018-01-02\t2018-01-08\nSZ000001\t2018-01-02\t2018-01-08\n"
    if extra:
        members += "SH600001\t2018-01-02\t2018-01-08\n"
    archive = root / "qlib_bin.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name in METADATA:
            data = (("\n".join(future if name.endswith("day_future.txt") else calendar) + "\n")
                    if name.startswith("calendars/") else members).encode()
            info = tarfile.TarInfo("qlib_bin/" + name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for symbol in ("sh600000", "sz000001", "sh000300") + (("sh600001",) if extra else ()):
            for field in FIELDS:
                value = {"open": 5., "close": 5., "high": 5.1, "low": 4.9,
                         "volume": 20., "amount": 10., "factor": .5}[field]
                data = struct.pack("<6f", 0., *([value] * 5))
                info = tarfile.TarInfo(f"qlib_bin/features/{symbol}/{field}.day.bin")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    config = {"release_tag": "2018-01-08", "history_start": "2018-01-02", "history_end": "2018-01-08",
              "cohort_date": "2018-01-02", "sample_size": 2, "seed": "fixed", "benchmark_code": "sh.000300",
              "release_archive_bytes": archive.stat().st_size, "release_archive_sha256": file_digest(archive),
              "release_dolt_commit": "a" * 32}
    manifest = {"release_tag": config["release_tag"], "target_trade_date": config["history_end"],
        "archive_sha256": "sha256:" + config["release_archive_sha256"], "archive_size_bytes": config["release_archive_bytes"],
        "dolt_commit": config["release_dolt_commit"], "qlib_commit": "b87a2c294d364a33fb739359886acffe8ec907d1",
        "image_digest": "sha256:" + "b" * 64, "future_start_date": future[-1], "future_end_date": future[-1]}
    archive.with_name("qlib_bin.manifest.json").write_text(json.dumps(manifest))
    return archive, manifest, config, calendar


class PublicQlibHistoryTests(unittest.TestCase):
    def test_cohort_expansion_preserves_previous_extraction_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, _, config, _ = archive_fixture(root, extra=True)
            with patch.dict(os.environ, {"STOCK_QLIB_ARCHIVE": str(archive)}):
                with QlibRelease(root, config) as first:
                    old = deepcopy(first.provenance)
                path = root / old["extraction_receipt_file"]
                original = path.read_bytes()
                with QlibRelease(root, {**config, "sample_size": 3}) as second:
                    self.assertNotEqual(old["extraction_receipt_file"], second.provenance["extraction_receipt_file"])
                self.assertEqual(original, path.read_bytes())
                self.assertEqual(old["extraction_receipt_sha256"], file_digest(path))

    def test_original_binary_units_are_recovered_without_inventing_st_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, manifest, config, calendar = archive_fixture(root)
            with patch.dict(os.environ, {"STOCK_QLIB_ARCHIVE": str(archive)}), QlibRelease(root, config) as source:
                rows = source.query({"method": "query_history_k_data_plus", "kwargs": {
                    "code": "sh.600000", "start_date": calendar[0], "end_date": calendar[-1], "frequency": "d", "adjustflag": "3"}})
                self.assertEqual(10., rows[0]["close"])
                self.assertEqual(1000., rows[0]["volume"])
                self.assertEqual(10000., rows[0]["amount"])
                self.assertEqual("unknown", rows[0]["isST"])
                self.assertEqual("unavailable_st_price_only_research", source.status_basis)
                self.assertEqual(calendar, [r["date"] for r in rows])
                with self.assertRaises(ValueError): normalize(rows)
                self.assertTrue(normalize(rows, allow_unknown_status=True))

    def test_release_tampering_or_tag_mismatch_blocks_import(self):
        with tempfile.TemporaryDirectory() as directory:
            archive, manifest, config, _ = archive_fixture(Path(directory))
            verify_archive(archive, manifest, config)
            with self.assertRaises(ValueError): verify_archive(archive, {**manifest, "target_trade_date": "2099-01-01"}, config)
            archive.write_bytes(archive.read_bytes() + b"tampered")
            with self.assertRaises(ValueError): verify_archive(archive, manifest, config)

    def test_unsafe_archive_paths_and_links_are_rejected(self):
        for name, kind in (("../escape", tarfile.REGTYPE), ("qlib_bin/link", tarfile.SYMTYPE)):
            entry = tarfile.TarInfo(name)
            entry.type = kind
            with self.assertRaises(ValueError): safe_member(entry, set())

    def test_float_calendar_offset_and_out_of_range_binary_are_rejected(self):
        for raw in (struct.pack("<2f", .5, 1.), struct.pack("<3f", 1., 1., 2.), b"x"):
            with self.assertRaises(ValueError): decode_binary(raw, ["2018-01-02"])

    def test_unknown_status_does_not_silently_become_an_eligible_formal_entry(self):
        bar = {"tradestatus": "1", "isST": "unknown", "volume": 100., "open": 10., "close": 10.,
               "high": 10.1, "low": 9.9, "preclose": 10.}
        self.assertEqual("risk_warning_at_entry", entry_rejection(bar))
        self.assertIsNone(entry_rejection(bar, allow_unknown_status=True))

    def test_price_only_labels_are_accepted_only_by_explicit_pilot_validation(self):
        data = early_dataset(20)
        data["metadata"].update(scope="pilot", universe_basis="fixed_historical_origin_cohort",
            benchmark_basis="provider_index_not_independently_verified",
            corporate_actions_basis="causal_preclose_chain_raw_execution_retained",
            entry_policy="simulated_next_session_open_no_wait", execution_limits_basis="price_only_proxy_st_status_unknown",
            source_provider="qlib_public_release", st_status="not_supplied_never_assumed_normal")
        self.assertTrue(validate(data, scope="pilot"))
        with self.assertRaises(ValueError): validate(data)
        changed = deepcopy(data)
        changed["metadata"]["st_status"] = "assumed_normal"
        with self.assertRaises(ValueError): validate(changed, scope="pilot")


if __name__ == "__main__":
    unittest.main()

