"""Deterministic completed-day indicators and transparent BOLL-first triage."""
from __future__ import annotations

from datetime import date
import math
import statistics

PARAMETERS = {
    "history_bars": 160, "adjustment": "unadjusted",
    "boll": {"n": 20, "stddev": 2, "ddof": 0},
    "kdj": {"n": 9, "k": 3, "d": 3, "seed": 50},
    "macd": {"fast": 12, "slow": 26, "signal": 9, "histogram_multiplier": 2},
}


def normalize_bars(rows, target_date):
    """Reject malformed history before sorting; never turn live bars into closes."""
    date.fromisoformat(target_date)
    result, seen = [], set()
    for source in rows:
        if not isinstance(source, dict):
            raise ValueError("daily_bar_is_not_an_object")
        day = str(source.get("day", source.get("date", "")))[:10]
        date.fromisoformat(day)
        if day > target_date:
            continue
        if day in seen:
            raise ValueError("duplicate_daily_date:" + day)
        seen.add(day)
        row = {"day": day}
        for field in ("open", "high", "low", "close", "volume"):
            number = float(source[field])
            if not math.isfinite(number) or (number < 0 if field == "volume" else number <= 0):
                raise ValueError("invalid_" + field)
            row[field] = number
        if not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
            raise ValueError("invalid_ohlc_bounds")
        if source.get("amount") is not None:
            amount = float(source["amount"])
            if not math.isfinite(amount) or amount < 0:
                raise ValueError("invalid_amount")
            row["amount"] = amount
        result.append(row)
    result.sort(key=lambda row: row["day"])
    if not result:
        raise ValueError("empty_completed_history")
    return result[-180:]


def calculate(rows, target_date):
    bars = normalize_bars(rows, target_date)[-160:]
    prices = [row["close"] for row in bars]
    series = []
    k = d = 50.0
    ema12 = ema26 = prices[0]
    dea = 0.0
    for i, row in enumerate(bars):
        nine = bars[max(0, i - 8):i + 1]
        high, low = max(x["high"] for x in nine), min(x["low"] for x in nine)
        rsv = (row["close"] - low) / (high - low) * 100 if i >= 8 and high > low else 50.0
        k = (2 * k + rsv) / 3
        d = (2 * d + k) / 3
        if i:
            ema12 += (row["close"] - ema12) * 2 / 13
            ema26 += (row["close"] - ema26) * 2 / 27
        dif = ema12 - ema26
        dea += (dif - dea) * 2 / 10
        item = {"k": k, "d": d, "j": 3 * k - 2 * d,
                "dif": dif, "dea": dea, "hist2": 2 * (dif - dea)}
        if i >= 19:
            window = prices[i - 19:i + 1]
            mid, sigma = statistics.mean(window), statistics.pstdev(window)
            item.update(mid=mid, upper=mid + 2 * sigma, lower=mid - 2 * sigma,
                        width=4 * sigma / mid)
        series.append(item)
    latest, previous = series[-1], series[-2] if len(series) > 1 else {}
    out = {"bar_date": bars[-1]["day"], "history_current": bars[-1]["day"] == target_date,
           "bar_count": len(bars), "parameters": PARAMETERS, "price": prices[-1],
           "last_bar": bars[-1], "previous_bar": bars[-2] if len(bars) > 1 else None,
           "kdj": {key: latest[key] for key in ("k", "d", "j")},
           "macd": {key: latest[key] for key in ("dif", "dea", "hist2")},
           "previous": previous, "analysis_reviewed": False}
    if "mid" not in latest:
        out.update(boll=None, patterns=[])
        return out
    out["boll"] = {key: latest[key] for key in ("lower", "mid", "upper", "width")}
    old = series[-6] if len(series) >= 25 else previous
    prev_widths = [x["width"] for x in series[max(0, len(series) - 65):-1] if "width" in x]
    recent_widths = [x["width"] for x in series[-6:-1] if "width" in x]
    median_width = statistics.median(prev_widths) if prev_widths else latest["width"]
    q25_width = sorted(prev_widths)[int((len(prev_widths) - 1) * .25)] if prev_widths else latest["width"]
    prev_mid = previous.get("mid", latest["mid"])
    band_span = latest["upper"] - latest["lower"]
    position = (prices[-1] - latest["lower"]) / band_span if band_span > 0 else .5
    rails_up = all(latest[key] > previous.get(key, latest[key]) for key in ("lower", "mid", "upper"))
    mid_up = latest["mid"] > prev_mid and latest["mid"] >= old.get("mid", latest["mid"])
    opening_up = mid_up and latest["upper"] > previous.get("upper", latest["upper"]) and latest["width"] > previous.get("width", latest["width"])
    recent_squeeze = bool(recent_widths and min(recent_widths) <= q25_width and median_width > 0)
    below_twice = len(series) >= 21 and prices[-1] < latest["mid"] and prices[-2] < prev_mid
    patterns = []
    if mid_up and rails_up and bars[-1]["low"] <= latest["mid"] * 1.02 and prices[-1] >= latest["mid"]:
        patterns.append("uptrend_middle_band_pullback")
    if recent_squeeze and opening_up and prices[-1] >= latest["mid"] and position >= .65:
        patterns.append("squeeze_upward_opening")
    if mid_up and rails_up and .75 <= position <= 1.08:
        patterns.append("rising_upper_band_trend")
    proxy_values = [x["close"] * x["volume"] for x in bars[-20:]]
    volume_ratio = bars[-1]["volume"] / bars[-2]["volume"] if len(bars) > 1 and bars[-2]["volume"] > 0 else None
    out.update(
        patterns=patterns, rails_up=rails_up, mid_up=mid_up, opening_up=opening_up,
        recent_squeeze=recent_squeeze, below_mid_last_two=below_twice, band_position=position,
        mid_change_5d_pct=(latest["mid"] / old.get("mid", latest["mid"]) - 1) * 100,
        width_previous=previous.get("width"), width_prior_60d_q25=q25_width,
        volume_vs_previous_complete_day=volume_ratio,
        volume_vs_previous20_median=bars[-1]["volume"] / statistics.median([x["volume"] for x in bars[-21:-1]]) if len(bars) >= 21 and statistics.median([x["volume"] for x in bars[-21:-1]]) > 0 else None,
        estimated_turnover_20d_median=statistics.median(proxy_values),
        turnover_proxy_note="close * volume, CNY estimate; not exchange-reported turnover",
        return_1d_pct=(prices[-1] / prices[-2] - 1) * 100 if len(prices) > 1 else None,
        return_20d_pct=(prices[-1] / prices[-21] - 1) * 100 if len(prices) > 20 else None,
        distance_to_mid_pct=(prices[-1] / latest["mid"] - 1) * 100,
        distance_to_upper_pct=(prices[-1] / latest["upper"] - 1) * 100,
    )
    return out


