from __future__ import annotations

import unittest

from pipeline.render import render_health, render_manifest, render_snapshot
from tests.helpers import valid_manifest, valid_snapshot


class RenderTests(unittest.TestCase):
    def test_snapshot_markdown_contains_contract_and_technical_columns(self) -> None:
        snapshot = valid_snapshot()
        snapshot["stocks"][0].update(
            {
                "latest_price": 101.23,
                "pct_change": 2.34,
                "ma5": 99.0,
                "ma10": 98.0,
                "ma20": 95.0,
                "ma60": 90.0,
                "box_lower": 88.0,
                "box_upper": 105.0,
                "quote_time": "2026-07-16T11:30:05+08:00",
            }
        )
        markdown = render_snapshot(snapshot)
        self.assertIn(snapshot["snapshot_id"], markdown)
        self.assertIn("MA60", markdown)
        self.assertIn("箱底", markdown)
        self.assertIn("105", markdown)

    def test_manifest_markdown_explains_authoritative_archive(self) -> None:
        manifest = valid_manifest()
        markdown = render_manifest(manifest)
        self.assertIn("report_readiness", str(manifest))
        self.assertIn("不可变 JSON", markdown)
        self.assertIn(manifest["snapshots"]["noon"]["selected_file"], markdown)

    def test_health_markdown_contains_failure_reason(self) -> None:
        markdown = render_health(
            {
                "status": "not_ready",
                "snapshot_type": "noon",
                "quality_grade": "F",
                "published": False,
                "reason": "quote time invalid",
            }
        )
        self.assertIn("quote time invalid", markdown)
        self.assertIn("是否发布：否", markdown)


if __name__ == "__main__":
    unittest.main()
