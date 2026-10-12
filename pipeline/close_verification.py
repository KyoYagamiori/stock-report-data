"""Verify a completed close without changing the provider's update timestamp."""
from __future__ import annotations

import math
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
DAILY_SOURCE = "新浪240分钟未复权日线"


def verify_completed_close(record: dict[str, Any], bar: dict[str, Any], market_date: str) -> dict[str, Any]:
    stamp = _timestamp(record.get("quote_time"))
    verified = bool(stamp and stamp.date().isoformat() == market_date
                    and stamp.time().replace(tzinfo=None) >= time(15)
                    and bar.get("date") == market_date)
    for quote_key, bar_key in (("latest_price", "close"), ("today_open", "open"),
                               ("today_high", "high"), ("today_low", "low")):
        verified = verified and _same_number(record.get(quote_key), bar.get(bar_key))
    return {
        "close_quote_verified": verified,
        "market_asof": f"{market_date}T15:00:00+08:00" if verified else None,
        "close_verification": {
            "status": "verified" if verified else "unverified",
            "source": DAILY_SOURCE,
            "market_date": market_date,
            "quote_time": record.get("quote_time"),
            "daily_bar": dict(bar),
        },
    }


def has_verified_completed_close(record: dict[str, Any], market_date: str) -> bool:
    evidence = record.get("close_verification", {})
    if not record.get("close_quote_verified") or evidence.get("quote_time") != record.get("quote_time"):
        return False
    if evidence.get("source") != DAILY_SOURCE or evidence.get("market_date") != market_date:
        return False
    quote = dict(record)
    if "latest_price" not in quote:
        quote["latest_price"] = quote.get("latest")
    return verify_completed_close(quote, evidence.get("daily_bar", {}), market_date)["close_quote_verified"]


def completed_close_window_verified(snapshot: dict[str, Any]) -> bool:
    """Only independently verified records may pass an after-close time window."""
    market_date = str(snapshot.get("market_date", ""))
    records = [row for row in snapshot.get("stocks", []) if row.get("valid_quote")]
    records.extend(snapshot.get("market", {}).get("indices", []))
    if not records:
        return False
    stamps = [_timestamp(row.get("quote_time")) for row in records]
    if any(stamp is None or stamp.date().isoformat() != market_date for stamp in stamps):
        return False
    if any(stamp.time().replace(tzinfo=None) < time(15) for stamp in stamps):
        return False
    # Records inside the original close window retain the established path.
    if any(stamp.time().replace(tzinfo=None) >= time(16)
           and not has_verified_completed_close(row, market_date)
           for row, stamp in zip(records, stamps)):
        return False
    return max(stamps) == _timestamp(snapshot.get("quote_time_max"))


def _same_number(left: Any, right: Any) -> bool:
    try:
        return math.isclose(float(left), float(right), rel_tol=0, abs_tol=0.005)
    except (TypeError, ValueError):
        return False


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.astimezone(TZ) if parsed.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None
