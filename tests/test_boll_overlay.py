from datetime import datetime
import unittest
from zoneinfo import ZoneInfo

from market_screen.runner import overlay_record


class OverlayCoverageTests(unittest.TestCase):
    def quote(self):
        return {"code": "000001", "name": "sample", "open": 10, "prev_close": 10,
                "close": 10.1, "high": 10.2, "low": 9.9, "volume": 1000, "amount": 10100,
                "date": "2026-10-15", "time": "11:30:00", "status": "valid",
                "retrieved_at": "2026-10-15T11:32:00+08:00"}

    def test_excluded_stock_quote_still_counts_as_quote_coverage(self):
        record = {"code": "000001", "name": "sample", "market_date": "2026-10-14", "status": "excluded"}
        row = overlay_record(record, self.quote(), "2026-10-15", "noon",
                             datetime(2026, 10, 15, 11, 32, tzinfo=ZoneInfo("Asia/Shanghai")), "2026-10-14")
        self.assertEqual(row["quote_status"], "valid")
        self.assertEqual(row["status"], "stale_baseline")
        self.assertNotIn("corporate_action_basis_changed", row)

    def test_afternoon_price_cannot_count_as_noon_quote(self):
        record = {"code": "000001", "name": "sample", "market_date": "2026-10-14"}
        quote = self.quote()
        quote["time"] = "13:01:00"
        quote["retrieved_at"] = "2026-10-15T13:02:00+08:00"
        row = overlay_record(record, quote, "2026-10-15", "noon",
                             datetime(2026, 10, 15, 13, 2, tzinfo=ZoneInfo("Asia/Shanghai")), "2026-10-14")
        self.assertEqual(row["quote_status"], "unavailable")
        self.assertIn("not_noon", row["errors"])


if __name__ == "__main__":
    unittest.main()
