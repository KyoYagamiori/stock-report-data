from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TradeState(str, Enum):
    CASH = "cash"
    CANDIDATE = "candidate"
    PROBE_40 = "probe_40"
    CONFIRM_70 = "confirm_70"
    FULL_100 = "full_100"
    PROFIT_70 = "profit_70"
    PROFIT_40 = "profit_40"
    MA5_WARNING = "ma5_warning"
    EXIT = "exit"
    REVIEW = "review"


ALLOWED_TRANSITIONS = {
    TradeState.CASH: {TradeState.CANDIDATE},
    TradeState.CANDIDATE: {TradeState.PROBE_40, TradeState.CASH},
    TradeState.PROBE_40: {TradeState.CONFIRM_70, TradeState.MA5_WARNING, TradeState.EXIT},
    TradeState.CONFIRM_70: {TradeState.FULL_100, TradeState.PROFIT_40, TradeState.MA5_WARNING, TradeState.EXIT},
    TradeState.FULL_100: {TradeState.PROFIT_70, TradeState.PROFIT_40, TradeState.MA5_WARNING, TradeState.EXIT},
    TradeState.PROFIT_70: {TradeState.PROFIT_40, TradeState.MA5_WARNING, TradeState.EXIT},
    TradeState.PROFIT_40: {TradeState.MA5_WARNING, TradeState.EXIT},
    TradeState.MA5_WARNING: {TradeState.PROBE_40, TradeState.CONFIRM_70, TradeState.FULL_100, TradeState.PROFIT_70, TradeState.PROFIT_40, TradeState.EXIT},
    TradeState.EXIT: {TradeState.REVIEW},
    TradeState.REVIEW: {TradeState.CASH},
}

LEVEL_BY_STATE = {
    TradeState.CASH: 0,
    TradeState.CANDIDATE: 0,
    TradeState.PROBE_40: 40,
    TradeState.CONFIRM_70: 70,
    TradeState.FULL_100: 100,
    TradeState.PROFIT_70: 70,
    TradeState.PROFIT_40: 40,
    TradeState.MA5_WARNING: 40,
    TradeState.EXIT: 0,
    TradeState.REVIEW: 0,
}


@dataclass(frozen=True)
class ActionContext:
    price: float
    ma5: float
    ma10: float
    hard_invalidation: float
    box_top: float | None
    market_cap_pct: int
    target_2r: float | None = None
    event_risk: bool = False
    direction_retreating: bool = False
    volume_weak: bool = False
    after_1445: bool = True
    confirmation_met: bool = False
    add_confirmation_met: bool = False
    breakout_confirmed: bool = False
    current_level_pct: int = 40
    same_day_prior_upgrade: bool = False


@dataclass(frozen=True)
class ActionDecision:
    current_state: TradeState
    next_state: TradeState
    target_level_pct: int
    reason: str
    allowed: bool


def transition(current: TradeState, target: TradeState) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"Illegal MA5 state transition: {current.value} -> {target.value}")


def decide_action(current: TradeState, context: ActionContext, a_plus: bool = False) -> ActionDecision:
    if current == TradeState.CASH:
        if not a_plus:
            return ActionDecision(current, current, 0, "No A+ candidate; remain in cash", True)
        return _decision(current, TradeState.CANDIDATE, "Unique A+ candidate entered observation")
    if current == TradeState.CANDIDATE:
        if not context.confirmation_met or context.market_cap_pct < 40:
            return ActionDecision(current, current, 0, "Wait for MA5 reclaim and confirmation", True)
        return _decision(current, TradeState.PROBE_40, "New confirmation unlocked the 40% probe level")
    if context.price <= context.hard_invalidation or context.price < context.ma10:
        return _decision(current, TradeState.EXIT, "Hard invalidation or MA10 break")
    cap = min(context.market_cap_pct, 70 if context.event_risk else 100)
    if cap < 40:
        return _decision(current, TradeState.EXIT, "Weak-market 30% cap is below the minimum 40% tranche; move to cash")
    if current == TradeState.FULL_100 and cap <= 70:
        return _decision(current, TradeState.PROFIT_70, "Market or event cap fell to 70%; reduce target risk")
    profit_reached = bool(
        (context.target_2r is not None and context.price >= context.target_2r)
        or (context.box_top is not None and context.price >= context.box_top)
    )
    if profit_reached:
        if current == TradeState.FULL_100:
            return _decision(current, TradeState.PROFIT_70, "Box top or 2R reached; protect part of the profit")
        if current in {TradeState.CONFIRM_70, TradeState.PROFIT_70}:
            return _decision(current, TradeState.PROFIT_40, "Box top/2R zone reached; reduce risk")
    if context.price < context.ma5:
        if context.after_1445 and (context.volume_weak or context.direction_retreating):
            if current in {TradeState.FULL_100, TradeState.CONFIRM_70, TradeState.PROFIT_70}:
                return _decision(current, TradeState.PROFIT_40, "MA5 not reclaimed by 14:45 with weakening evidence")
        if current != TradeState.MA5_WARNING:
            transition(current, TradeState.MA5_WARNING)
            return ActionDecision(current, TradeState.MA5_WARNING, context.current_level_pct, "Intraday MA5 break; warning only until 14:45 evidence confirms weakness", True)
        return ActionDecision(current, current, context.current_level_pct, "MA5 warning remains active", True)
    if current == TradeState.MA5_WARNING and context.price >= context.ma5:
        recovered = TradeState.FULL_100 if context.current_level_pct >= 100 else TradeState.CONFIRM_70 if context.current_level_pct >= 70 else TradeState.PROBE_40
        return _decision(current, recovered, "MA5 reclaimed; restore the prior risk state without adding")
    if context.same_day_prior_upgrade and current in {TradeState.PROBE_40, TradeState.CONFIRM_70}:
        return ActionDecision(current, current, min(LEVEL_BY_STATE[current], cap), "Same-day consecutive upgrades are blocked", True)
    if current == TradeState.CONFIRM_70 and context.breakout_confirmed and cap >= 100 and not profit_reached:
        return _decision(current, TradeState.FULL_100, "Fresh key-pressure breakout unlocked 100% before the profit zone")
    if current == TradeState.PROBE_40 and context.add_confirmation_met and cap >= 70:
        return _decision(current, TradeState.CONFIRM_70, "Fresh MA5 support evidence unlocked 70%")
    return ActionDecision(current, current, min(LEVEL_BY_STATE[current], cap), "Hold current risk level", True)


def drawdown_alert(current_drawdown_pct: float) -> dict[str, Any] | None:
    magnitude = max(0.0, -current_drawdown_pct)
    if magnitude >= 12:
        return {"level": "red_12", "message": "Drawdown from stage high reached 12%; audit consecutive failures."}
    if magnitude >= 8:
        return {"level": "red_8", "message": "Drawdown from stage high reached 8%; reduce discretion and audit execution."}
    return None


def _decision(current: TradeState, target: TradeState, reason: str) -> ActionDecision:
    transition(current, target)
    return ActionDecision(current, target, LEVEL_BY_STATE[target], reason, True)
