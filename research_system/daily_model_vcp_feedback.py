"""Review frozen VCP report windows against reconciled minute prices."""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
from urllib.request import Request, urlopen

from market_screen.history import TZ, write_json
from market_screen.noon_repair import sina_minute_rows, sina_minute_url
from market_screen.quotes import HEADERS
from .daily_model import load_calendar
from .daily_model_data import checked, load_bars
from .daily_model_report_feedback import READER as REPORT_READER, close_time, load_state
from .ledger import stamp


DATA = Path("output/research/daily_model/vcp_feedback")
STATE = DATA / "minute_evidence.json"
SOURCES = DATA / "sources"
READER = Path("output/research/latest/daily_model_vcp_feedback.json")
MINUTE = timedelta(minutes=1)
CLOSE_DELAY = 5 * MINUTE
RETRY_AFTER = timedelta(minutes=30)
SOURCE_ERRORS = (OSError, ValueError, KeyError, TypeError, EOFError)
PRICES = ("open", "high", "low", "close")


def market_time(day, clock):
    return stamp(f"{day}T{clock}:00+08:00")


def minute_day(rows, day, daily):
    """Require continuous-session bars and the closing auction, in shares."""
    morning = market_time(day, "09:31")
    afternoon = market_time(day, "13:01")
    close = market_time(day, "15:00")
    expected = {morning + i * MINUTE for i in range(120)}
    expected.update(afternoon + i * MINUTE for i in range(117))
    expected.add(close)
    bars = {}
    for row in rows:
        if row["day"][:10] != day:
            continue
        end = datetime.fromisoformat(row["day"])
        end = end.replace(tzinfo=TZ) if end.tzinfo is None else end.astimezone(TZ)
        if end not in expected or end in bars:
            raise ValueError("unexpected_or_duplicate_minute")
        items = {k: row[k] for k in (*PRICES, "volume")}
        if any(isinstance(v, bool) or not math.isfinite(float(v)) for v in items.values()):
            raise ValueError("minute_nonfinite_numeric")
        values = {k: float(v) for k, v in items.items()}
        if (not 0 < values["low"] <= min(values["open"], values["close"])
                <= max(values["open"], values["close"]) <= values["high"] or values["volume"] < 0):
            raise ValueError("minute_ohlcv_invalid")
        bars[end] = values
    if bars.keys() != expected:
        raise ValueError("complete_session_minutes_required")
    aggregate = {"open": bars[morning]["open"], "close": bars[close]["close"],
                 "high": max(b["high"] for b in bars.values()), "low": min(b["low"] for b in bars.values()),
                 "volume": sum(b["volume"] for b in bars.values())}
    if (daily["day"] != day or aggregate["volume"] <= 0 or aggregate["volume"] != daily["volume"]
            or any(abs(aggregate[key] - daily[key]) > .005 for key in PRICES)):
        raise ValueError("minute_data_does_not_reconcile_with_verified_daily_ohlcv")
    return sorted(bars.items())


def expected_days(call, calendar, start, end):
    if not stamp(call["issued_at"]) <= start < min(end, close_time(call)):
        return None
    lo = bisect_left(calendar, start.date().isoformat())
    hi = bisect_right(calendar, end.date().isoformat())
    return [day for day in calendar[lo:hi]
            if start < market_time(day, "15:00") and end > market_time(day, "09:30")]


def price_events(sessions, plan, start, end):
    first = {}
    closes = []
    for bars in sessions:
        quarter_volume = 0
        for moment, bar in bars:
            width = 6 * MINUTE if (moment.hour, moment.minute) == (9, 31) else (
                3 * MINUTE if moment.hour == 15 else MINUTE)
            quarter_volume += bar["volume"]
            if start <= moment - width and moment <= end and bar["volume"] > 0:
                for key in ("buy", "reduce"):
                    low, high = plan[key + "_low"], plan[key + "_high"]
                    if low is None:
                        continue
                    if bar["low"] <= high and bar["high"] >= low:
                        first.setdefault(key + "_range_overlap", {"at": moment.isoformat()})
                    prices = [bar[k] for k in PRICES if low <= bar[k] <= high]
                    if prices:
                        first.setdefault(key + "_band_price", {"at": moment.isoformat(), "ohlc_price": prices[0]})
                if plan["stop"] is not None and bar["low"] < plan["stop"]:
                    first.setdefault("minute_below_stop", {"at": moment.isoformat(), "low": bar["low"]})
            if moment.minute % 15 == 0:
                if start <= moment - 15 * MINUTE and moment <= end and quarter_volume > 0:
                    closes.append({"at": moment.isoformat(), "close": bar["close"]})
                quarter_volume = 0
    if plan["stop"] is not None:
        stop = next((bar for bar in closes if bar["close"] < plan["stop"]), None)
        if stop:
            first["completed_15m_close_below_stop"] = stop
    if touch := first.get("reduce_band_price"):
        following = next((bar for bar in closes if bar["at"] >= touch["at"]), None)
        if following:
            first["first_completed_15m_close_after_reduce_band"] = following
    return first


