from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ma5_system.config import load_strategy_config
from ma5_system.data import board_for, limit_pct_for, normalize_code, safe_number
from ma5_system.scoring import apply_direction_context, build_technical_record, market_score, rank_directions, score_stock


@dataclass
class Position:
    code: str
    name: str
    shares: float
    avg_cost: float
    level: int
    entry_date: str
    entry_equity: float
    hard_invalidation: float
    box_top: float | None
    target_2r: float | None
    initial_risk: float
    max_price: float
    min_price: float
    last_price: float
    entry_regime: str
    event_risk: bool
    bars_held: int = 0


def run_backtest(frame: pd.DataFrame, config: dict[str, Any] | None = None, initial_cash: float = 1_000_000.0) -> dict[str, Any]:
    config = config or load_strategy_config()
    data = _normalize_panel(frame)
    dates = sorted(data["date"].unique())
    cash = initial_cash
    position: Position | None = None
    pending_level: int | None = None
    pending_card: dict[str, Any] | None = None
    pending_reason = ""
    equity_curve: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    fee_config = config["costs"]
    previous_directions: list[str] = []
    previous_turnover: float | None = None
    synthetic_market_level = 100.0
    synthetic_market_history: list[float] = []

    for date_index, current_date in enumerate(dates):
        today = data[data["date"] == current_date].copy()
        by_code = {row.code: row for row in today.itertuples()}
        if pending_level is not None:
            target_row = by_code.get((pending_card or {}).get("code") if pending_card else position.code if position else "")
            if target_row is not None:
                cash, position, executed_trade = _execute_target(
                    cash, position, target_row, pending_level, pending_card, pending_reason, current_date, fee_config
                )
                if executed_trade:
                    trades.append(executed_trade)
            pending_level = None
            pending_card = None
            pending_reason = ""

        history_before = data[data["date"] < current_date]
        directions = rank_directions(today.rename(columns={"close": "latest"}), previous_directions)
        direction_by_name = {item["name"]: item for item in directions}
        median_pct = float(pd.to_numeric(today["pct_change"], errors="coerce").median())
        if pd.isna(median_pct):
            median_pct = 0.0
        synthetic_market_level *= 1 + median_pct / 100
        synthetic_market_history.append(synthetic_market_level)
        proxy_points = _proxy_index_points(synthetic_market_history, median_pct)
        current_turnover = float(pd.to_numeric(today["amount"], errors="coerce").sum())
        turnover_ratio = current_turnover / previous_turnover if previous_turnover and previous_turnover > 0 else None
        day_environment = market_score(
            today,
            [{"trend_points": proxy_points} for _ in range(3)],
            directions,
            turnover_ratio,
            config,
        )
        day_regime = day_environment["regime"]
        day_cap = int(day_environment["maximum_position_pct"])
        long_holiday_risk = bool(
            date_index + 1 < len(dates)
            and (pd.Timestamp(dates[date_index + 1]) - pd.Timestamp(current_date)).days > 3
        )
        cards: list[dict[str, Any]] = []
        for row in today.to_dict(orient="records"):
            limit_pct = limit_pct_for(str(row["code"]), str(row["name"]))
            one_price_limit = bool(
                safe_number(row.get("high")) is not None
                and safe_number(row.get("low")) is not None
                and abs(float(row["high"]) - float(row["low"])) < 1e-8
                and abs(float(row.get("pct_change") or 0.0)) >= limit_pct - 0.05
            )
            quote = {
                **row,
                "latest": row["close"],
                "pct_change": row.get("pct_change", 0.0),
                "quote_time": f"{current_date}T15:00:00+08:00",
                "valid_quote": bool(safe_number(row.get("close")) and (safe_number(row.get("volume")) or 0) > 0),
                "suspended": (safe_number(row.get("volume")) or 0) <= 0,
                "one_price_limit": one_price_limit,
            }
            history = history_before[history_before["code"] == row["code"]]
            technical = build_technical_record(quote, history, current_date, "close", config)
            technical = apply_direction_context(technical, direction_by_name.get(row["industry"]))
            technical["data_grade"] = "A"
            technical["long_holiday_risk"] = long_holiday_risk
            technical["event_risk"] = bool(technical.get("event_risk")) or long_holiday_risk
            technical["major_data_gap"] = not bool(technical.get("technical_complete"))
            technical["market_regime"] = day_regime
            technical["market_cap_pct"] = day_cap
            cards.append(score_stock(technical, technical.get("direction_rank"), config).card)
        candidates = sorted((card for card in cards if card.get("a_plus")), key=lambda item: item["score"], reverse=True)
        if candidates:
            leader = candidates[0]
            signals.append({"date": current_date, "code": leader["code"], "score": leader["score"], "close": leader["latest"], "market_regime": day_regime})

        if position:
            card = next((item for item in cards if item["code"] == position.code), None)
            position_row = by_code.get(position.code)
            if position_row is not None:
                position.bars_held += 1
                close = float(position_row.close)
                position.last_price = close
                position.max_price = max(position.max_price, float(position_row.high))
                position.min_price = min(position.min_price, float(position_row.low))
                current_event_risk = bool(card.get("event_risk")) if card else position.event_risk
                position.event_risk = current_event_risk
                profit_reached = bool(
                    (position.target_2r is not None and close >= position.target_2r)
                    or (position.box_top is not None and close >= position.box_top)
                )
                volume_weak = bool(
                    card
                    and (safe_number(card.get("pct_change")) or 0) < 0
                    and (safe_number(card.get("amount_ratio_20")) or 0) >= 1.0
                )
                direction_retreating = bool(card.get("direction_retreating")) if card else True
                if card and (close <= position.hard_invalidation or close < (card.get("ma10") or 0)):
                    pending_level, pending_reason = 0, "hard_invalidation"
                elif day_cap < 40:
                    pending_level, pending_reason = 0, "weak_market_cap"
                elif position.level == 100 and (day_cap <= 70 or current_event_risk):
                    pending_level, pending_reason = 70, "market_or_event_cap"
                elif profit_reached and position.level == 100:
                    pending_level, pending_reason = 70, "two_r_or_box_profit"
                elif profit_reached and position.level == 70:
                    pending_level, pending_reason = 40, "two_r_or_box_profit"
                elif card and close < (card.get("ma5") or 0) and position.level > 40 and (volume_weak or direction_retreating):
                    pending_level, pending_reason = 40, "ma5_warning_confirmed"
                elif card and position.level == 40 and day_cap >= 70 and card.get("ma5_rising") and close >= card.get("ma5", close):
                    pending_level, pending_reason = 70, "ma5_confirmation"
                elif (
                    card
                    and position.level == 70
                    and day_cap >= 100
                    and not current_event_risk
                    and close >= (safe_number(card.get("confirmation_price")) or float("inf"))
                    and not profit_reached
                ):
                    pending_level, pending_reason = 100, "key_pressure_breakout"
        elif candidates and day_cap >= 40:
            pending_level, pending_card, pending_reason = 40, candidates[0], "a_plus_entry"

        close_equity = cash + (position.shares * position.last_price if position else 0.0)
        equity_curve.append({"date": current_date, "equity": close_equity})
        previous_directions = [item["name"] for item in directions[:3]]
        previous_turnover = current_turnover

    metrics = _metrics(equity_curve, trades, initial_cash)
    forward = _forward_returns(data, signals)
    validation = _backtest_validation(dates, equity_curve, trades)
    return {
        "strategy_id": config["strategy_id"],
        "market_score_method": "equal_weight_all_a_proxy_for_index_trend; live deployment uses three official indices",
        "metrics": metrics,
        "future_returns": forward,
        "validation": validation,
        "trades": trades,
        "equity_curve": equity_curve,
    }


