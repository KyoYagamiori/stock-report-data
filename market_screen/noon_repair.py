"""Recover only rejected noon quotes from complete, archived minute evidence."""
from __future__ import annotations

from datetime import datetime, time, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from .quotes import HEADERS, TIMEZONE, parse_sina_quotes, validate_quote

FIELDS = ("code", "date", "time", "status", "open", "prev_close", "close", "high", "low", "volume", "amount")


def evidence_path(root, reference):
    root = Path(root).resolve()
    marker = "output/boll/archive/"
    value = str(reference or "")
    if marker not in value:
        raise ValueError("quote_raw_evidence_missing")
    path = (root / value[value.index(marker):]).resolve()
    if not path.is_relative_to(root / "output/boll/archive"):
        raise ValueError("quote_raw_evidence_outside_archive")
    return path


def _number(value):
    if isinstance(value, bool):
        raise ValueError("minute_boolean_numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("minute_nonfinite_numeric")
    return number


def minute_quote(raw, provider, stock, target, reference=None):
    """Aggregate 09:30/09:31--11:30 bars; never sum an incomplete morning.

    Eastmoney interval volume is in lots (100 shares), interval amount in CNY.
    Sina interval volume is shares and amount is required, never estimated by
    close*volume. The aggregate amount/volume must lie inside its price range.
    """
    text = raw.decode("utf-8")
    previous = None
    if provider == "eastmoney":
        data = json.loads(text).get("data") or {}
        if str(data.get("code", "")) != stock["code"]:
            raise ValueError("minute_security_identity_mismatch")
        if data.get("market") is not None and str(data["market"]) != ("1" if stock["exchange"] == "SH" else "0"):
            raise ValueError("minute_exchange_identity_mismatch")
        rows = []
        for item in data.get("trends", []):
            fields = item.split(",")
            if len(fields) != 8:
                raise ValueError("minute_eight_fields_required")
            rows.append(dict(zip(("day", "open", "close", "high", "low", "volume", "amount", "average"), fields)))
        if data.get("preClose") is not None:
            previous = _number(data["preClose"])
        volume_scale = 100
    elif provider == "sina":
        match = re.search(r"\(\s*(\[.*\])\s*\)", text, re.S)
        if not match:
            raise ValueError("minute_sina_bar_array_missing")
        rows = json.loads(match.group(1))
        volume_scale = 1
    else:
        raise ValueError("unsupported_minute_provider")
    morning = {}
    for row in rows:
        if str(row.get("day", ""))[:10] != target:
            continue
        stamp = datetime.fromisoformat(row["day"])
        if stamp.tzinfo is not None:
            stamp = stamp.astimezone(TIMEZONE).replace(tzinfo=None)
        if not time(9, 30) <= stamp.time() <= time(11, 30):
            continue
        if stamp.second or stamp.microsecond or stamp in morning:
            raise ValueError("minute_duplicate_or_nonminute_time")
        values = {key: _number(row[key]) for key in ("open", "close", "high", "low", "volume", "amount")}
        if (min(values[key] for key in ("open", "close", "high", "low")) <= 0
                or min(values["volume"], values["amount"]) < 0
                or not values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]):
            raise ValueError("minute_numeric_or_ohlc_invalid")
        values["volume"] *= volume_scale
        morning[stamp] = values
    start = datetime.fromisoformat(target + "T09:31:00")
    expected = {start + timedelta(minutes=i) for i in range(120)}
    if not expected.issubset(morning):
        raise ValueError("complete_0931_to_1130_minutes_required")
    ordered = [morning[key] for key in sorted(morning)]
    if previous is None:
        if not reference or reference.get("code") != stock["code"] or reference.get("date") != target:
            raise ValueError("previous_close_evidence_missing")
        previous = _number(reference["prev_close"])
    if previous <= 0:
        raise ValueError("previous_close_evidence_invalid")
    volume, amount = sum(r["volume"] for r in ordered), sum(r["amount"] for r in ordered)
    low, high = min(r["low"] for r in ordered), max(r["high"] for r in ordered)
    if (volume == 0) != (amount == 0):
        raise ValueError("minute_aggregate_activity_inconsistent")
    if volume and not low - .011 <= amount / volume <= high + .011:
        raise ValueError("minute_volume_amount_units_inconsistent")
    return {"code": stock["code"], "name": stock["name"], "exchange": stock["exchange"], "symbol": ("sh" if stock["exchange"] == "SH" else "sz") + stock["code"],
            "date": target, "time": "11:30:00", "status": "valid" if volume else "no_trades",
            "open": ordered[0]["open"], "close": ordered[-1]["close"], "high": high, "low": low,
            "prev_close": previous, "volume": volume, "amount": amount,
            "minute_source": provider, "morning_minute_count": len(ordered),
            "volume_unit": "shares", "amount_unit": "CNY", "price_adjustment": "unadjusted"}


