from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import pandas as pd

from ma5_system.bootstrap import (
    _fetch_ths_board_members,
    _parse_sw_industry_files,
    bootstrap_industry_map,
    merge_history,
)


class _FallbackAK:
    @staticmethod
    def stock_board_industry_name_em() -> pd.DataFrame:
        raise ConnectionError("eastmoney unavailable")

    @staticmethod
    def stock_board_industry_name_ths() -> pd.DataFrame:
        return pd.DataFrame([{"name": "半导体", "code": "881121"}])


class _PrimaryAK:
    @staticmethod
    def stock_board_industry_name_em() -> pd.DataFrame:
        return pd.DataFrame([{"板块名称": "半导体"}])

    @staticmethod
    def stock_board_industry_cons_em(symbol: str) -> pd.DataFrame:
        assert symbol == "半导体"
        return pd.DataFrame(
            [
                {"代码": "600001", "名称": "甲公司"},
                {"代码": "000002", "名称": "乙公司"},
            ]
        )

    @staticmethod
    def stock_board_industry_name_ths() -> pd.DataFrame:
        raise AssertionError("THS should not be used when the primary map is complete")


class _Response:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code


def _write_history(root: Path) -> None:
    path = root / "output" / "ma5" / "state" / "daily_history.csv.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"code": "600001", "date": "2026-07-16"},
            {"code": "000002", "date": "2026-07-16"},
        ]
    ).to_csv(path, index=False, compression="gzip")


