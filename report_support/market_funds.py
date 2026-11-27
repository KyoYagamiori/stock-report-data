"""Read dated public Dragon and Tiger List tables and narrow fund-flow estimates."""

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
import json
from math import isfinite
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

DATACENTER = "https://datacenter-web.eastmoney.com/api/data/v1/get"
DAILY_FLOW = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
OVERVIEW = "RPT_DAILYBILLBOARD_DETAILS"
INSTITUTIONS = "RPT_ORGANIZATION_TRADE_DETAILS"
SEAT_REPORTS = {"buy_seats": "RPT_BILLBOARD_DAILYDETAILSBUY", "sell_seats": "RPT_BILLBOARD_DAILYDETAILSSELL"}
BASE_FIELDS = ("SECURITY_CODE", "SECUCODE", "TRADE_DATE", "EXPLANATION", "ACCUM_AMOUNT")
OVERVIEW_FIELDS = BASE_FIELDS + (
    "SECURITY_NAME_ABBR", "TRADE_ID", "CHANGE_TYPE", "CLOSE_PRICE", "CHANGE_RATE",
    "TURNOVERRATE", "BILLBOARD_BUY_AMT", "BILLBOARD_SELL_AMT", "BILLBOARD_NET_AMT",
)
INSTITUTION_FIELDS = BASE_FIELDS + ("BUY_TIMES", "SELL_TIMES", "BUY_AMT", "SELL_AMT", "NET_BUY_AMT")
SEAT_FIELDS = BASE_FIELDS + ("TRADE_ID", "OPERATEDEPT_CODE", "OPERATEDEPT_NAME", "BUY", "SELL", "NET")
CHINA = ZoneInfo("Asia/Shanghai")
TIMEOUT_SECONDS = 8
PAGE_SIZE = 100
MAX_PAGES = 5
A_SHARE_PREFIXES = {"SH": ("60", "688"), "SZ": ("000", "001", "002", "003", "300", "301", "302")}


def is_a_share(code):
    symbol, _, market = code.partition(".")
    return (len(symbol) == 6 and symbol.isascii() and symbol.isdigit()
            and symbol.startswith(A_SHARE_PREFIXES.get(market, ())))


def request_json(endpoint, params):
    url = endpoint + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def fetch_board(trade_date, report, fields, *, trade_id=None):
    filters = f"(TRADE_DATE='{trade_date}')"
    if trade_id is not None:
        filters = f"(TRADE_ID={trade_id})"
    params = {"reportName": report, "columns": "ALL", "filter": filters,
              "pageSize": PAGE_SIZE, "source": "WEB", "client": "WEB"}
    if trade_id is None:
        sort_columns = "BILLBOARD_NET_AMT,SECURITY_CODE,EXPLANATION" if report == OVERVIEW else "NET_BUY_AMT,SECURITY_CODE,EXPLANATION"
        params.update(sortColumns=sort_columns, sortTypes="-1,1,1")
    rows = []
    expected_count = None
    for page in range(1, MAX_PAGES + 1):
        payload = request_json(DATACENTER, {**params, "pageNumber": page})
        result = payload.get("result")
        if payload.get("success") is not True or not result:
            raise ValueError("No confirmed board rows for the requested session")
        count, pages = result["count"], result["pages"]
        if page == 1:
            expected_count = count
        if count != expected_count or pages > MAX_PAGES:
            raise ValueError("Board pagination changed or exceeded the read limit")
        rows.extend(result.get("data") or [])
        if page >= pages:
            break
    if len(rows) != expected_count:
        raise ValueError("Board row count does not reconcile")
    if any(row["TRADE_DATE"][:10] != trade_date for row in rows):
        raise ValueError("Board contains a different trading date")
    if trade_id is not None and any(int(row["TRADE_ID"]) != trade_id for row in rows):
        raise ValueError("Board contains a different disclosure")
    scoped_rows = [{key: row[key] for key in fields} for row in rows if is_a_share(row["SECUCODE"])]
    return {"provider_row_count": len(rows), "scope_row_count": len(scoped_rows), "rows": scoped_rows}


def fetch_daily_flow(trade_date, code):
    symbol, exchange = code.split(".")
    market = {"SH": "1", "SZ": "0"}[exchange]
    params = {"secid": f"{market}.{symbol}", "klt": "101", "lmt": 10,
              "fields1": "f1,f2,f3,f7", "fields2": "f51,f52,f55,f56"}
    payload = request_json(DAILY_FLOW, params)
    data = payload.get("data") or {}
    if data.get("code") != symbol or str(data.get("market")) != market:
        raise ValueError("Fund-flow symbol or market does not match")
    lines = [line.split(",") for line in data["klines"] if line.split(",", 1)[0] == trade_date]
    if len(lines) != 1:
        raise ValueError("No unique dated fund-flow row")
    main, large, extra_large = map(float, lines[0][1:])
    if not all(map(isfinite, (main, large, extra_large))):
        raise ValueError("Fund-flow amount is not finite")
    return {"code": code, "main_order_net_cny": main, "large_order_net_cny": large,
            "extra_large_order_net_cny": extra_large}


def collect(trade_date, *, trade_id=None, flow_codes=()):
    if trade_id is None:
        jobs = {
            "board": (fetch_board, (trade_date, OVERVIEW, OVERVIEW_FIELDS), {}),
            "institutions": (fetch_board, (trade_date, INSTITUTIONS, INSTITUTION_FIELDS), {}),
        }
    else:
        jobs = {side: (fetch_board, (trade_date, report, SEAT_FIELDS), {"trade_id": trade_id})
                for side, report in SEAT_REPORTS.items()}
    jobs.update({code: (fetch_daily_flow, (trade_date, code), {}) for code in flow_codes})
    tables = {}
    with ThreadPoolExecutor(max_workers=min(5, len(jobs))) as pool:
        pending = {name: pool.submit(func, *args, **kwargs) for name, (func, args, kwargs) in jobs.items()}
        for name, future in pending.items():
            try:
                tables[name] = {"status": "available", **future.result()}
            except (OSError, KeyError, TypeError, ValueError) as exc:
                tables[name] = {"status": "unavailable", "error": str(exc)}
    return {"trade_date": trade_date, "retrieved_at": datetime.now(CHINA).isoformat(timespec="seconds"),
            "source": {"board": DATACENTER, "daily_flow": DAILY_FLOW}, "tables": tables}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("trade_date", type=date.fromisoformat)
    parser.add_argument("--trade-id", type=int)
    parser.add_argument("--flow-code", action="append", default=[])
    args = parser.parse_args()
    now = datetime.now(CHINA)
    if args.trade_date > now.date():
        parser.error("trade_date is in the future")
    if args.trade_date == now.date() and now.time() < time(15):
        parser.error("the requested daily session has not closed")
    for code in args.flow_code:
        if not is_a_share(code):
            parser.error("flow-code must be an A-share code with .SH or .SZ")
    result = collect(args.trade_date.isoformat(), trade_id=args.trade_id, flow_codes=args.flow_code)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
