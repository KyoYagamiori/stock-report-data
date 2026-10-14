import unittest
from research_pipeline.daily import calculate


class DailyEvidenceTests(unittest.TestCase):
    def rows(self, n=40):
        from datetime import date,timedelta
        start=date(2026,8,1)
        return [{'day':(start+timedelta(days=i)).isoformat(),'open':str(10+i),
                 'close':str(10+i),'high':str(11+i),'low':str(9+i),'volume':'1000'}
                for i in range(n)]

    def test_future_session_removed(self):
        record,rows=calculate(self.rows(),'2026-08-20')
        self.assertEqual(len(rows),20)
        self.assertEqual(record['bar_date'],'2026-08-20')
        self.assertEqual(record['boll']['mid'],19.5)
        self.assertAlmostEqual(record['boll']['upper'],19.5+2*(399/12)**0.5)

    def test_zero_volume_not_a_division(self):
        rows=self.rows();rows[-2]['volume']='0'
        record,_=calculate(rows,'2026-10-13')
        self.assertIsNone(record['volume_vs_previous_ratio'])

    def test_duplicate_date_rejected(self):
        rows=self.rows();rows.append(dict(rows[-1]))
        with self.assertRaises(ValueError):calculate(rows,'2026-10-13')

    def test_invalid_price_bounds_rejected(self):
        rows=self.rows();rows[-1]['close']='1000'
        with self.assertRaises(ValueError):calculate(rows,'2026-10-13')

    def test_short_history_cannot_be_called_complete(self):
        record,_=calculate(self.rows(10),'2026-10-13')
        self.assertFalse(record['technical_complete'])
        self.assertFalse(record['history_current'])


if __name__=='__main__':unittest.main()