def check_conditions(plan, events, daily, missing_days):
    """Grade only the numerical clauses supplied when the plan was frozen."""
    structured = plan.get("vcp_checks")
    if not structured:
        return {"status": "price_evidence_only", "error": plan.get("vcp_checks_error")}
    result = {"status": "defined_conditions_checked"}
    if "daily_breakout" in structured:
        gate = structured["daily_breakout"]
        if daily is None:
            result["daily_breakout"] = {"state": "awaiting_evidence", **gate}
        else:
            met = daily["close"] > gate["pivot"] and daily["volume"] >= gate["min_volume_shares"]
            result["daily_breakout"] = {"state": "met" if met else "not_met",
                                        "close": daily["close"], "volume": daily["volume"], **gate}
    if structured.get("stop_below_15m"):
        stop = events.get("completed_15m_close_below_stop")
        result["stop_below_15m"] = {"state": "observed" if stop else (
            "evidence_gap" if missing_days else "not_observed_in_reviewed_sessions"), "event": stop}
    if structured.get("reduce_after_band_below_15m"):
        touch = events.get("reduce_band_price")
        close = events.get("first_completed_15m_close_after_reduce_band")
        state = "evidence_gap" if missing_days else "not_observed_in_reviewed_sessions"
        if not missing_days and close and close["close"] < plan["reduce_low"]:
            state = "order_unverified_within_bar" if close["at"] == touch["at"] else "observed"
        result["reduce_after_band_below_15m"] = {"state": state, "touch": touch, "event": close}
    return result


def source_url(code):
    return sina_minute_url(("sh" if code.startswith("6") else "sz") + code)


def fetch_minutes(code):
    url = source_url(code)
    with urlopen(Request(url, headers=HEADERS), timeout=8) as response:
        raw = response.read(400_001)
    if len(raw) > 400_000:
        raise ValueError("minute_response_exceeds_expected_size")
    return raw, datetime.now(TZ)


def archive_source(root, raw):
    digest = hashlib.sha256(raw).hexdigest()
    path = root / SOURCES / (digest + ".json.gz")
    if path.exists():
        compressed = path.read_bytes()
        if gzip.decompress(compressed) != raw:
            raise ValueError("minute_archive_bytes_mismatch")
    else:
        compressed = gzip.compress(raw, mtime=0)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(compressed)
        temporary.replace(path)
    return {"file": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(compressed).hexdigest(),
            "raw_sha256": digest}


def read_minutes(root, evidence):
    raw = gzip.decompress(checked(root, evidence["source"], SOURCES))
    if hashlib.sha256(raw).hexdigest() != evidence["source"]["raw_sha256"]:
        raise ValueError("minute_raw_hash_mismatch")
    return minute_day(sina_minute_rows(raw), evidence["daily"]["day"], evidence["daily"])


def collect(root, catalog, requested, now, fetcher):
    if not requested:
        return
    history, daily_ref = load_bars(root, set(requested), now)
    due = {}
    for code, days in requested.items():
        available = [day for day in days if day in history.get(code, {})]
        if available:
            due[code] = available
    daily_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    for code, days in list(due.items())[:6]:
        try:
            raw, retrieved = fetcher(code)
            rows = sina_minute_rows(raw)
        except SOURCE_ERRORS as exc:
            for day in days:
                catalog["attempts"][f"{day}:{code}"] = {"at": now.isoformat(), "reason": str(exc)[:160]}
            continue
        for day in days:
            key = f"{day}:{code}"
            daily = history[code][day]
            try:
                if retrieved < market_time(day, "15:00") + CLOSE_DELAY:
                    raise ValueError("minute_response_observed_before_session_complete")
                minute_day(rows, day, daily)
                ref = archive_source(root, raw)
            except SOURCE_ERRORS as exc:
                catalog["attempts"][key] = {"at": now.isoformat(), "reason": str(exc)[:160]}
                continue
            catalog["sessions"][key] = {"code": code, "retrieved_at": retrieved.isoformat(), "source_url": source_url(code),
                                        "source": ref, "daily": daily, "daily_source": {**daily_ref, "commit": daily_commit}}
            catalog["attempts"].pop(key, None)


