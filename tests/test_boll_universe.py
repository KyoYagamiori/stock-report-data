"""Unit tests for official membership boundaries, completeness and fallbacks."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from market_screen import universe as u


def record(code="600000", exchange="SH", board="main"):
    return {"code": code, "exchange": exchange, "board": board,
            "name": "测试公司", "listing_date": "2000-01-01", "industry": "制造业",
            "security_type": "A_SHARE"}


def sse_payload(rows=None, total=None, page_count=1):
    rows = rows if rows is not None else [{"A_STOCK_CODE": "600000", "SEC_NAME_CN": "浦发银行",
                                          "LIST_DATE": "19991110", "CSRC_CODE_DESC": "金融业"}]
    return json.dumps({"result": rows, "queryDate": "", "pageHelp": {
        "total": len(rows) if total is None else total, "pageNo": 1, "pageCount": page_count,
    }}).encode()


def xlsx_payload(rows):
    headers = ["板块", "A股代码", "A股简称", "A股上市日期", "所属行业"]
    root = ET.Element("worksheet", xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    data = ET.SubElement(root, "sheetData")
    for number, values in enumerate([headers] + rows, 1):
        row = ET.SubElement(data, "row", r=str(number))
        for index, value in enumerate(values):
            cell = ET.SubElement(row, "c", r=f"{chr(65+index)}{number}", t="inlineStr")
            ET.SubElement(ET.SubElement(cell, "is"), "t").text = str(value)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="A股列表" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", ET.tostring(root))
    return payload.getvalue()


def sz_meta(total=1, page_count=1):
    return json.dumps([{"metadata": {"tabkey": "tab1", "catalogid": "1110", "recordcount": total,
                                      "pagesize": 20, "pageno": 1, "pagecount": page_count,
                                      "subname": "2026-10-13 "},
                        "data": [{"agdm": "000001", "agjc": "<a><u>平安银行</u></a>",
                                  "agssrq": "1991-04-03"}], "error": None}]).encode()


class UniverseValidationTests(unittest.TestCase):
    def test_boundary_codes_and_board_counts(self):
        rows = [record(code) for code in ("600000", "601999", "603999", "605999")]
        rows.append(record("688999", "SH", "star"))
        rows.extend(record(code, "SZ") for code in ("000001", "001999", "002999", "003999"))
        rows.extend(record(code, "SZ", "chinext") for code in ("300001", "301999", "302132"))
        counts = u.validate_universe(rows, 12)
        self.assertEqual(counts["exchange_counts"], {"SH": 5, "SZ": 7})
        self.assertEqual(counts["board_counts"]["SZ_chinext"], 3)

    def test_invalid_and_nonordinary_codes_rejected(self):
        for code, exchange in (("60000", "SH"), (600000, "SH"), ("0600000", "SH"),
                               ("600000x", "SH"), ("689009", "SH"), ("900901", "SH"),
                               ("200001", "SZ"), ("920001", "BJ"), ("000001", "SH")):
            with self.subTest(code=code, exchange=exchange), self.assertRaises(ValueError):
                u.validate_universe([record(code, exchange)])

    def test_duplicates_fail_instead_of_silent_deduplication(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            u.validate_universe([record(), record()])
        cdr = record("689009", "SH", "star")
        cdr["security_type"] = "CDR"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            u._ordinary([record(), cdr, cdr])

    def test_code_board_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, "board"):
            u.validate_universe([record("688001", "SH", "main")])

    def test_incomplete_official_sse_page_fails(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            u._parse_sse(sse_payload(total=2), "main")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            u._parse_sse(sse_payload(page_count=2), "main")

    def test_sse_cdr_exclusion_preserves_counts_and_version_unknown(self):
        payload = sse_payload([
            {"A_STOCK_CODE": "688001", "SEC_NAME_CN": "华兴源创", "LIST_DATE": "20190722"},
            {"A_STOCK_CODE": "689009", "SEC_NAME_CN": "九号公司", "LIST_DATE": "20201029"},
        ])
        parsed, meta = u._parse_sse(payload, "star")
        rows, excluded = u._ordinary(parsed)
        self.assertEqual([r["code"] for r in rows], ["688001"])
        self.assertEqual(excluded, [{"code": "689009", "reason": "CDR"}])
        self.assertEqual(meta["reported_total"], 2)
        self.assertIsNone(meta["source_version_date"])

    def test_st_and_suspended_ordinary_names_retained(self):
        row = record()
        row["name"] = "*ST测试"
        row["official_state_code"] = "7"
        rows, _ = u._ordinary([row])
        self.assertEqual(rows, [row])

    def test_b_share_and_bse_exclusion_is_explicit(self):
        rows, excluded = u._ordinary([record(), record("200001", "SZ"),
                                      record("900901"), record("920001", "BJ")])
        self.assertEqual(len(rows), 1)
        self.assertEqual([row["reason"] for row in excluded], ["B_SHARE", "B_SHARE", "BSE"])
        with self.assertRaisesRegex(ValueError, "invalid"):
            u._ordinary([record(), record("8", "BJ")])

    def test_szse_xlsx_preserves_code_and_metadata_version(self):
        xlsx = xlsx_payload([["主板", "000001", "平安银行", "1991-04-03", "J 金融业"]])
        rows, meta = u._parse_szse(sz_meta(), xlsx)
        self.assertEqual(rows[0]["code"], "000001")
        self.assertEqual(meta["source_version_date"], "2026-10-13")
        self.assertTrue(meta["json_xlsx_sample_agrees"])

    def test_szse_incomplete_metadata_page_or_xlsx_fails(self):
        xlsx = xlsx_payload([["主板", "000001", "平安银行", "1991-04-03", "J 金融业"]])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            u._parse_szse(sz_meta(total=2), xlsx)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            u._parse_szse(sz_meta(page_count=2), xlsx)
        with self.assertRaisesRegex(ValueError, "XLSX incomplete"):
            u._parse_szse(sz_meta(), xlsx_payload([]))

    def test_szse_json_xlsx_sample_disagreement_fails(self):
        xlsx = xlsx_payload([["主板", "000002", "万科A", "1991-01-29", "K 房地产"]])
        with self.assertRaisesRegex(ValueError, "disagrees"):
            u._parse_szse(sz_meta(), xlsx)


class UniverseFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def seed(self, **overrides):
        seed = {"records": [record(), record("000001", "SZ")], "version_date": "2026-10-13",
                "retrieved_at": "2026-10-13T16:40:00+08:00", "sources": [u.SSE_ENDPOINT, u.SZSE_XLSX_URL]}
        seed.update(overrides)
        path = self.root / "config/boll_universe_seed.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(seed))

    @patch.object(u, "_live", side_effect=TimeoutError("offline"))
    def test_refresh_failure_falls_back_to_seed_and_persists_hash(self, live):
        self.seed()
        rows, meta = u.load_universe(self.root, "2026-10-15")
        self.assertEqual(len(rows), 2)
        self.assertEqual(meta["mode"], "seed")
        self.assertFalse(meta["fresh"])
        self.assertEqual(meta["version_date"], "2026-10-13")
        self.assertEqual(meta["retrieved_at"], "2026-10-13T16:40:00+08:00")
        self.assertIn("offline", " ".join(meta["freshness_reasons"]))
        self.assertEqual(meta["universe_sha256"], u._sha256((self.root / "output/boll/state/universe.json").read_bytes()))

    @patch.object(u, "_live", side_effect=TimeoutError("offline"))
    def test_refresh_failure_uses_hash_valid_cache_without_redating_it(self, live):
        self.seed()
        _, first_meta = u.load_universe(self.root, "2026-10-14", refresh=False)
        _, meta = u.load_universe(self.root, "2026-10-15")
        self.assertEqual(meta["mode"], "cache")
        self.assertFalse(meta["fresh"])
        self.assertEqual(meta["retrieved_at"], first_meta["retrieved_at"])
        self.assertEqual(meta["version_date"], "2026-10-13")

    def test_corrupt_cache_hash_uses_seed(self):
        self.seed()
        u.load_universe(self.root, "2026-10-14", refresh=False)
        (self.root / "output/boll/state/universe.json").write_text("[]")
        rows, meta = u.load_universe(self.root, "2026-10-15", refresh=False)
        self.assertEqual(len(rows), 2)
        self.assertEqual(meta["mode"], "seed")
        self.assertIn("SHA-256", " ".join(meta["freshness_reasons"]))

    def test_seed_duplicate_fails(self):
        self.seed(records=[record(), record()])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            u.load_universe(self.root, "2026-10-15", refresh=False)

    def test_seed_cdr_excluded_with_expected_ordinary_count(self):
        cdr = record("689009", "SH", "star")
        cdr["security_type"] = "CDR"
        self.seed(records=[record(), cdr], expected_count=1)
        rows, meta = u.load_universe(self.root, "2026-10-15", refresh=False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(meta["excluded"], [{"code": "689009", "reason": "CDR"}])

    def test_no_complete_source_raises(self):
        with self.assertRaisesRegex(ValueError, "No validated complete"):
            u.load_universe(self.root, "2026-10-15", refresh=False)


class OfficialRequestRetryTests(unittest.TestCase):
    def test_connection_reset_retries_once_and_preserves_source_headers(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers = {"Date": "Mon, 26 Oct 2026 07:10:00 GMT"}
        response.read.return_value = b'{"official":true}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "official.json"
            with patch.object(u.urllib.request, "urlopen", side_effect=[ConnectionResetError("reset"), response]) as fetch:
                raw, meta = u._fetch(u.SZSE_JSON_URL, 12, path)
            self.assertEqual(2, fetch.call_count)
            self.assertEqual(2, meta["attempt_count"])
            self.assertIn("reset", meta["earlier_errors"][0])
            self.assertEqual("Mon, 26 Oct 2026 07:10:00 GMT", meta["http_headers"]["date"])
            self.assertEqual(raw, path.read_bytes())
            self.assertEqual(u._sha256(raw), meta["sha256"])

    def test_persistent_failure_remains_a_failure_after_two_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(u.urllib.request, "urlopen", side_effect=ConnectionResetError("reset")) as fetch:
                with self.assertRaises(ConnectionResetError):
                    u._fetch(u.SZSE_JSON_URL, 12, Path(directory) / "official.json")
            self.assertEqual(2, fetch.call_count)


if __name__ == "__main__":
    unittest.main()