class MA5BootstrapTests(unittest.TestCase):
    def test_merge_history_rejects_false_green_below_coverage_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "output" / "ma5" / "bootstrap"
            source.mkdir(parents=True, exist_ok=True)
            pd.DataFrame([{"code": "600001", "date": "2026-07-17", "close": 10}]).to_csv(
                source / "history-shard-00.csv.gz",
                index=False,
                compression="gzip",
            )
            (source / "history-shard-00.csv.json").write_text(
                json.dumps({"codes": 2, "successful_codes": 1}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "1/2 codes"):
                merge_history(root, minimum_coverage=0.95)
            status = json.loads(
                (root / "output" / "ma5" / "state" / "history_bootstrap.status.json").read_text(encoding="utf-8")
            )
            self.assertFalse(status["ready"])
            self.assertEqual(0.5, status["coverage"])

    def test_merge_history_accepts_complete_shards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "output" / "ma5" / "bootstrap"
            source.mkdir(parents=True, exist_ok=True)
            for index, code in enumerate(("600001", "000002")):
                pd.DataFrame([{"code": code, "date": "2026-07-17", "close": 10 + index}]).to_csv(
                    source / f"history-shard-{index:02d}.csv.gz",
                    index=False,
                    compression="gzip",
                )
                (source / f"history-shard-{index:02d}.csv.json").write_text(
                    json.dumps({"codes": 1, "successful_codes": 1}),
                    encoding="utf-8",
                )
            output = merge_history(root, minimum_coverage=0.95)
            self.assertTrue(output.exists())
            status = json.loads(
                (root / "output" / "ma5" / "state" / "history_bootstrap.status.json").read_text(encoding="utf-8")
            )
            self.assertTrue(status["ready"])
            self.assertEqual(1.0, status["coverage"])
            self.assertEqual(2, status["rows"])
            self.assertEqual(2, status["source_rows"])
            self.assertEqual(2, status["stored_codes"])
            self.assertEqual(1, status["rows_per_code_min"])
            self.assertEqual(1.0, status["rows_per_code_median"])
            self.assertEqual(1, status["rows_per_code_max"])

    def test_industry_bootstrap_falls_back_to_official_sw_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_history(root)

            def sw_fetcher() -> dict[str, dict[str, str]]:
                return {
                    "600001": {"code": "600001", "name": "", "industry": "半导体"},
                    "000002": {"code": "000002", "name": "", "industry": "房地产开发"},
                }

            output = bootstrap_industry_map(
                root,
                workers=1,
                ak_module=_FallbackAK,
                sw_fetcher=sw_fetcher,
                ths_fetcher=lambda *_: self.fail("THS should be skipped after the SW map passes"),
                minimum_coverage=1.0,
                minimum_records=1,
            )

            result = pd.read_csv(output, dtype={"code": str})
            self.assertEqual(["000002", "600001"], result["code"].tolist())
            self.assertEqual(["房地产开发", "半导体"], result["industry"].tolist())
            status = json.loads(output.with_suffix(".status.json").read_text(encoding="utf-8"))
            self.assertTrue(status["ready"])
            self.assertEqual(1.0, status["coverage"])
            self.assertEqual(2, status["sources"]["shenwan"]["records"])
            self.assertTrue(status["sources"]["ths"]["skipped"])

    def test_industry_bootstrap_uses_ths_as_tertiary_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_history(root)

            def ths_fetcher(industry: str, board_code: str) -> pd.DataFrame:
                self.assertEqual("半导体", industry)
                self.assertEqual("881121", board_code)
                return pd.DataFrame(
                    [
                        {"代码": "600001", "名称": "甲公司"},
                        {"代码": "000002", "名称": "乙公司"},
                    ]
                )

            output = bootstrap_industry_map(
                root,
                workers=1,
                ak_module=_FallbackAK,
                sw_fetcher=lambda: (_ for _ in ()).throw(ConnectionError("SWS unavailable")),
                ths_fetcher=ths_fetcher,
                minimum_coverage=1.0,
                minimum_records=1,
            )
            status = json.loads(output.with_suffix(".status.json").read_text(encoding="utf-8"))
            self.assertTrue(status["ready"])
            self.assertEqual(2, status["sources"]["ths"]["records"])

    def test_complete_primary_map_skips_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_history(root)
            output = bootstrap_industry_map(
                root,
                workers=1,
                ak_module=_PrimaryAK,
                minimum_coverage=1.0,
                minimum_records=1,
            )
            status = json.loads(output.with_suffix(".status.json").read_text(encoding="utf-8"))
            self.assertTrue(status["sources"]["ths"]["skipped"])
            self.assertTrue(status["sources"]["shenwan"]["skipped"])
            self.assertEqual(2, status["sources"]["eastmoney"]["records"])

    def test_sw_files_select_latest_stock_assignment_and_level_two_name(self) -> None:
        stock_buffer = BytesIO()
        pd.DataFrame(
            [
                {"股票代码": "600001", "计入日期": "2020-01-01", "行业代码": "270101", "更新日期": "2020-01-02"},
                {"股票代码": "600001", "计入日期": "2021-07-30", "行业代码": "270107", "更新日期": "2025-01-01"},
                {"股票代码": "000002", "计入日期": "2021-07-30", "行业代码": "430101", "更新日期": "2025-01-01"},
            ]
        ).to_excel(stock_buffer, index=False)

        mapping_buffer = BytesIO()
        columns = ["旧版一级行业", "旧版二级行业", "旧版三级行业", "行业代码", "新版一级行业", "新版二级行业", "新版三级行业", "行业代码.1"]
        mapping = pd.DataFrame(
            [
                [None, None, None, None, "电子", None, None, "270000"],
                [None, None, None, None, None, "半导体", None, "270100"],
                [None, None, None, None, "房地产", None, None, "430000"],
                [None, None, None, None, None, "房地产开发", None, "430100"],
            ],
            columns=columns,
        )
        with pd.ExcelWriter(mapping_buffer, engine="openpyxl") as writer:
            mapping.to_excel(writer, sheet_name="旧版", index=False)
            mapping.to_excel(writer, sheet_name="新版", index=False)

        records = _parse_sw_industry_files(stock_buffer.getvalue(), mapping_buffer.getvalue())
        self.assertEqual("半导体", records["600001"]["industry"])
        self.assertEqual("房地产开发", records["000002"]["industry"])

    def test_ths_pagination_uses_the_site_route_order_and_refreshes_token(self) -> None:
        first_page = """
        <table><tr><th>代码</th><th>名称</th></tr><tr><td>600001</td><td>甲公司</td></tr></table>
        <span class="page_info">1/2</span>
        """
        second_page = """
        <table><tr><th>代码</th><th>名称</th></tr><tr><td>000002</td><td>乙公司</td></tr></table>
        """
        urls: list[str] = []
        cookies: list[str] = []

        def fake_get(url: str, *, headers: dict[str, str], timeout: int) -> _Response:
            self.assertEqual(20, timeout)
            urls.append(url)
            cookies.append(headers["Cookie"])
            return _Response(first_page if len(urls) == 1 else second_page)

        tokens = iter(["token-1", "token-2"])
        result = _fetch_ths_board_members(
            "半导体",
            "881121",
            http_get=fake_get,
            token_factory=lambda: next(tokens),
            sleeper=lambda _: None,
        )

        self.assertEqual(["600001", "000002"], result["代码"].astype(str).str.zfill(6).tolist())
        self.assertEqual(
            "https://q.10jqka.com.cn/thshy/detail/code/881121/field/199112/order/desc/page/2/ajax/1/",
            urls[1],
        )
        self.assertEqual(["v=token-1", "v=token-2"], cookies)


if __name__ == "__main__":
    unittest.main()
