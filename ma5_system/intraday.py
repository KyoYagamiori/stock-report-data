from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Iterable

import pandas as pd

try:
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None


def fetch_intraday_metrics(
    codes: Iterable[str],
    moment: datetime,
    ak_module: Any = ak,
    workers: int = 8,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if ak_module is None or not hasattr(ak_module, "stock_zh_a_hist_min_em"):
        return {}, ["AKShare minute adapter is unavailable"]
    start = f"{moment.date().isoformat()} 09:30:00"
    end = moment.strftime("%Y-%m-%d %H:%M:%S")
    metrics: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    def fetch(code: str) -> tuple[str, pd.DataFrame]:
        return code, ak_module.stock_zh_a_hist_min_em(
            symbol=code,
            start_date=start,
            end_date=end,
            period="5",
            adjust="qfq",
        )

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(fetch, str(code)): str(code) for code in codes}
        for future in as_completed(futures):
            code = futures[future]
            try:
                _, frame = future.result()
                result = normalize_intraday_frame(frame)
                if result is None:
                    errors.append(f"{code}: minute data incomplete")
                else:
                    metrics[code] = result
            except Exception as exc:
                errors.append(f"{code}: minute fetch failed: {str(exc)[:180]}")
    return metrics, errors


def normalize_intraday_frame(frame: pd.DataFrame) -> dict[str, Any] | None:
    if frame is None or frame.empty:
        return None
    time_column = _column(frame, ("时间", "day", "datetime", "time"))
    close_column = _column(frame, ("收盘", "close"))
    high_column = _column(frame, ("最高", "high"))
    volume_column = _column(frame, ("成交量", "volume"))
    if time_column is None or close_column is None or high_column is None or volume_column is None:
        return None
    data = frame.copy()
    data["_close"] = pd.to_numeric(data[close_column], errors="coerce")
    data["_high"] = pd.to_numeric(data[high_column], errors="coerce")
    data["_volume"] = pd.to_numeric(data[volume_column], errors="coerce")
    data = data.dropna(subset=["_close", "_high", "_volume"])
    if len(data) < 3 or data["_volume"].sum() <= 0:
        return None
    vwap = float((data["_close"] * data["_volume"]).sum() / data["_volume"].sum())
    prior_tail = data.iloc[-4:-1] if len(data) >= 4 else data.iloc[:-1]
    local_tail_high = float(prior_tail["_high"].max()) if not prior_tail.empty else float(data.iloc[-1]["_high"])
    latest = float(data.iloc[-1]["_close"])
    return {
        "minute_source": "AKShare stock_zh_a_hist_min_em qfq 5m",
        "minute_quote_time": str(data.iloc[-1][time_column]),
        "minute_bars": int(len(data)),
        "minute_vwap": vwap,
        "local_tail_high": local_tail_high,
        "reclaimed_vwap": latest >= vwap,
        "intraday_data_complete": True,
    }


def apply_intraday_metrics(record: dict[str, Any], metrics: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(record)
    if metrics is None:
        updated.update(
            {
                "minute_source": None,
                "minute_quote_time": None,
                "minute_bars": 0,
                "minute_vwap": None,
                "local_tail_high": None,
                "reclaimed_vwap": False,
                "intraday_data_complete": False,
                "confirmation_met": False,
            }
        )
        return updated
    updated.update(metrics)
    levels = [
        value
        for value in (
            _number(updated.get("confirmation_price")),
            _number(metrics.get("minute_vwap")),
            _number(metrics.get("local_tail_high")),
        )
        if value is not None
    ]
    if levels:
        updated["confirmation_price"] = max(levels)
    latest = _number(updated.get("latest"))
    confirmation = _number(updated.get("confirmation_price"))
    updated["confirmation_met"] = bool(latest is not None and confirmation is not None and latest >= confirmation and metrics.get("reclaimed_vwap"))
    return updated


def _column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if not pd.isna(number) else None