def _execute_target(
    cash: float,
    position: Position | None,
    row: Any,
    target_level: int,
    card: dict[str, Any] | None,
    reason: str,
    trade_date: str,
    costs: dict[str, Any],
) -> tuple[float, Position | None, dict[str, Any] | None]:
    open_price = safe_number(row.open)
    previous_close = safe_number(getattr(row, "prev_close", None))
    if open_price is None or open_price <= 0 or safe_number(row.volume) in (None, 0):
        return cash, position, None
    limit = limit_pct_for(str(row.code), str(row.name)) / 100
    if target_level > (position.level if position else 0) and previous_close and open_price >= previous_close * (1 + limit - 0.001):
        return cash, position, None
    if target_level < (position.level if position else 0) and previous_close and open_price <= previous_close * (1 - limit + 0.001):
        return cash, position, None
    slippage = costs["slippage_bps"] / 10_000
    equity = cash + (position.shares * open_price if position else 0.0)
    desired_value = equity * target_level / 100
    current_value = position.shares * open_price if position else 0.0
    delta = desired_value - current_value
    if abs(delta) < 1:
        return cash, position, None
    if delta > 0:
        price = open_price * (1 + slippage)
        budget = min(delta, cash)
        estimated_fee_rate = costs["commission_bps"] / 10_000
        shares = math.floor((budget / (price * (1 + estimated_fee_rate))) / 100) * 100
        if shares <= 0:
            return cash, position, None
        gross = shares * price
        commission = max(costs["minimum_commission"], gross * costs["commission_bps"] / 10_000)
        while shares > 0 and gross + commission > cash:
            shares -= 100
            gross = shares * price
            commission = max(costs["minimum_commission"], gross * costs["commission_bps"] / 10_000)
        if shares <= 0:
            return cash, position, None
        cash -= gross + commission
        if position:
            total_cost = position.shares * position.avg_cost + shares * price + commission
            position.shares += shares
            position.avg_cost = total_cost / position.shares
            position.level = target_level
            position.last_price = price
        else:
            assert card is not None
            position = Position(
                code=card["code"], name=card["name"], shares=shares, avg_cost=(shares * price + commission) / shares,
                level=target_level, entry_date=trade_date, entry_equity=equity,
                hard_invalidation=float(card["hard_invalidation"]), box_top=safe_number(card.get("box_top")),
                target_2r=safe_number(card.get("target_2r")),
                initial_risk=float(card["entry_reference"] - card["hard_invalidation"]), max_price=price, min_price=price, last_price=price,
                entry_regime=str(card.get("market_regime", "unknown")), event_risk=bool(card.get("event_risk")),
            )
        return cash, position, {"date": trade_date, "code": row.code, "side": "buy", "target_level": target_level, "price": price, "shares": shares, "reason": reason}
    if position is None or trade_date <= position.entry_date:
        return cash, position, None
    sell_value = min(-delta, current_value)
    shares = position.shares if target_level == 0 else math.floor(min(position.shares, sell_value / open_price) / 100) * 100
    if shares <= 0:
        return cash, position, None
    price = open_price * (1 - slippage)
    gross = shares * price
    commission = max(costs["minimum_commission"], gross * costs["commission_bps"] / 10_000)
    stamp = gross * costs["stamp_duty_sell_bps"] / 10_000
    cash += gross - commission - stamp
    position.shares -= shares
    trade = {"date": trade_date, "code": row.code, "side": "sell", "target_level": target_level, "price": price, "shares": shares, "reason": reason}
    if target_level == 0 or position.shares <= 1e-8:
        exit_equity = cash
        trade.update(
            {
                "entry_date": position.entry_date,
                "return_pct": (exit_equity / position.entry_equity - 1) * 100,
                "r_multiple": (price - position.avg_cost) / position.initial_risk if position.initial_risk > 0 else None,
                "mfe_pct": (position.max_price / position.avg_cost - 1) * 100,
                "mae_pct": (position.min_price / position.avg_cost - 1) * 100,
                "holding_days": position.bars_held,
                "market_regime": position.entry_regime,
            }
        )
        position = None
    else:
        position.level = target_level
        position.last_price = price
    return cash, position, trade