def review(root, row, catalog, now, cache):
    call, start, end, days = row
    code = call["code"]
    receipt = {"signal_id": call["signal_id"], "code": code, "phase": call["phase"],
               "issued_at": call["issued_at"], "seen_at": call["seen_at"], "check_day": call["check_day"],
               "valid_until": call["plan"]["valid_until"],
               "forecast_file": call["source"], "forecast_sha256": call["source_sha256"]}
    if days is None:
        return {**receipt, "status": "publication_window_unverified"}
    if not days:
        return {**receipt, "status": "no_trading_session_in_window"}
    observed, pending, gaps, refs = [], [], {}, []
    gate_daily = None
    for day in days:
        key = f"{day}:{code}"
        if market_time(day, "15:00") + CLOSE_DELAY > now:
            pending.append(day)
            continue
        if key not in cache:
            evidence = catalog["sessions"].get(key)
            try:
                if not evidence:
                    reason = catalog["attempts"].get(key, {}).get("reason", "awaiting_verified_minute_and_daily_evidence")
                    raise ValueError(reason)
                if evidence["code"] != code or evidence["daily"]["day"] != day:
                    raise ValueError("minute_receipt_identity_mismatch")
                if stamp(evidence["retrieved_at"]) > now:
                    raise ValueError("minute_evidence_not_yet_available")
                cache[key] = (read_minutes(root, evidence), evidence)
            except SOURCE_ERRORS as exc:
                cache[key] = str(exc)[:160]
        if isinstance(cache[key], str):
            gaps[day] = cache[key]
            continue
        bars, evidence = cache[key]
        observed.append(bars)
        if day == call["check_day"] and end >= market_time(day, "15:00"):
            gate_daily = evidence["daily"]
        refs.append({"day": day, "minute_source": evidence["source"], "minute_retrieved_at": evidence["retrieved_at"],
                     "daily_source": evidence["daily_source"]})
    status = "data_gap" if gaps else "waiting_for_close" if not observed and pending else (
        "window_open" if pending or now < end else "window_reviewed")
    events = price_events(observed, call["plan"], start, end)
    return {**receipt, "status": status, "observed_days": [ref["day"] for ref in refs],
            "pending_days": pending, "missing_days": gaps, "price_events": events, "sources": refs,
            "condition_checks": check_conditions(call["plan"], events, gate_daily, gaps),
            "entry_condition_state": "original_additional_conditions_require_review",
            "fill_state": "no_execution_evidence"}


def run(root, now=None, *, fetcher=fetch_minutes):
    root = Path(root).resolve()
    live_clock = now is None
    now = stamp(now.isoformat()) if now is not None else datetime.now(TZ)
    calendar = load_calendar(root, now)
    path = root / STATE
    catalog = json.loads(path.read_bytes()) if path.exists() else {"sessions": {}, "attempts": {}}
    today = now.date().isoformat()
    cutoff = market_time(today, "15:00") + CLOSE_DELAY
    completed_until = (bisect_left if now < cutoff else bisect_right)(calendar, today)
    recent = set(calendar[max(0, completed_until - 7):completed_until])
    requested = defaultdict(set)
    rows = []
    for call in load_state(root)["calls"].values():
        if "vcp" not in call["roles"]:
            continue
        start, end = stamp(call["seen_at"]), stamp(call["plan"]["valid_until"])
        days = expected_days(call, calendar, start, end)
        rows.append((call, start, end, days))
        for day in (set(days or ()) & recent):
            key = f"{day}:{call['code']}"
            last = catalog["attempts"].get(key)
            if key not in catalog["sessions"] and (not last or now - stamp(last["at"]) >= RETRY_AFTER):
                requested[call["code"]].add(day)
    collection_error = None
    active_codes = {call["code"] for call, _, end, days in rows if days and end >= now}
    selected = sorted(requested, key=lambda code: (code not in active_codes, code))
    try:
        collect(root, catalog, {code: sorted(requested[code]) for code in selected}, now, fetcher)
    except SOURCE_ERRORS as exc:
        collection_error = str(exc)[:160]
    if live_clock:
        now = datetime.now(TZ)
    cache = {}
    receipts = [review(root, row, catalog, now, cache) for row in rows]
    recent_calls = sorted(receipts, key=lambda row: (row["seen_at"], row["signal_id"]), reverse=True)[:12]
    summary = {"version": "vcp_minute_price_review_v1", "evaluated_at": now.isoformat(), "plans": len(receipts),
               "statuses": dict(Counter(row["status"] for row in receipts)),
               "verified_security_sessions": len(catalog["sessions"]), "collection_error": collection_error,
               "price_evidence_only": True, "trade_execution_labels": 0, "formal_training_rows": 0,
               "recent_calls": recent_calls}
    write_json(path, catalog)
    write_json(root / READER, summary)
    report_reader = root / REPORT_READER
    if report_reader.exists():
        report = json.loads(report_reader.read_bytes())
        report["vcp_minute_feedback"] = {**summary, "file": READER.as_posix()}
        write_json(report_reader, report)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    report = run(parser.parse_args().root)
    print(json.dumps({k: report[k] for k in ("plans", "statuses", "verified_security_sessions", "collection_error")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
