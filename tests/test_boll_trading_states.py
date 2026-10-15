import unittest
from market_screen.runner import assemble_record, verified_suspension


class DatedTradingStateTests(unittest.TestCase):
    def state(self):
        return {"code": "600825", "status": "issuer_announced_suspension", "start_date": "2026-10-13",
                "verified_market_dates": ["2026-10-14"], "source_kind": "issuer_announcement_copy",
                "source_url": "https://example.org/issuer-announcement.pdf", "verified_at": "2026-10-15T10:00:00+08:00"}

    def test_dated_evidence_expires_instead_of_marking_future_sessions(self):
        self.assertTrue(verified_suspension(self.state(), "600825", "2026-10-14"))
        self.assertFalse(verified_suspension(self.state(), "600825", "2026-10-15"))

    def test_code_and_primary_document_are_required(self):
        self.assertFalse(verified_suspension(self.state(), "600826", "2026-10-14"))
        state = self.state(); state.pop("source_url")
        self.assertFalse(verified_suspension(state, "600825", "2026-10-14"))

    def test_issuer_document_resolves_halt_without_inventing_a_bar(self):
        stock = {"code": "600825", "name": "sample", "exchange": "SH", "listing_date": "1994-02-04"}
        row = assemble_record(stock, {"bars": [], "fetch_status": "failed"}, "2026-10-14", {}, [], trading_state=self.state())
        self.assertEqual(row["status"], "excluded")
        self.assertEqual(row["reasons"], ["issuer_announced_suspension"])
        self.assertNotIn("indicators", row)

    def test_trade_data_conflict_is_not_hidden_by_a_manual_state(self):
        stock = {"code": "600825", "name": "sample", "exchange": "SH", "listing_date": "1994-02-04"}
        row = assemble_record(stock, {"bars": [{"day": "2026-10-14", "volume": 1000}]}, "2026-10-14", {}, [], trading_state=self.state())
        self.assertEqual(row["status"], "unresolved")
        self.assertIn("conflicts", row["reasons"][0])


if __name__ == "__main__":
    unittest.main()
