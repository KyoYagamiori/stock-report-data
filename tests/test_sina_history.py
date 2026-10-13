import json
import unittest
from unittest.mock import MagicMock, patch

from pipeline.adapters.sina_history import SinaHistory


class HistoryFallbackTests(unittest.TestCase):
    def response(self, code="688700"):
        result = MagicMock()
        result.__enter__.return_value.read.return_value = json.dumps({"data": {
            "code": code, "trends": ["2026-10-13 11:30,53.13,53.28,53.33,53.13,226,1204023.35,51.047"]
        }}).encode()
        return result

    def test_fallback_converts_lots_to_shares_once_and_preserves_cny(self):
        with patch("pipeline.adapters.sina_history.urlopen", return_value=self.response()):
            frame = SinaHistory().stock_zh_a_minute_fallback("sh688700")
        self.assertEqual(22600, frame.iloc[0]["volume"])
        self.assertEqual("1204023.35", frame.iloc[0]["amount"])
        self.assertIn("手转股", frame.attrs["source"])

    def test_fallback_rejects_response_for_another_security(self):
        with patch("pipeline.adapters.sina_history.urlopen", return_value=self.response("600584")):
            with self.assertRaisesRegex(ValueError, "wrong security"):
                SinaHistory().stock_zh_a_minute_fallback("sh688700")
