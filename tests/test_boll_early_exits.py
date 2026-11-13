from datetime import date, timedelta
import unittest

from market_screen.exits import create_plan, initial_state, assess, record_fill, candidate_plan


class ExitPlanTests(unittest.TestCase):
    def plan(self, **kw):
        return create_plan(100,96,2,entry_date="2020-01-02",**kw)

    def test_initial_risk_and_profit_levels_are_explicit_and_legacy_rule_disabled(self):
        p=self.plan()
        self.assertEqual(95.5,p["initial_stop"])
        self.assertEqual(109,p["partial_profit_at"])
        self.assertEqual(106.75,p["profit_protection_arms_at"])
        self.assertFalse(p["policy"]["legacy_midline_rule_enabled"])

    def test_entry_day_sell_instruction_is_not_claimed_executable(self):
        p=self.plan()
        decision=assess(p,initial_state(p),{"day":"2020-01-02","close":94},holding_sessions=0)
        self.assertEqual("exit_all",decision["action"])
        self.assertEqual("T_plus_1_blocked_until_next_session",decision["execution_status"])
        self.assertEqual(1,decision["state"]["remaining_fraction"])

    def test_profit_protection_can_only_raise_and_uses_completed_closes(self):
        p=self.plan()
        first=assess(p,initial_state(p),{"day":"2020-01-03","close":108},holding_sessions=1,atr=2)
        floor=first["state"]["stop"]
        self.assertGreaterEqual(floor,100.2)
        second=assess(p,first["state"],{"day":"2020-01-06","close":107},holding_sessions=2,atr=20)
        self.assertGreaterEqual(second["state"]["stop"],floor)
        intraday=assess(p,second["state"],{"day":"2020-01-07","close":115},holding_sessions=3,completed=False)
        self.assertEqual(second["state"]["stop"],intraday["state"]["stop"])

    def test_partial_recommendation_is_not_a_fill(self):
        p=self.plan()
        out=assess(p,initial_state(p),{"day":"2020-01-03","close":110},holding_sessions=1)
        self.assertEqual("reduce",out["action"])
        self.assertFalse(out["state"]["partial_taken"])
        self.assertAlmostEqual(2/3,record_fill(out["state"],1/3)["remaining_fraction"])

    def test_failed_breakout_exits_without_waiting_for_midline(self):
        p=create_plan(105,101,1,pivot=104,entry_date="2020-01-02")
        out=assess(p,initial_state(p),{"day":"2020-01-03","close":103.5},holding_sessions=1)
        self.assertEqual("early_breakout_failed",out["reason"])

    def test_midline_alone_does_not_force_exit_and_time_stop_is_separate(self):
        p=self.plan()
        state=initial_state(p)
        state["highest_close"]=103
        out=assess(p,state,{"day":"2020-01-08","close":98,"mid":105},holding_sessions=4)
        self.assertEqual("hold",out["action"])
        out=assess(p,initial_state(p),{"day":"2020-01-08","close":100},holding_sessions=3)
        self.assertEqual("time_stop_insufficient_progress",out["reason"])
        self.assertEqual("review",out["action"])

    def test_reference_only_plan_cannot_invent_personal_holding_or_sell_decision(self):
        p=create_plan(100,96,2)
        out=assess(p,initial_state(p),{"day":"2020-01-03","close":90},holding_sessions=1)
        self.assertEqual("needs_entry_details",out["action"])
        self.assertFalse(create_plan(100,80,2)["entry_risk_acceptable"])
        self.assertEqual("skip_entry_structure_too_wide",create_plan(100,80,2)["entry_decision"])

    def test_future_repeat_nonfinite_and_basis_conflicts_are_rejected(self):
        p=self.plan()
        first=assess(p,initial_state(p),{"day":"2020-01-03","close":101},holding_sessions=1)
        with self.assertRaises(ValueError): assess(p,first["state"],{"day":"2020-01-03","close":101},holding_sessions=1)
        with self.assertRaises(ValueError): assess(p,initial_state(p),{"day":"2020-01-01","close":101},holding_sessions=0)
        with self.assertRaises(ValueError): assess(p,initial_state(p),{"day":"2020-01-03","close":float("nan")},holding_sessions=1)
        out=assess(p,initial_state(p),{"day":"2020-01-03","close":90},holding_sessions=1,basis_change=True)
        self.assertEqual("requires_price_basis_review",out["action"])

    def test_live_candidate_has_exit_levels_without_fabricating_a_fill(self):
        from tests.test_boll_early import record,quote,DATES,NOW,CONFIG
        from market_screen.early import build
        data=build([record()],DATES,NOW,CONFIG,{"600000":quote()})
        plan=data["shortlist"][0]["exit_plan"]
        self.assertEqual("conditional_reference_plan",plan["status"])
        self.assertIsNone(plan["entry_date"])
        self.assertLess(plan["initial_stop"],plan["entry_price"])


if __name__=="__main__": unittest.main()
