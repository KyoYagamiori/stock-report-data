from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.adapters import AdapterResult
from pipeline.contracts import load_report_pools
from scripts import fetch_snapshot as legacy


TIMEZONE = ZoneInfo("Asia/Shanghai")


def collect_stock_quotes(
    root: Path,
    moment: datetime,
    market_date: str,
    mode: str,
) -> tuple[AdapterResult, pd.DataFrame]:
    started = moment.astimezone(TIMEZONE)
    pools = load_report_pools()
    pool_by_code = {
        record["code"]: pool_name
        for pool_name in ("core", "watch", "supplemental")
        for record in pools[pool_name]
    }
    expected_codes = set(pool_by_code)
    spot_result = legacy.fetch_realtime_spot()
    payload = legacy.collect_snapshot_payload(
        generated_at=started,
        root=root,
        active_codes=expected_codes,
        mode=mode,
        spot_result=spot_result,
        apply_observation_updates=False,
    )
    stocks = [
        _normalize_stock(record, pool_by_code.get(record.get("code", ""), "watch"), market_date)
        for record in payload["stocks"]
    ]
    returned_codes = {record["code"] for record in stocks}
    for pool_name in ("core", "watch", "supplemental"):
        for configured in pools[pool_name]:
            if configured["code"] not in returned_codes:
                stocks.append(_missing_stock(configured, pool_name, "观察池配置未进入旧采集脚本"))

    valid = sum(1 for record in stocks if record["valid_quote"])
    errors = [*payload.get("errors", []), *payload.get("warnings", [])]
    if valid == len(stocks):
        status = "success"
    elif valid > 0:
        status = "partial"
    else:
        status = "source_error"
    finished = datetime.now(TIMEZONE)
    return (
        AdapterResult(
            status=status,
            source=spot_result[1],
            data={"stocks": stocks, "legacy_payload": payload},
            started_at=started,
            finished_at=finished,
            records_expected=len(expected_codes),
            records_valid=valid,
            errors=errors,
        ),
        spot_result[0],
    )


def _normalize_stock(record: dict[str, Any], pool: str, market_date: str) -> dict[str, Any]:
    quote_time = _stock_quote_time(record)
    trade_date = str(record.get("latest_trade_date", ""))
    price = legacy.safe_number(record.get("today_close"))
    pct = legacy.safe_number(record.get("today_pct_change"))
    amount = legacy.safe_number(record.get("today_amount"))
    turnover = legacy.safe_number(record.get("today_turnover_rate"))
    valid_quote = (
        trade_date == market_date
        and price is not None
        and pct is not None
        and (amount is not None or turnover is not None)
    )
    normalized = dict(record)
    normalized.update(
        {
            "pool": pool,
            "valid_quote": valid_quote,
            "quote_time": quote_time,
            "latest_price": price,
            "pct_change": pct,
            "amount": amount,
            "turnover_rate": turnover,
        }
    )
    return normalized


def _stock_quote_time(record: dict[str, Any]) -> str | None:
    quote_date = str(record.get("realtime_quote_date", ""))
    quote_time = str(record.get("realtime_quote_time", "")).strip()
    if quote_date and quote_time:
        if "T" in quote_time:
            return quote_time
        return f"{quote_date}T{quote_time}+08:00"
    trade_date = str(record.get("latest_trade_date", ""))
    if trade_date and not record.get("realtime_quote_available"):
        return f"{trade_date}T15:00:00+08:00"
    return None


def _missing_stock(configured: dict[str, Any], pool: str, error: str) -> dict[str, Any]:
    return {
        "code": configured["code"],
        "name": configured["name"],
        "pool": pool,
        "locked": bool(configured.get("locked")),
        "valid_quote": False,
        "quote_time": None,
        "latest_price": None,
        "pct_change": None,
        "amount": None,
        "turnover_rate": None,
        "warnings": [],
        "errors": [error],
    }
