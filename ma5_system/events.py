from __future__ import annotations

from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

import pandas as pd

try:
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None


EVENT_KEYWORDS = (
    "业绩预告",
    "业绩快报",
    "年度报告",
    "季度报告",
    "监管",
    "问询",
    "立案",
    "重大事项",
    "重大资产重组",
    "停牌",
    "复牌",
    "减持",
    "股东大会",
)


def fetch_event_risks(
    codes: Iterable[str],
    market_date: str,
    ak_module: Any = ak,
    lookback_days: int = 3,
    forward_days: int = 7,
) -> tuple[dict[str, list[dict[str, str]]], list[str]]:
    if ak_module is None or not hasattr(ak_module, "stock_zh_a_disclosure_report_cninfo"):
        return {}, ["CNInfo disclosure adapter is unavailable"]
    anchor = date.fromisoformat(market_date)
    start = (anchor - timedelta(days=lookback_days)).strftime("%Y%m%d")
    end = (anchor + timedelta(days=forward_days)).strftime("%Y%m%d")
    events: dict[str, list[dict[str, str]]] = {}
    errors: list[str] = []
    def fetch(code: str) -> tuple[str, pd.DataFrame]:
        return code, ak_module.stock_zh_a_disclosure_report_cninfo(
                symbol=str(code), market="沪深京", keyword="", category="", start_date=start, end_date=end
            )
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch, str(code)): str(code) for code in codes}
        for future in as_completed(futures):
            code = futures[future]
            try:
                _, frame = future.result()
                matches = _normalize_events(frame)
                events[code] = matches
            except Exception as exc:
                errors.append(f"{code}: disclosure fetch failed: {str(exc)[:180]}")
    return events, errors


def _normalize_events(frame: pd.DataFrame) -> list[dict[str, str]]:
    if frame is None or frame.empty:
        return []
    title_column = _column(frame, ("公告标题", "标题", "title"))
    date_column = _column(frame, ("公告时间", "公告日期", "date"))
    url_column = _column(frame, ("公告链接", "url"))
    if title_column is None:
        return []
    records = []
    for _, row in frame.iterrows():
        title = str(row.get(title_column, "") or "").strip()
        if not title or not any(keyword in title for keyword in EVENT_KEYWORDS):
            continue
        records.append(
            {
                "title": title,
                "date": str(row.get(date_column, "") or "")[:10] if date_column else "",
                "url": str(row.get(url_column, "") or "") if url_column else "",
            }
        )
    return records[:10]


def _column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None
