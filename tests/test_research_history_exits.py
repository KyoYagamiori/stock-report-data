from copy import deepcopy
from datetime import date,timedelta
import unittest

from research_system.history_exits import replay,summarize


def fixture():
    raw=[]
    for i in range(70):
        price={42:104.,43:104.,44:102.,45:101.}.get(i,100.)
        day=(date(2020,1,1)+timedelta(days=i)).isoformat()
        raw.append({"day":day,"code":"sh.600000","open":105. if i==43 else price,
                    "high":max(price,105. if i==43 else price)+.2,"low":price-.2,
                    "close":price,"volume":1000000,"tradestatus":"1","isST":"0",
                    "preclose":raw[-1]["close"] if raw else price})
    days=[r["day"] for r in raw]
    benchmark={d:{"open":100.,"close":100.} for d in days}
    row={"date":days[40],"code":"600000","execution_state":"filled_daily_proxy",
         "round_trip_cost_bps_assumption":20,"target_t3_net_excess_pct":1.8}
    return row,raw,days,benchmark


class ExitReplayTests(unittest.TestCase):
    def test_partial_and_defensive_exits_use_later_open_and_keep_t_plus_one(self):
        row,raw,days,index=fixture()
        result=replay(row,raw,raw,days,index,"2030-01-01")
        self.assertEqual("completed_daily_proxy",result["state"])
        self.assertEqual(2,len(result["fills"]))
        self.assertAlmostEqual(1,sum(f["fraction"] for f in result["fills"]))
        self.assertTrue(all(f["date"]>days[41] for f in result["fills"]))
        self.assertAlmostEqual(1/3,result["fills"][0]["fraction"])

    def test_missing_path_is_censored_and_not_assumed_halted_or_zero_return(self):
        row,raw,days,index=fixture()
        raw=[r for r in raw if r["day"]!=days[42]]
        result=replay(row,raw,raw,days,index,"2030-01-01")
        self.assertEqual("censored_missing_path",result["state"])
        self.assertNotIn("net_excess_pct",result)

    def test_entry_day_stop_touch_never_sells_at_same_day_stop(self):
        row,raw,days,index=fixture()
        raw[41]["low"]=95.
        result=replay(row,raw,raw,days,index,"2030-01-01")
        self.assertEqual(days[42],result["fills"][0]["date"])
        self.assertEqual(raw[42]["open"],result["fills"][0]["price"])

    def test_crossing_previous_review_boundary_is_excluded_before_return_calculation(self):
        row,raw,days,index=fixture()
        result=replay(row,raw,raw,days,index,days[45])
        self.assertEqual("immature_or_cross_review_boundary",result["state"])

    def test_censored_exits_and_cash_are_preserved_in_summary_denominators(self):
        records=[{"state":"censored_unresolved_exit","date":"2020-01-01","code":"600000"},
                 {"state":"unfilled","date":"2020-01-02","code":"600001","net_excess_pct":0.,"fixed3_pct":0.,"filled":False}]
        result=summarize(records)
        self.assertEqual(1,result["state_counts"]["censored_unresolved_exit"])
        self.assertEqual(0,result["round_trip_cost_bps_sensitivity"]["40"])
        self.assertFalse(result["production_activation"])


if __name__=="__main__": unittest.main()
