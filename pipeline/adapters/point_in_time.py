from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.adapters import AdapterResult
from scripts import fetch_snapshot as legacy

try:
    import akshare as ak
except Exception:  # pragma: no cover - dependency failure path
    ak = None


TIMEZONE = ZoneInfo("Asia/Shanghai")
INDEX_SYMBOLS = {
    "000001": ("sh000001", "上证指数"),
    "399001": ("sz399001", "深证成指"),
    "399006": ("sz399006", "创业板指"),
}
RECOVERABLE_PROFILES = {"trading_preopen", "trading_noon"}


def recover_fixed_point_in_time(
    stock_result: AdapterResult,
    market_result: AdapterResult,
    profile: str,
    report_date: str,
    market_date: str,
    moment: datetime,
    ak_module: Any = ak,
) -> tuple[AdapterResult, AdapterResult]:
    """Rebuild a missed fixed snapshot without relabelling later live quotes.

    GitHub scheduled jobs can start late. For early snapshots we recover the
    latest completed market close; for noon snapshots we reconstruct the exact
    11:30 state from one-minute history. Current afternoon breadth and sector
    rankings are deliberately discarded because they cannot represent noon.
    """
    if profile not in RECOVERABLE_PROFILES:
        raise ValueError(f"Unsupported point-in-time recovery profile: {profile}")
    if ak_module is None:
        raise RuntimeError("AKShare is unavailable for point-in-time recovery")

    started = moment.astimezone(TIMEZONE)
    target_date = market_date if profile == "trading_preopen" else report_date
    target_time = time(15, 0) if profile == "trading_preopen" else time(11, 30)
    recovered_stocks: list[dict[str, Any]] = []
    stock_errors: list[str] = []

    for base in stock_result.data.get("stocks", []):
        try:
            recovered_stocks.append(
                _recover_stock(base, target_date, target_time, profile, ak_module)
            )
        except Exception as exc:
            code = str(base.get("code", "unknown"))
            stock_errors.append(f"{code} 时点恢复失败：{str(exc)[:240]}")
            recovered_stocks.append(_invalidate_late_quote(base, str(exc)))

    valid_stocks = sum(bool(item.get("valid_quote")) for item in recovered_stocks)
    stock_status = (
        "success"
        if valid_stocks == len(recovered_stocks) and recovered_stocks
        else "partial"
        if valid_stocks
        else "source_error"
    )
    recovered_stock_result = AdapterResult(
        status=stock_status,
        source="新浪一分钟历史时点恢复；新浪前复权日线",
        data={
            "stocks": recovered_stocks,
            "recovery_profile": profile,
            "recovery_target": _iso_at(target_date, target_time),
        },
        started_at=started,
        finished_at=datetime.now(TIMEZONE),
        records_expected=len(recovered_stocks),
        records_valid=valid_stocks,
        errors=[
            *stock_errors,
            "本次为延迟任务的历史时点恢复，不是当前实时行情。",
        ],
    )

    recovered_market_result = _recover_market(
        market_result,
        target_date,
        target_time,
        profile,
        started,
        ak_module,
    )
    return recovered_stock_result, recovered_market_result


