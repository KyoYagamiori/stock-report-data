from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

try:
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None


INDEX_SYMBOLS = {"000001": "sh000001", "399001": "sz399001", "399006": "sz399006"}


def enrich_index_trends(
    indices: list[dict[str, Any]],
    moment: datetime,
    ak_module: Any = ak,
) -> tuple[list[dict[str, Any]], list[str]]:
    if ak_module is None:
        return indices, ["AKShare unavailable for index trend history"]
    start = (moment.date() - timedelta(days=45)).strftime("%Y%m%d")
    end = moment.date().strftime("%Y%m%d")
    errors: list[str] = []
    enriched = []
    for item in indices:
        record = dict(item)
        symbol = INDEX_SYMBOLS.get(str(item.get("code")))
        if not symbol:
            enriched.append(record)
            continue
        try:
            frame = ak_module.stock_zh_index_daily_em(symbol=symbol, start_date=start, end_date=end)
            close_column = _column(frame, ("close", "收盘"))
            if close_column is None:
                raise ValueError("missing close column")
            closes = pd.to_numeric(frame[close_column], errors="coerce").dropna().tolist()
            current = _number(item.get("latest"))
            if current is not None and (not closes or abs(closes[-1] - current) / current > 0.0001):
                closes.append(current)
            record["ma5"] = _mean(closes, 5)
            record["ma10"] = _mean(closes, 10)
            record["trend_points"] = _trend_points(record)
        except Exception as exc:
            errors.append(f"{symbol}: index trend failed: {str(exc)[:180]}")
        enriched.append(record)
    return enriched, errors


def _trend_points(record: dict[str, Any]) -> float:
    latest, ma5, ma10 = _number(record.get("latest")), _number(record.get("ma5")), _number(record.get("ma10"))
    points = 0.0
    points += 4.0 if latest is not None and ma5 is not None and latest >= ma5 else 0.0
    points += 3.0 if ma5 is not None and ma10 is not None and ma5 > ma10 else 0.0
    points += 3.0 if (_number(record.get("pct_change")) or 0) > 0 else 0.0
    return points


def _column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _mean(values: list[float], period: int) -> float | None:
    return float(sum(values[-period:]) / period) if len(values) >= period else None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if not pd.isna(number) else None

