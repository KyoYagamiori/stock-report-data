from __future__ import annotations

import unittest

from ma5_system.state_machine import ActionContext, TradeState, decide_action, drawdown_alert, transition


def context(**overrides):
    values = dict(price=10.2, ma5=10.0, ma10=9.5, hard_invalidation=9.4, box_top=11.0, market_cap_pct=100, target_2r=10.8)
    values.update(overrides)
    return ActionContext(**values)


class MA5StateMachineTests(unittest.TestCase):
    def test_cash_cannot_jump_to_full(self) -> None:
        with self.assertRaises(ValueError):
            transition(TradeState.CASH, TradeState.FULL_100)

    def test_three_levels_require_new_evidence(self) -> None:
        candidate = decide_action(TradeState.CASH, context(), a_plus=True)
        self.assertEqual(TradeState.CANDIDATE, candidate.next_state)
        probe = decide_action(TradeState.CANDIDATE, context(confirmation_met=True), a_plus=True)
        self.assertEqual(TradeState.PROBE_40, probe.next_state)
        hold = decide_action(TradeState.PROBE_40, context())
        self.assertEqual(TradeState.PROBE_40, hold.next_state)
        confirm = decide_action(TradeState.PROBE_40, context(add_confirmation_met=True))
        self.assertEqual(TradeState.CONFIRM_70, confirm.next_state)

    def test_event_window_caps_position_at_70(self) -> None:
        decision = decide_action(TradeState.CONFIRM_70, context(event_risk=True, breakout_confirmed=True))
        self.assertEqual(TradeState.CONFIRM_70, decision.next_state)
        self.assertEqual(70, decision.target_level_pct)

    def test_hard_invalidation_exits_without_averaging(self) -> None:
        decision = decide_action(TradeState.PROBE_40, context(price=9.3))
        self.assertEqual(TradeState.EXIT, decision.next_state)

    def test_ma5_intraday_break_warns_without_automatic_reduction(self) -> None:
        decision = decide_action(TradeState.CONFIRM_70, context(price=9.8, current_level_pct=70))
        self.assertEqual(TradeState.MA5_WARNING, decision.next_state)
        self.assertEqual(70, decision.target_level_pct)

    def test_same_day_second_upgrade_is_blocked(self) -> None:
        decision = decide_action(TradeState.PROBE_40, context(add_confirmation_met=True, same_day_prior_upgrade=True))
        self.assertEqual(TradeState.PROBE_40, decision.next_state)

    def test_weak_market_uses_cash_instead_of_nonexistent_30_level(self) -> None:
        decision = decide_action(TradeState.PROBE_40, context(market_cap_pct=30))
        self.assertEqual(TradeState.EXIT, decision.next_state)
        self.assertEqual(0, decision.target_level_pct)

    def test_event_cap_reduces_full_state_to_70(self) -> None:
        decision = decide_action(TradeState.FULL_100, context(event_risk=True))
        self.assertEqual(TradeState.PROFIT_70, decision.next_state)
        self.assertEqual(70, decision.target_level_pct)

    def test_fresh_breakout_can_unlock_full_before_profit_zone(self) -> None:
        decision = decide_action(TradeState.CONFIRM_70, context(price=10.6, breakout_confirmed=True))
        self.assertEqual(TradeState.FULL_100, decision.next_state)

    def test_two_r_reduces_full_position(self) -> None:
        decision = decide_action(TradeState.FULL_100, context(price=10.85))
        self.assertEqual(TradeState.PROFIT_70, decision.next_state)

    def test_drawdown_alert_does_not_treat_gain_as_drawdown(self) -> None:
        self.assertIsNone(drawdown_alert(8.0))
        self.assertEqual("red_8", drawdown_alert(-8.0)["level"])
        self.assertEqual("red_12", drawdown_alert(-12.0)["level"])


if __name__ == "__main__":
    unittest.main()