def _recover_stock(
    base: dict[str, Any],
    target_date: str,
    target_time: time,
    profile: str,
    ak_module: Any,
) -> dict[str, Any]:
    code = str(base["code"])
    symbol = _market_symbol(code)
    minute = _minute_frame(ak_module.stock_zh_a_minute(symbol=symbol, period="1", adjust=""))
    session = _session_rows(minute, target_date, target_time)
    quote = session.iloc[-1]
    quote_at = pd.Timestamp(quote["day"])
    previous_close = _previous_close(minute, target_date)

    price = _number(quote["close"])
    volume = _sum(session, "volume")
    amount = _sum(session, "amount")
    if price is None or previous_close in (None, 0) or amount is None:
        raise ValueError("价格、前收盘价或成交额不完整")
    pct = (price / previous_close - 1) * 100

    daily = _daily_frame(ak_module, symbol, target_date)
    technical, previous_daily = _technical_history(
        daily,
        session,
        target_date,
        profile,
    )
    outstanding = _latest_number(daily, "outstanding_share", target_date)
    turnover = volume / outstanding * 100 if volume is not None and outstanding not in (None, 0) else None
    chinese_history = _to_legacy_history(technical)
    ma_metrics = legacy.compute_ma_metrics(chinese_history, price, "新浪前复权日线+恢复时点")
    box_metrics = legacy.compute_box_metrics(chinese_history, price, "新浪前复权日线+恢复时点")

    recovered = deepcopy(base)
    recovered.update(
        {
            "valid_quote": True,
            "quote_time": quote_at.tz_localize(TIMEZONE).isoformat(),
            "latest_price": price,
            "pct_change": pct,
            "amount": amount,
            "turnover_rate": turnover,
            "price_data_source": "新浪一分钟历史时点恢复",
            "realtime_quote_available": True,
            "realtime_data_source": "新浪一分钟历史时点恢复",
            "realtime_quote_date": target_date,
            "realtime_quote_time": quote_at.strftime("%H:%M:%S"),
            "latest_trade_date": target_date,
            "daily_latest_trade_date": target_date,
            "today_close": price,
            "today_pct_change": pct,
            "today_volume": volume,
            "today_amount": amount,
            "today_turnover_rate": turnover,
            "previous_trade_date": _date_text(previous_daily.get("date")),
            "previous_volume": _number(previous_daily.get("volume")),
            "previous_amount": _number(previous_daily.get("amount")),
            "saved_snapshot_used": False,
            "saved_snapshot_source": "",
            "point_in_time_recovered": True,
            "collection_mode": "historical_point_in_time_recovery",
            "is_limit_up_pool": False,
            "limit_up_seal_amount": None,
            "first_limit_up_time": "",
            "last_limit_up_time": "",
            "break_limit_up_count": None,
            "limit_up_days": None,
            **ma_metrics,
            **box_metrics,
        }
    )
    _refresh_volume_signals(recovered)
    warnings = list(base.get("warnings") or [])
    warnings.append(
        f"GitHub任务延迟启动；已从分钟历史重建 {target_date} {quote_at.strftime('%H:%M:%S')} 时点，未使用更晚行情。"
    )
    recovered["warnings"] = warnings
    return recovered


def _recover_market(
    base: AdapterResult,
    target_date: str,
    target_time: time,
    profile: str,
    started: datetime,
    ak_module: Any,
) -> AdapterResult:
    del base
    indices: list[dict[str, Any]] = []
    errors: list[str] = []
    exchange_amounts: dict[str, float] = {}

    for code, (symbol, name) in INDEX_SYMBOLS.items():
        try:
            minute = _minute_frame(
                ak_module.stock_zh_a_minute(symbol=symbol, period="1", adjust="")
            )
            session = _session_rows(minute, target_date, target_time)
            quote = session.iloc[-1]
            previous_close = _previous_close(minute, target_date)
            latest = _number(quote["close"])
            if latest is None or previous_close in (None, 0):
                raise ValueError("指数点位或前收盘价不完整")
            quote_at = pd.Timestamp(quote["day"])
            indices.append(
                {
                    "code": code,
                    "name": name,
                    "latest": latest,
                    "pct_change": (latest / previous_close - 1) * 100,
                    "quote_time": quote_at.tz_localize(TIMEZONE).isoformat(),
                    "source": "新浪指数一分钟历史时点恢复",
                }
            )
            if code in {"000001", "399001"}:
                amount = _sum(session, "amount")
                if amount is not None:
                    exchange_amounts[code] = amount
        except Exception as exc:
            errors.append(f"{code} 指数时点恢复失败：{str(exc)[:240]}")

    turnover = None
    if {"000001", "399001"}.issubset(exchange_amounts):
        turnover = exchange_amounts["000001"] + exchange_amounts["399001"]
    market = {
        "indices": indices,
        "total_turnover": turnover,
        "turnover_valid": turnover is not None,
        "turnover_scope": "上证指数与深证成指一分钟成交额累计之和；不含北交所",
        "breadth": {},
        "breadth_valid": False,
        "sectors_top": [],
        "sectors_bottom": [],
        "quote_source": "新浪一分钟历史时点恢复",
        "index_source": "新浪指数一分钟历史时点恢复",
        "sector_source": "not_recoverable_after_the_fact",
        "point_in_time_recovered": True,
        "collection_mode": "historical_point_in_time_recovery",
        "recovery_profile": profile,
        "recovery_target": _iso_at(target_date, target_time),
    }
    if profile == "trading_noon":
        errors.extend(
            [
                "延迟任务无法事后精确恢复11:30市场宽度，已留空。",
                "延迟任务无法事后精确恢复11:30行业/概念榜，已留空。",
            ]
        )
    else:
        errors.extend(
            [
                "延迟任务未事后恢复上一交易日市场宽度，已留空。",
                "延迟任务未事后恢复上一交易日行业/概念榜，已留空。",
            ]
        )
    valid_groups = int(len(indices) >= 2) + int(turnover is not None)
    return AdapterResult(
        status="partial" if valid_groups else "source_error",
        source="新浪指数一分钟历史时点恢复",
        data=market,
        started_at=started,
        finished_at=datetime.now(TIMEZONE),
        records_expected=5,
        records_valid=valid_groups,
        errors=errors,
    )


