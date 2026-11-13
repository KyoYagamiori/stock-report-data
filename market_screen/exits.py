"""Explicit, stateful exit plans. Reference plans never imply a user's actual trade."""
from __future__ import annotations

import math
from datetime import date

VERSION = "risk_exit_20261113_v1"
POLICY = {"initial_stop_buffer_atr": .25, "maximum_initial_risk_pct": 8.,
          "protect_after_r": 1.5, "partial_at_r": 2., "partial_fraction": 1/3,
          "trailing_atr": 2., "time_review_sessions": 3, "minimum_progress_r": .5,
          "time_stop_action": "review",
          "early_pivot_failure_sessions": 3, "pivot_failure_buffer_atr": .25,
          "round_trip_cost_bps_assumption": 20., "legacy_midline_rule_enabled": False}


def create_plan(entry_price, structure_low, atr, *, pivot=None, entry_date=None, policy=None):
    c = {**POLICY, **(policy or {})}
    if entry_date is not None:
        date.fromisoformat(entry_date)
    for value in (entry_price, structure_low, atr):
        if isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0:
            raise ValueError("exit_plan_requires_positive_finite_prices_and_atr")
    stop = math.floor((structure_low - c["initial_stop_buffer_atr"] * atr + 1e-9) * 100) / 100
    if stop <= 0 or stop >= entry_price:
        raise ValueError("initial_structural_stop_must_be_below_entry")
    risk = entry_price - stop
    risk_pct = risk / entry_price * 100
    return {"version": VERSION, "entry_price": entry_price, "entry_date": entry_date,
            "price_basis": "same_basis_required_for_entry_structure_and_observation",
            "entry_basis": "user_or_simulation_supplied" if entry_date else "reference_only_not_a_recorded_fill",
            "initial_stop": stop, "initial_risk_per_share": risk, "initial_risk_pct": risk_pct,
            "entry_risk_acceptable": risk_pct <= c["maximum_initial_risk_pct"],
            "entry_decision": "risk_budget_review_required" if risk_pct <= c["maximum_initial_risk_pct"] else "skip_entry_structure_too_wide",
            "pivot": pivot, "initial_atr": atr,
            "profit_protection_arms_at": round(entry_price + c["protect_after_r"] * risk, 4),
            "partial_profit_at": round(entry_price + c["partial_at_r"] * risk, 4),
            "partial_fraction_of_original": c["partial_fraction"],
            "time_review_sessions": c["time_review_sessions"], "policy": c,
            "execution_note": "T_plus_1_halts_limits_and_gaps_may_prevent_exit_at_reference_price",
            "parameter_status": "fixed_research_hypotheses_not_jlaw_private_rules_or_empirical_optimum"}


def initial_state(plan):
    return {"stop": plan["initial_stop"], "highest_close": plan["entry_price"],
            "partial_taken": False, "remaining_fraction": 1., "last_completed_date": None}