def verify_quote_evidence(root, quote, target, moment, *, cache=None):
    """Reparse raw bytes, including a recovered quote's previous-close source."""
    stamp = datetime.fromisoformat(quote["retrieved_at"])
    if stamp.tzinfo is None or stamp > moment:
        raise ValueError("quote_retrieval_time_invalid_or_future")
    if "future_timestamp" in validate_quote(quote, target, "noon", now=stamp):
        raise ValueError("quote_observation_later_than_actual_retrieval")
    path = evidence_path(root, quote.get("raw_file"))
    cache = cache if cache is not None else {}
    key = (str(path), quote.get("raw_sha256"))
    if key not in cache:
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != quote.get("raw_sha256"):
            raise ValueError("quote_raw_sha256_mismatch")
        cache[key] = raw
    raw = cache[key]
    provider = quote.get("minute_source")
    if provider:
        reference = quote.get("recovery", {}).get("original_quote")
        if reference:
            original_path = evidence_path(root, reference.get("raw_file"))
            original_raw = original_path.read_bytes()
            if hashlib.sha256(original_raw).hexdigest() != reference.get("raw_sha256"):
                raise ValueError("previous_close_source_sha256_mismatch")
            original = parse_sina_quotes(original_raw).get(quote["code"], {})
            if any(original.get(key) != reference.get(key) for key in ("code", "date", "prev_close")):
                raise ValueError("previous_close_source_fields_mismatch")
        parsed = minute_quote(raw, provider, quote, target, reference)
    else:
        parsed_key = ("parsed_sina", *key)
        if parsed_key not in cache:
            cache[parsed_key] = parse_sina_quotes(raw)
        parsed = cache[parsed_key].get(quote["code"], {})
    if any(parsed.get(key) != quote.get(key) for key in FIELDS):
        raise ValueError("quote_raw_fields_mismatch")
    return True


def recover_quote(stock, original, root, directory, target, *, timeout=8, moment=None):
    """Two providers at most, each once; callers supply only actual gap codes."""
    root, directory = Path(root).resolve(), Path(directory).resolve()
    if not directory.is_relative_to(root / "output/boll/archive"):
        raise ValueError("minute_output_outside_archive")
    prefix = "sh" if stock["exchange"] == "SH" else "sz"
    secid = ("1" if prefix == "sh" else "0") + "." + stock["code"]
    eastmoney = "https://push2his.eastmoney.com/api/qt/stock/trends2/get?" + urlencode({
        "secid": secid, "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58", "ndays": 5, "iscr": 0, "iscca": 0})
    sina = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/CN_MarketDataService.getKLineData?" + urlencode({
        "symbol": prefix + stock["code"], "scale": 1, "ma": "no", "datalen": 1970})
    attempts = []
    sources = directory / "quote_sources"
    sources.mkdir(parents=True, exist_ok=True)
    for provider, url in (("eastmoney", eastmoney), ("sina", sina)):
        attempt = {"code": stock["code"], "provider": provider, "source_url": url}
        try:
            with urlopen(Request(url, headers=HEADERS), timeout=timeout) as response:
                raw = response.read()
            stamp = moment or datetime.now(TIMEZONE)
            path = sources / (provider + "_minute_" + stock["code"] + "_" + uuid4().hex + ".raw")
            path.write_bytes(raw)
            attempt.update(raw_file=path.relative_to(root).as_posix(), raw_sha256=hashlib.sha256(raw).hexdigest(),
                           retrieved_at=stamp.isoformat(), bytes=len(raw))
            # A missing primary quote may still be repaired if the minute
            # provider supplies its own previous close.
            reference = original if original and original.get("raw_file") else None
            if reference:
                old_raw = evidence_path(root, reference["raw_file"]).read_bytes()
                if hashlib.sha256(old_raw).hexdigest() != reference.get("raw_sha256"):
                    raise ValueError("original_quote_sha256_mismatch")
                check = parse_sina_quotes(old_raw).get(stock["code"], {})
                if any(check.get(key) != reference.get(key) for key in ("code", "date", "prev_close")):
                    raise ValueError("original_previous_close_fields_mismatch")
            quote = minute_quote(raw, provider, stock, target, reference)
            quote.update(source_url=url, raw_file=attempt["raw_file"], raw_sha256=attempt["raw_sha256"], retrieved_at=stamp.isoformat(),
                         recovery={"method": "complete_morning_minute_aggregation", "original_quote": reference,
                                   "original_rejection": validate_quote(original or {}, target, "noon", now=stamp),
                                   "not_available_at_cutoff": stamp.time() >= time(12, 40),
                                   "note": "Actual historical 11:30 bars; retrieval/publication time remains actual. No later trades or estimated amount."})
            errors = validate_quote(quote, target, "noon", now=stamp)
            if errors not in ([], ["no_trades"]):
                raise ValueError("recovered_quote_invalid:" + ",".join(errors))
            attempts.append({**attempt, "accepted": True})
            return quote, attempts
        except Exception as exc:
            attempts.append({**attempt, "accepted": False, "error": type(exc).__name__ + ":" + str(exc)[:300]})
    return None, attempts