def _minute_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError("分钟历史为空")
    required = {"day", "open", "high", "low", "close", "volume", "amount"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"分钟历史缺少字段：{','.join(sorted(missing))}")
    normalized = frame.copy()
    normalized["day"] = pd.to_datetime(normalized["day"], errors="coerce")
    normalized = normalized.dropna(subset=["day"]).sort_values("day")
    return normalized


def _session_rows(frame: pd.DataFrame, target_date: str, target_time: time) -> pd.DataFrame:
    target = date.fromisoformat(target_date)
    dates = frame["day"].dt.date
    times = frame["day"].dt.time
    rows = frame[(dates == target) & (times >= time(9, 30)) & (times <= target_time)].copy()
    if rows.empty:
        raise ValueError(f"{target_date} {target_time.isoformat()} 前无分钟记录")
    last_time = pd.Timestamp(rows.iloc[-1]["day"]).time()
    target_minutes = target_time.hour * 60 + target_time.minute
    last_minutes = last_time.hour * 60 + last_time.minute
    if target_minutes - last_minutes > 5:
        raise ValueError(f"最近分钟记录 {last_time.isoformat()} 距目标时点超过5分钟")
    return rows


def _previous_close(frame: pd.DataFrame, target_date: str) -> float | None:
    target = date.fromisoformat(target_date)
    previous = frame[frame["day"].dt.date < target]
    if previous.empty:
        return None
    return _number(previous.iloc[-1]["close"])


def _daily_frame(ak_module: Any, symbol: str, target_date: str) -> pd.DataFrame:
    target = date.fromisoformat(target_date)
    start = (target - timedelta(days=240)).strftime("%Y%m%d")
    end = target.strftime("%Y%m%d")
    frame = ak_module.stock_zh_a_daily(
        symbol=symbol,
        start_date=start,
        end_date=end,
        adjust="qfq",
    )
    if frame is None or frame.empty:
        raise ValueError("前复权日线为空")
    normalized = frame.copy().reset_index(drop=False)
    if "date" not in normalized.columns:
        raise ValueError("前复权日线缺少date字段")
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    normalized = normalized.dropna(subset=["date"]).sort_values("date")
    return normalized


def _technical_history(
    daily: pd.DataFrame,
    session: pd.DataFrame,
    target_date: str,
    profile: str,
) -> tuple[pd.DataFrame, pd.Series]:
    target = date.fromisoformat(target_date)
    before = daily[daily["date"].dt.date < target].copy()
    previous = before.iloc[-1] if not before.empty else pd.Series(dtype=object)
    if profile == "trading_preopen":
        history = daily[daily["date"].dt.date <= target].copy()
        if history.empty or history.iloc[-1]["date"].date() != target:
            history = pd.concat([before, _synthetic_daily(session, target_date, daily)], ignore_index=True)
    else:
        history = pd.concat([before, _synthetic_daily(session, target_date, daily)], ignore_index=True)
    return history.tail(80), previous


