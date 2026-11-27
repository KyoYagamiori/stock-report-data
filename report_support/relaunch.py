"""Screen a fixed sample of former A-share leaders on completed daily bars."""

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, time
import json
from math import isfinite
from statistics import median

from .market_funds import CHINA, is_a_share, request_json

KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
HISTORICAL_END = "2025-12-31"
COHORT = """
000017 000032 000062 000099 000158 000530 000536 000628 000676 000678 000711
000766 000938 000977 001696 002031 002046 002085 002123 002148 002172 002173
002174 002175 002232 002242 002261 002272 002281 002292 002343 002369 002472
002583 002625 002654 002691 002771 002786 002813 002855 002896 002962 002693
300010 300058 300085 300133 300308 300339 300364 300394 300418 300459 300496
300502 300781 301236 600088 600152 600186 600355 600410 600501 600520 600550
600611 600630 600640 600715 600734 600839 601360 601929 603000 603019 603083
603108 603178 603598 603716 605588 688327 688343 688365
""".split()


@dataclass(frozen=True)
class Bar:
    day: str
    open: float
    close: float
    high: float
    low: float
    amount: float
    change_pct: float


def market_symbol(code):
    return code + (".SH" if code.startswith("6") else ".SZ")


def fetch_history(code, asof):
    secid = ("1." if code.startswith("6") else "0.") + code
    payload = request_json(KLINE, {
        "secid": secid, "klt": 101, "fqt": 1, "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59",
        "beg": 20230101, "end": asof.replace("-", ""), "lmt": 1800,
    })["data"]
    if payload["code"] != code:
        raise ValueError("History symbol does not match")
    return payload


def parse_bars(payload, asof):
    bars = []
    for row in payload["klines"]:
        day, opening, closing, high, low, volume, amount, _, change, *_ = row.split(",")
        if date.fromisoformat(day).isoformat() != day or day > asof:
            raise ValueError("History date is outside the requested cutoff")
        o, c, h, l, v, a, p = map(float, (opening, closing, high, low, volume, amount, change))
        if not all(map(isfinite, (o, c, h, l, v, a, p))) or not 0 < l <= min(o, c) <= max(o, c) <= h:
            raise ValueError("Invalid daily bar")
        if v > 0 and a > 0:
            bars.append(Bar(day, o, c, h, l, a, p))
    if any(a.day >= b.day for a, b in zip(bars, bars[1:])):
        raise ValueError("Daily bars are out of order or repeated")
    return bars


def measure_base(bars):
    high = max(row.high for row in bars)
    low = min(row.low for row in bars)
    return {"from": bars[0].day, "through": bars[-1].day, "high": high, "low": low,
            "range_pct": (high / low - 1) * 100,
            "close_change_pct": (bars[-1].close / bars[0].close - 1) * 100}


def fits_base(box, range_limit, change_limit):
    return box["range_pct"] <= range_limit and abs(box["close_change_pct"]) <= change_limit


def screen_history(payload, asof):
    code, name = payload["code"], payload["name"]
    bars = parse_bars(payload, asof)
    result = {"code": code, "name": name, "asof": bars[-1].day if bars else None}
    if not bars or bars[-1].day != asof:
        return {**result, "status": "quote_not_current"}
    if name.upper().startswith(("ST", "*ST")) or name.endswith("退"):
        return {**result, "status": "risk_warning"}
    historical = [row for row in bars if row.day <= HISTORICAL_END]
    if len(bars) < 121 or len(historical) < 21:
        return {**result, "status": "insufficient_history"}

    peak = max(historical, key=lambda row: row.high)
    best_swing = max((row.close / historical[index - 20].close - 1) * 100
                     for index, row in enumerate(historical) if index >= 20)
    sessions_after_peak = sum(row.day > peak.day for row in bars)
    last = bars[-1]
    decline = (last.close / peak.high - 1) * 100
    box_60 = measure_base(bars[-60:])
    box_120 = measure_base(bars[-120:])
    qualifies_60 = fits_base(box_60, 30, 12)
    qualifies_120 = qualifies_60 and fits_base(box_120, 40, 15)
    high_20 = max(row.high for row in bars[-21:-1])
    high_60 = max(row.high for row in bars[-61:-1])
    amount_multiple = last.amount / median(row.amount for row in bars[-21:-1])
    old_leader = best_swing >= 60 and sessions_after_peak >= 120 and decline <= -20

    return {
        **result, "status": "screened", "old_leader": old_leader, "old_high": peak.high,
        "old_high_date": peak.day, "past_max_20d_gain_pct": best_swing, "sessions_after_peak": sessions_after_peak,
        "decline_from_old_high_pct": decline, "close": last.close, "change_pct": last.change_pct,
        "amount_multiple": amount_multiple, "single_price_day": last.high == last.low,
        "prior_20d_high": high_20, "prior_60d_high": high_60,
        "base_10_before_today": measure_base(bars[-11:-1]), "base_60": box_60, "base_120": box_120,
        "fits_60d_base": qualifies_60, "fits_120d_base": qualifies_120,
        "above_prior_20d_high": last.close > high_20, "above_prior_60d_high": last.close > high_60,
    }


def screen_symbol(code, asof):
    try:
        return screen_history(fetch_history(code, asof), asof)
    except (OSError, KeyError, TypeError, ValueError) as error:
        return {"code": code, "status": "data_unavailable", "reason": str(error)}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("asof", type=date.fromisoformat, help="Completed A-share trading date")
    parser.add_argument("--code", action="append", default=[], help="Restrict scan to these A-share codes")
    args = parser.parse_args()
    now = datetime.now(CHINA)
    if args.asof > now.date() or args.asof == now.date() and now.time() < time(15, 10):
        parser.error("Use a completed A-share trading date")
    codes = list(dict.fromkeys(args.code or COHORT))
    if not all(is_a_share(market_symbol(code)) for code in codes):
        parser.error("Expected six-digit Shanghai or Shenzhen A-share codes")

    asof = args.asof.isoformat()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda code: screen_symbol(code, asof), codes))
    print(json.dumps({"asof": asof, "requested": len(codes), "source": KLINE,
                      "price_basis": "forward_adjusted", "rows": results}, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
