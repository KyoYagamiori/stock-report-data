from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    import akshare as ak
except Exception:  # pragma: no cover - dependency failure path
    ak = None


TIMEZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class CalendarInfo:
    date: str
    is_trading_day: bool
    latest_completed_trading_day: str
    next_trading_day: str | None
    source: str
    valid: bool
    warning: str | None = None

    def as_manifest(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "is_trading_day": self.is_trading_day,
            "latest_completed_trading_day": self.latest_completed_trading_day,
            "next_trading_day": self.next_trading_day,
            "source": self.source,
        }


def resolve_calendar(moment: datetime, root: Path, ak_module: Any = ak) -> CalendarInfo:
    local_moment = moment.astimezone(TIMEZONE)
    dates, source, warning = _load_trade_dates(root)
    if not dates and ak_module is not None:
        dates, warning = _fetch_trade_dates(ak_module)
        if dates:
            source = "AKShare tool_trade_date_hist_sina"
            _write_trade_dates(root, dates, source)
    if not dates:
        return _weekday_fallback(local_moment, warning)

    today = local_moment.date()
    is_trading = today in dates
    completed_cutoff = time(15, 10)
    completed_candidates = [item for item in dates if item < today]
    if is_trading and local_moment.time() >= completed_cutoff:
        completed_candidates.append(today)
    latest_completed = max(completed_candidates) if completed_candidates else min(dates)
    future = [item for item in dates if item > today]
    next_trading = min(future) if future else None
    return CalendarInfo(
        date=today.isoformat(),
        is_trading_day=is_trading,
        latest_completed_trading_day=latest_completed.isoformat(),
        next_trading_day=next_trading.isoformat() if next_trading else None,
        source=source,
        valid=True,
        warning=warning,
    )


def _fetch_trade_dates(ak_module: Any) -> tuple[set[date], str | None]:
    try:
        frame = ak_module.tool_trade_date_hist_sina()
        if frame is None or frame.empty or "trade_date" not in frame.columns:
            return set(), "交易日历接口返回空或缺少 trade_date。"
        dates = {item.date() for item in frame["trade_date"] if hasattr(item, "date")}
        if not dates:
            dates = {datetime.fromisoformat(str(item)).date() for item in frame["trade_date"]}
        return dates, None
    except Exception as exc:
        return set(), f"交易日历接口失败：{str(exc)[:300]}"


def _calendar_path(root: Path) -> Path:
    return root / "output" / "cache" / "trade_calendar.json"


def _load_trade_dates(root: Path) -> tuple[set[date], str, str | None]:
    path = _calendar_path(root)
    if not path.exists():
        return set(), "unavailable", None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        dates = {date.fromisoformat(item) for item in payload.get("trade_dates", [])}
    except Exception as exc:
        return set(), "invalid-cache", f"交易日历缓存解析失败：{str(exc)[:300]}"
    return dates, str(payload.get("source", "cached-calendar")), None


def _write_trade_dates(root: Path, dates: set[date], source: str) -> None:
    path = _calendar_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source,
        "trade_dates": [item.isoformat() for item in sorted(dates)],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _weekday_fallback(moment: datetime, warning: str | None) -> CalendarInfo:
    today = moment.date()
    is_weekend = today.weekday() >= 5
    previous = today - timedelta(days=1)
    while previous.weekday() >= 5:
        previous -= timedelta(days=1)
    following = today + timedelta(days=1)
    while following.weekday() >= 5:
        following += timedelta(days=1)
    return CalendarInfo(
        date=today.isoformat(),
        is_trading_day=not is_weekend,
        latest_completed_trading_day=previous.isoformat(),
        next_trading_day=following.isoformat(),
        source="weekday-fallback-unverified",
        valid=is_weekend,
        warning=warning or "缺少交易日历；仅周末判断可视为可靠，工作日状态未通过校验。",
    )
