"""Bounded public quote collection. Pool totals are NEVER market totals."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from pipeline.adapters import AdapterResult
from pipeline.contracts import load_report_pools
from pipeline.close_verification import verify_completed_close
from scripts.fetch_snapshot import compute_indicators, compute_ma_metrics

TZ = ZoneInfo("Asia/Shanghai")
SOURCE = "新浪证券批量行情（源日期时间）"
INDEX_SYMBOLS = ("sh000001", "sz399001", "sz399006")


def symbol(code):
    return ("sh" if code.startswith(("6", "5", "9")) else "bj" if code.startswith(("4", "8")) else "sz") + code


def parse_quotes(text):
    result = {}
    for sym, raw in re.findall(r'var hq_str_([a-z]{2}\d{6})="([^"]*)";', text):
        parts = raw.split(",")
        if len(parts) < 32:
            continue
        try:
            stamp = datetime.fromisoformat(parts[30] + "T" + parts[31]).replace(tzinfo=TZ)
            price, previous = float(parts[3]), float(parts[2])
            if price <= 0 or previous <= 0:
                continue
            result[sym] = {"name": parts[0], "latest_price": price,
                "pct_change": (price / previous - 1) * 100,
                "today_open": float(parts[1]), "previous_close": previous,
                "today_high": float(parts[4]), "today_low": float(parts[5]),
                "today_volume": float(parts[8]), "today_amount": float(parts[9]),
                "volume_unit": "shares", "amount_unit": "CNY",
                "quote_time": stamp.isoformat(), "latest_trade_date": stamp.date().isoformat()}
        except (ValueError, IndexError):
            continue
    return result


def parse_tencent(text):
    result = {}
    for sym, raw in re.findall(r'v_([a-z]{2}\d{6})="([^"]*)";', text):
        parts = raw.split("~")
        if len(parts) < 38:
            continue
        try:
            stamp = datetime.strptime(parts[30], "%Y%m%d%H%M%S").replace(tzinfo=TZ)
            price, previous = float(parts[3]), float(parts[4])
            if price <= 0 or previous <= 0:
                continue
            result[sym] = {"name": parts[1], "latest_price": price,
                "pct_change": (price / previous - 1) * 100,
                "today_open": float(parts[5]), "previous_close": previous,
                "today_high": float(parts[33]), "today_low": float(parts[34]),
                "today_volume": None, "today_amount": float(parts[37]) * 10000,
                "volume_unit": "unverified_unavailable", "amount_unit": "CNY",
                "quote_time": stamp.isoformat(), "latest_trade_date": stamp.date().isoformat(),
                "source": "腾讯证券批量行情（成交额万元转元，成交量单位未核验故留空）"}
        except (ValueError, IndexError):
            continue
    return result


def fetch_quotes(symbols):
    result = {}
    failures = []
    for url, parser in (("https://hq.sinajs.cn/list=", parse_quotes),
                        ("https://qt.gtimg.cn/q=", parse_tencent)):
        missing = [sym for sym in symbols if sym not in result]
        if not missing:
            break
        try:
            response = requests.get(url + ",".join(missing),
                headers={"Referer": "https://finance.sina.com.cn"}, timeout=(15, 20))
            response.raise_for_status()
            response.encoding = "gb18030"
            result.update(parser(response.text))
        except requests.RequestException as exc:
            failures.append(f"{url}: {type(exc).__name__}")
    if not result:
        raise RuntimeError("quote providers unavailable: " + "; ".join(failures))
    return result


def fetch_daily_frame(code, quote_symbol=None):
    url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/CN_MarketDataService.getKLineData"
    response = requests.get(url, params={"symbol": quote_symbol or symbol(code), "scale": 240,
        "ma": "no", "datalen": 160}, timeout=(15, 20))
    response.raise_for_status()
    match = re.search(r'\(\s*(\[.*\])\s*\)', response.text, re.S)
    if not match:
        raise ValueError("daily bars missing")
    frame = pd.DataFrame(json.loads(match.group(1)))
    frame = frame.rename(columns={"day": "日期", "close": "收盘", "high": "最高", "low": "最低"})
    frame["日期"] = pd.to_datetime(frame["日期"])
    for key in ("open", "最高", "最低", "收盘", "volume"):
        frame[key] = pd.to_numeric(frame[key], errors="coerce")
    return frame.sort_values("日期")


def daily_indicators(code, market_date, quote_time, quote_symbol=None):
    frame = fetch_daily_frame(code, quote_symbol)
    # During the session publish only completed daily indicators, labelled by date.
    quote = datetime.fromisoformat(quote_time)
    mask = frame["日期"].dt.strftime("%Y-%m-%d") <= market_date
    if quote.time() < time(15):
        mask &= frame["日期"].dt.strftime("%Y-%m-%d") < market_date
    frame = frame[mask]
    result = compute_indicators(frame, "新浪240分钟日线（未复权，已完成日线）", "unadjusted")
    result.update(compute_ma_metrics(frame, None, "新浪已完成日线"))
    result["indicator_is_completed_daily"] = True
    if not frame.empty:
        last = frame.iloc[-1]
        result["completed_daily_bar"] = {
            "date": last["日期"].strftime("%Y-%m-%d"),
            "open": float(last["open"]), "high": float(last["最高"]),
            "low": float(last["最低"]), "close": float(last["收盘"]),
            "volume": float(last["volume"]),
        }
    return result


def collect_direct(root, moment, market_date, mode):
    del root
    started = moment.astimezone(TZ)
    pools = load_report_pools()
    entries = [(group, entry) for group in ("core", "watch", "supplemental") for entry in pools[group]]
    symbols = [symbol(entry["code"]) for _, entry in entries] + list(INDEX_SYMBOLS)
    quotes = fetch_quotes(symbols)
    stocks, errors = [], []
    for group, entry in entries:
        code = entry["code"]
        quote = quotes.get(symbol(code), {})
        valid = bool(quote) and quote["latest_trade_date"] == market_date
        row = {**quote, "code": code, "name": quote.get("name", entry["name"]),
            "pool": group, "locked": bool(entry.get("locked")), "valid_quote": valid,
            "amount": quote.get("today_amount"), "today_close": quote.get("latest_price"),
            "today_pct_change": quote.get("pct_change"), "turnover_rate": None,
            "price_data_source": quote.get("source", SOURCE), "indicator_status": "missing", "warnings": [],
            "same_phase_amount_ratio": None, "volume_comparison_valid": False}
        if not valid:
            row["warnings"].append("未取得目标交易日的有效源行情，不沿用旧报价。")
        stocks.append(row)
    def enrich(row):
        if row["valid_quote"] and (mode == "full" or row["locked"]):
            try:
                row.update(daily_indicators(row["code"], market_date, row["quote_time"]))
                row.update(verify_completed_close(row, row.get("completed_daily_bar", {}), market_date))
            except Exception as exc:
                row["warnings"].append(f"日线指标缺失：{type(exc).__name__}: {str(exc)[:140]}")
        return row
    with ThreadPoolExecutor(max_workers=6) as executor:
        stocks = list(executor.map(enrich, stocks))
    def enrich_index(sym):
        row = quotes.get(sym)
        if row and row["latest_trade_date"] == market_date:
            row = dict(row)
            if datetime.fromisoformat(row["quote_time"]).time() >= time(15):
                try:
                    daily = daily_indicators(sym[2:], market_date, row["quote_time"], quote_symbol=sym)
                    row.update(verify_completed_close(row, daily.get("completed_daily_bar", {}), market_date))
                except Exception as exc:
                    errors.append(f"{sym} 收盘日线核验缺失：{type(exc).__name__}")
            return {**row, "code": sym[2:], "latest": row["latest_price"], "source": row.get("source", SOURCE)}
        return None
    with ThreadPoolExecutor(max_workers=3) as executor:
        indices = [row for row in executor.map(enrich_index, INDEX_SYMBOLS) if row]
    frame = pd.DataFrame()
    frame.attrs["direct_indices"] = indices
    frame.attrs["quote_scope"] = "configured_pool_only"
    frame.attrs["fetch_full_market"] = mode == "full"
    valid_count = sum(row["valid_quote"] for row in stocks)
    errors.append("批量接口仅覆盖配置池；全市场成交额、宽度及板块排名缺失，禁止以池内汇总替代。")
    close_verified = (valid_count == len(stocks) and len(indices) == 3
                      and all(row.get("close_quote_verified") for row in [*stocks, *indices]))
    return AdapterResult(status="success" if valid_count == len(stocks) else "partial",
        source="; ".join(sorted({row["price_data_source"] for row in stocks})), data={"stocks": stocks, "completed_close_verified": close_verified}, started_at=started, finished_at=datetime.now(TZ),
        records_expected=len(stocks), records_valid=valid_count, errors=errors), frame


def fetch_full_market():
    """Fetch every Sina SH/SZ A-share page concurrently, or discard all totals."""
    base = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center."
    response = requests.get(base + "getHQNodeStockCount", params={"node": "hs_a"}, timeout=(15, 20))
    response.raise_for_status()
    count = int(re.search(r'\d+', response.text).group())
    if not 4000 <= count <= 10000:
        raise ValueError("unexpected market universe count")
    pages = (count + 79) // 80
    def page(number):
        response = requests.get(base + "getHQNodeData", params={"page": number, "num": 80,
            "sort": "symbol", "asc": 1, "node": "hs_a", "symbol": "", "_s_r_a": "page"}, timeout=(15, 20))
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise ValueError("market page is not a list")
        return rows
    with ThreadPoolExecutor(max_workers=6) as executor:
        rows = [row for batch in executor.map(page, range(1, pages + 1)) for row in batch]
    frame = pd.DataFrame(rows).drop_duplicates('symbol')
    if len(frame) != count:
        raise ValueError(f"incomplete market coverage: {len(frame)}/{count}")
    frame = frame.rename(columns={"symbol":"代码", "name":"名称", "changepercent":"涨跌幅", "amount":"成交额"})
    for column in ("涨跌幅", "成交额"):
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any():
            raise ValueError(f"incomplete {column}")
        frame[column] = values
    frame.attrs['quote_scope'] = 'sina_hs_a_complete'
    frame.attrs['expected_count'] = count
    return frame