def _synthetic_daily(session: pd.DataFrame, target_date: str, daily: pd.DataFrame) -> pd.DataFrame:
    outstanding = _latest_number(daily, "outstanding_share", target_date)
    volume = _sum(session, "volume")
    turnover = volume / outstanding if volume is not None and outstanding not in (None, 0) else None
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp(target_date),
                "open": _number(session.iloc[0]["open"]),
                "high": _number(pd.to_numeric(session["high"], errors="coerce").max()),
                "low": _number(pd.to_numeric(session["low"], errors="coerce").min()),
                "close": _number(session.iloc[-1]["close"]),
                "volume": volume,
                "amount": _sum(session, "amount"),
                "outstanding_share": outstanding,
                "turnover": turnover,
            }
        ]
    )


def _to_legacy_history(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = frame.rename(
        columns={
            "date": "日期",
            "open": "开盘",
            "high": "最高",
            "low": "最低",
            "close": "收盘",
            "volume": "成交量",
            "amount": "成交额",
            "turnover": "换手率",
        }
    )
    return renamed[[column for column in ("日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额", "换手率") if column in renamed.columns]]


def _invalidate_late_quote(base: dict[str, Any], reason: str) -> dict[str, Any]:
    record = deepcopy(base)
    record.update(
        {
            "valid_quote": False,
            "quote_time": None,
            "latest_price": None,
            "pct_change": None,
            "amount": None,
            "turnover_rate": None,
            "today_close": None,
            "today_pct_change": None,
            "today_volume": None,
            "today_amount": None,
            "today_turnover_rate": None,
            "point_in_time_recovered": False,
        }
    )
    errors = list(base.get("errors") or [])
    errors.append(f"延迟任务未能恢复目标时点，已拒绝使用更晚行情：{reason}")
    record["errors"] = errors
    return record


def _refresh_volume_signals(record: dict[str, Any]) -> None:
    today = _number(record.get("today_volume"))
    previous = _number(record.get("previous_volume"))
    ratio = (today - previous) / previous if today is not None and previous not in (None, 0) else None
    pct = _number(record.get("today_pct_change"))
    record["volume_change_ratio"] = ratio
    record["is_volume_down_vs_previous"] = ratio is not None and ratio < 0
    record["is_volume_up_vs_previous"] = ratio is not None and ratio > 0
    record["volume_strength"] = legacy.volume_strength(ratio)
    record["is_volume_rise"] = bool(pct is not None and pct > 0 and ratio is not None and ratio >= 0.30)
    record["is_volume_fall"] = bool(pct is not None and pct < 0 and ratio is not None and ratio >= 0.30)
    record["is_shrink_rise"] = bool(pct is not None and pct > 0 and ratio is not None and ratio < 0)
    record["is_shrink_pullback"] = bool(pct is not None and pct < 0 and ratio is not None and ratio < 0)
    record["auto_signals"] = ["历史时点恢复；涨停池与封板字段不可事后重建"]


def _market_symbol(code: str) -> str:
    return ("sh" if code.startswith(("5", "6", "9")) else "sz") + code


def _sum(frame: pd.DataFrame, column: str) -> float | None:
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return float(values.sum()) if not values.empty else None


def _latest_number(frame: pd.DataFrame, column: str, target_date: str) -> float | None:
    if column not in frame.columns:
        return None
    target = date.fromisoformat(target_date)
    eligible = frame[frame["date"].dt.date <= target]
    if eligible.empty:
        return None
    return _number(eligible.iloc[-1][column])


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def _date_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def _iso_at(target_date: str, target_time: time) -> str:
    return f"{target_date}T{target_time.isoformat()}+08:00"