def assess(plan, state, bar, *, holding_sessions, atr=None, completed=True, basis_change=False):
    """Return an instruction; the caller separately records whether it could be filled."""
    state = dict(state)
    c, price = plan["policy"], bar["close"]
    date.fromisoformat(bar["day"])
    if not math.isfinite(float(price)) or price <= 0 or not isinstance(holding_sessions, int) or holding_sessions < 0:
        raise ValueError("invalid_exit_price_or_session_count")
    if atr is not None and (not math.isfinite(float(atr)) or atr <= 0):
        raise ValueError("invalid_exit_atr")
    answer = {"version": VERSION, "action": "hold", "reason": "no_exit_trigger", "trigger_price": None,
              "fraction_of_original": 0., "observation_date": bar["day"],
              "execution_status": "recommendation_not_a_recorded_fill", "state": state}
    if plan["entry_date"] is None:
        return {**answer, "action": "needs_entry_details", "reason": "reference_levels_are_not_personalized_sell_orders"}
    if basis_change:
        return {**answer, "action": "requires_price_basis_review", "reason": "do_not_compare_unreconciled_prices"}
    if bar["day"] < plan["entry_date"] or holding_sessions < 0:
        raise ValueError("exit_observation_before_entry")
    if completed and state.get("last_completed_date") and bar["day"] <= state["last_completed_date"]:
        raise ValueError("exit_completed_observation_cannot_be_repeated_or_backdated")
    if state["remaining_fraction"] <= 0:
        return {**answer, "action": "already_closed", "reason": "no_remaining_position"}
    # The active stop was fixed before this bar; today's high cannot retroactively raise it.
    if price <= state["stop"]:
        reason = "initial_structure_failed" if state["stop"] <= plan["initial_stop"] else "profit_protection_triggered"
        answer.update(action="exit_all", reason=reason, trigger_price=state["stop"],
                      fraction_of_original=state["remaining_fraction"])
    elif completed and plan.get("pivot") and holding_sessions <= c["early_pivot_failure_sessions"] and price < plan["pivot"] - c["pivot_failure_buffer_atr"] * plan["initial_atr"]:
        answer.update(action="exit_all", reason="early_breakout_failed", trigger_price=plan["pivot"],
                      fraction_of_original=state["remaining_fraction"])
    elif completed:
        peak = max(state["highest_close"], price)
        progress = (peak - plan["entry_price"]) / plan["initial_risk_per_share"]
        if holding_sessions >= c["time_review_sessions"] and progress < c["minimum_progress_r"]:
            answer.update(action=c["time_stop_action"], reason="time_stop_insufficient_progress",
                          fraction_of_original=state["remaining_fraction"] if c["time_stop_action"]=="exit_all" else 0.)
        elif not state["partial_taken"] and price >= plan["partial_profit_at"]:
            answer.update(action="reduce", reason="partial_profit_at_2r", trigger_price=plan["partial_profit_at"],
                          fraction_of_original=min(c["partial_fraction"], state["remaining_fraction"]))
        # This higher stop becomes active only after this completed close.
        state["highest_close"] = peak
        if progress >= c["protect_after_r"]:
            atr = atr if atr is not None else plan["initial_atr"]
            breakeven = plan["entry_price"] * (1 + c["round_trip_cost_bps_assumption"] / 10000)
            state["stop"] = max(state["stop"], breakeven, peak - c["trailing_atr"] * atr)
    if completed:
        state["last_completed_date"] = bar["day"]
    if answer["action"] in {"exit_all", "reduce"}:
        answer["execution_status"] = "T_plus_1_blocked_until_next_session" if bar["day"] == plan["entry_date"] else "check_actual_liquidity_and_limit_evidence"
    return answer


def record_fill(state, fraction):
    """A recommendation alone must never mark a partial exit as executed."""
    if not 0 < fraction <= state["remaining_fraction"] + 1e-9:
        raise ValueError("exit_fill_fraction_invalid")
    out = dict(state)
    out["remaining_fraction"] = max(0., out["remaining_fraction"] - fraction)
    if out["remaining_fraction"] > 0:
        out["partial_taken"] = True
    return out


def candidate_plan(row):
    """Show explicit levels before entry without fabricating a holding or cost basis."""
    f, v = row.get("features", {}), row.get("vcp_shadow", {})
    atr = f.get("atr20")
    low = v.get("invalidation_below") if v.get("matched") else row.get("conditional_prices", {}).get("structural_reference_low")
    pivot = v.get("pivot") if v.get("matched") else None
    reference = round(pivot + .01, 2) if pivot else row.get("price")
    if not atr or not low or not reference:
        return {"version": VERSION, "status": "unavailable", "reason": "structural_reference_missing"}
    try:
        plan = create_plan(reference, low, atr, pivot=pivot)
    except ValueError as exc:
        return {"version": VERSION, "status": "unavailable", "reason": str(exc)}
    return {"status": "conditional_reference_plan", **plan,
            "current_holding_action": "requires_actual_entry_date_price_and_remaining_position",
            "trailing_stop_rule": "after_1.5R_raise_only_max_previous_stop_cost_breakeven_highest_completed_close_minus_2ATR",
            "time_stop_rule": "review_after_3_sessions_if_best_completed_close_advance_below_0.5R; no_forced_time_exit_without_validation",
            "legacy_midline_two_day_rule": "disabled_not_a_required_exit"}