def _normalize_panel(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "code", "name", "industry", "open", "high", "low", "close", "volume", "amount"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Backtest input missing columns: {', '.join(missing)}")
    data = frame.copy()
    data["date"] = data["date"].astype(str).str[:10]
    data["code"] = data["code"].map(normalize_code)
    data = data[data["code"].map(board_for).notna()]
    for column in ("open", "high", "low", "close", "volume", "amount", "turnover"):
        if column not in data.columns:
            data[column] = None
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["prev_close"] = data.groupby("code")["close"].shift(1)
    data["pct_change"] = (data["close"] / data["prev_close"] - 1) * 100
    return data.sort_values(["date", "code"]).reset_index(drop=True)


def _metrics(curve: list[dict[str, Any]], trades: list[dict[str, Any]], initial_cash: float) -> dict[str, Any]:
    if not curve:
        return {}
    equity = pd.Series([item["equity"] for item in curve], dtype=float)
    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    closed = [item for item in trades if item.get("side") == "sell" and "return_pct" in item]
    wins = [item for item in closed if item["return_pct"] > 0]
    gains = sum(item["return_pct"] for item in wins)
    losses = abs(sum(item["return_pct"] for item in closed if item["return_pct"] < 0))
    return {
        "total_return_pct": round((equity.iloc[-1] / initial_cash - 1) * 100, 4),
        "maximum_drawdown_pct": round(float(drawdown.min()) * 100, 4),
        "closed_trades": len(closed),
        "win_rate": round(len(wins) / len(closed), 4) if closed else None,
        "expected_trade_return_pct": round(sum(item["return_pct"] for item in closed) / len(closed), 4) if closed else None,
        "average_r": round(sum((item.get("r_multiple") or 0) for item in closed) / len(closed), 4) if closed else None,
        "profit_factor": round(gains / losses, 4) if losses > 0 else None,
        "average_mfe_pct": round(sum(item.get("mfe_pct", 0) for item in closed) / len(closed), 4) if closed else None,
        "average_mae_pct": round(sum(item.get("mae_pct", 0) for item in closed) / len(closed), 4) if closed else None,
        "average_holding_days": round(sum(item.get("holding_days", 0) for item in closed) / len(closed), 4) if closed else None,
        "performance_by_market_regime": _regime_metrics(closed),
        "drawdown_alerts": {
            "red_8_triggered": bool((drawdown <= -0.08).any()),
            "red_12_triggered": bool((drawdown <= -0.12).any()),
        },
    }


def _backtest_validation(
    dates: list[str],
    equity_curve: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    if not dates or not equity_curve:
        return {
            "trading_days": 0,
            "minimum_three_years_met": False,
            "out_of_sample_split_date": None,
            "out_of_sample_metrics": {},
            "formal_backtest_gate_passed": False,
        }
    split_index = min(len(dates) - 1, max(1, int(len(dates) * 0.70)))
    split_date = dates[split_index]
    oos_curve = [item for item in equity_curve if item["date"] >= split_date]
    baseline = float(oos_curve[0]["equity"]) if oos_curve else float(equity_curve[-1]["equity"])
    oos_trades = [
        item
        for item in trades
        if item.get("side") == "sell"
        and item.get("entry_date")
        and item["entry_date"] >= split_date
    ]
    oos_metrics = _metrics(oos_curve, oos_trades, baseline) if oos_curve else {}
    enough_history = len(dates) >= 720
    expected_positive = (oos_metrics.get("expected_trade_return_pct") or 0) > 0
    profit_factor = oos_metrics.get("profit_factor")
    no_losing_trade = bool(
        oos_metrics.get("closed_trades")
        and profit_factor is None
        and (oos_metrics.get("win_rate") or 0) == 1
    )
    profit_factor_met = bool((profit_factor is not None and profit_factor >= 1.15) or no_losing_trade)
    return {
        "trading_days": len(dates),
        "minimum_three_years_met": enough_history,
        "out_of_sample_split_date": split_date,
        "out_of_sample_metrics": oos_metrics,
        "sample_out_expectation_positive": expected_positive,
        "sample_out_profit_factor_met": profit_factor_met,
        "formal_backtest_gate_passed": enough_history and expected_positive and profit_factor_met,
        "note": "This gate covers historical performance only; live activation also requires the 20-day timing and coverage audit.",
    }


def _forward_returns(data: pd.DataFrame, signals: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    for signal in signals:
        series = data[(data["code"] == signal["code"]) & (data["date"] >= signal["date"])].sort_values("date")
        if series.empty:
            continue
        record = {"date": signal["date"], "code": signal["code"], "market_regime": signal.get("market_regime")}
        for horizon in (1, 3, 5, 10):
            record[f"return_{horizon}d_pct"] = round((series.iloc[horizon]["close"] / signal["close"] - 1) * 100, 4) if len(series) > horizon else None
        records.append(record)
    summary = {}
    for horizon in (1, 3, 5, 10):
        values = [item[f"return_{horizon}d_pct"] for item in records if item[f"return_{horizon}d_pct"] is not None]
        summary[f"{horizon}d"] = {
            "samples": len(values),
            "average_pct": round(sum(values) / len(values), 4) if values else None,
            "win_rate": round(sum(value > 0 for value in values) / len(values), 4) if values else None,
        }
    return {"summary": summary, "signals": records}


def _proxy_index_points(levels: list[float], daily_pct: float) -> float:
    latest = levels[-1]
    ma5 = sum(levels[-5:]) / 5 if len(levels) >= 5 else None
    ma10 = sum(levels[-10:]) / 10 if len(levels) >= 10 else None
    points = 0.0
    points += 4.0 if ma5 is not None and latest >= ma5 else 0.0
    points += 3.0 if ma5 is not None and ma10 is not None and ma5 > ma10 else 0.0
    points += 3.0 if daily_pct > 0 else 0.0
    return points


def _regime_metrics(closed: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for regime in ("strong", "neutral", "weak", "unknown"):
        records = [item for item in closed if item.get("market_regime") == regime]
        if not records:
            continue
        returns = [float(item["return_pct"]) for item in records]
        result[regime] = {
            "trades": len(records),
            "win_rate": round(sum(value > 0 for value in returns) / len(returns), 4),
            "average_return_pct": round(sum(returns) / len(returns), 4),
            "average_r": round(sum(float(item.get("r_multiple") or 0) for item in records) / len(records), 4),
        }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest MA5 close-confirmed strategy")
    parser.add_argument("--input", required=True, help="CSV or parquet panel with adjusted daily bars")
    parser.add_argument("--output", default="output/ma5/backtest/latest.json")
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    frame = pd.read_parquet(input_path) if input_path.suffix.lower() == ".parquet" else pd.read_csv(input_path, dtype={"code": str})
    result = run_backtest(frame, initial_cash=args.initial_cash)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["metrics"], ensure_ascii=False))


if __name__ == "__main__":
    main()