def rank_candidate(stock, indicators, config):
    """An explicit heuristic for the research queue, never a win-rate estimate."""
    reasons = []
    name = str(stock.get("name", "")).upper().replace(" ", "")
    if "ST" in name or "退" in name:
        reasons.append("risk_warning_name")
    if not indicators.get("history_current"):
        reasons.append("history_not_current")
    if indicators.get("bar_count", 0) < config["minimum_history_bars"]:
        reasons.append("insufficient_history")
    if not indicators.get("patterns"):
        reasons.append("no_boll_setup")
    if indicators.get("below_mid_last_two"):
        reasons.append("below_middle_two_completed_sessions")
    if indicators.get("distance_to_upper_pct", 99) > config["maximum_extension_above_upper_pct"]:
        reasons.append("extended_above_upper_band")
    if indicators.get("estimated_turnover_20d_median", 0) < config["minimum_estimated_turnover_20d_median_cny"]:
        reasons.append("low_liquidity_proxy")
    last = indicators["last_bar"]
    if last["volume"] <= 0:
        reasons.append("no_target_day_volume")
    if abs(last["high"] - last["low"]) < 1e-8:
        reasons.append("one_price_bar")
    if reasons:
        return {"eligible": False, "reasons": reasons, "score": None}
    patterns = indicators["patterns"]
    boll = 30.0
    boll += 15 if "uptrend_middle_band_pullback" in patterns else 0
    boll += 15 if "squeeze_upward_opening" in patterns else 0
    boll += 10 if "rising_upper_band_trend" in patterns else 0
    boll += 5 if indicators["rails_up"] else 0
    boll = min(boll, 70)
    vr = indicators.get("volume_vs_previous20_median")
    volume = 10 if vr is not None and 1.0 <= vr <= 2.5 else 6 if vr is not None and .6 <= vr <= 3.5 else 2
    liquidity = min(10, 5 + max(0, math.log10(max(1, indicators["estimated_turnover_20d_median"] / 5e7))) * 3)
    auxiliary = 0.0
    kdj, macd, prior = indicators["kdj"], indicators["macd"], indicators["previous"]
    if kdj["k"] >= kdj["d"]: auxiliary += 2
    if kdj["j"] > prior.get("j", kdj["j"]): auxiliary += 2
    if macd["hist2"] > 0: auxiliary += 3
    if macd["hist2"] > prior.get("hist2", macd["hist2"]): auxiliary += 3
    penalty = 0
    if indicators.get("return_20d_pct", 0) > 40: penalty += 8
    if kdj["j"] > 110: penalty += 3
    return {"eligible": True, "reasons": patterns, "score": round(max(0, boll + volume + liquidity + auxiliary - penalty), 3),
            "components": {"boll_max70": boll, "volume_max10": volume, "liquidity_max10": round(liquidity, 3),
                           "kdj_macd_max10": auxiliary, "extension_penalty": penalty},
            "score_meaning": "heuristic research priority; not backtested probability",
            "review_status": "company_filings_catalysts_valuation_review_required"}
