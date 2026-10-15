import json
from pathlib import Path
import shutil
import tempfile
import unittest

from market_screen.universe import load_universe, membership_current


class ShippedConfigurationTests(unittest.TestCase):
    def test_shipped_universe_seed_passes_the_real_loader(self):
        source = Path(__file__).resolve().parents[1] / "config/boll_universe_seed.json"
        seed = json.loads(source.read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            shutil.copy(source, root / "config/boll_universe_seed.json")
            rows, meta = load_universe(root, seed["version_date"], refresh=False)
            self.assertEqual(len(rows), seed["expected_count"])
            self.assertGreater(len(rows), 5000)
            self.assertEqual(len(rows), len({row["code"] for row in rows}))
            self.assertFalse(meta["fresh"])
            self.assertTrue(membership_current(meta, seed["version_date"]))
            self.assertFalse(membership_current(meta, "2099-01-01"))

    def test_archive_requires_source_hashes_and_same_date(self):
        meta = {"fresh": False, "version_date": "2026-10-15", "retrieved_at": "2026-10-15T10:00:00+08:00"}
        self.assertFalse(membership_current(meta, "2026-10-15"))
        meta["sources"] = {key: {"http_status": 200, "http_server_date": "2026-10-15", "sha256": "a" * 64,
                                  "source_version_date": "2026-10-15"}
                           for key in ("sse_main", "sse_star", "szse_metadata", "szse_xlsx")}
        self.assertTrue(membership_current(meta, "2026-10-15"))
        meta["sources"]["sse_main"]["sha256"] = "wrong"
        self.assertFalse(membership_current(meta, "2026-10-15"))


if __name__ == "__main__":
    unittest.main()
