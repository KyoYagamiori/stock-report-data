"""Bounded Sina quote collection with raw evidence and explicit time gates.

Quotes are cumulative, unadjusted observations.  In particular, ``volume`` is
shares traded up to the quoted timestamp; it is not a same-time volume ratio.
The structural ``status`` does not certify a target date or report phase.  Call
``validate_quote`` before using an observation in a screen or daily-bar overlay.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo


TIMEZONE = ZoneInfo("Asia/Shanghai")
SOURCE = "Sina hq.sinajs.cn"
BASE_URL = "https://hq.sinajs.cn/list="
BATCH_SIZE = 100
MAX_WORKERS = 6
MAX_ATTEMPTS = 2
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.sina.com.cn/",
}
_QUOTE_RE = re.compile(r'var\s+hq_str_((?:sh|sz)\d{6})\s*=\s*"([^"\r\n]*)"\s*;?')
_NUMERIC_KEYS = ("open", "prev_close", "close", "high", "low", "volume", "amount")


def _number(value: object) -> float | None:
    try:
        if isinstance(value, bool):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _quote_date(value: object) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _quote_time(value: object) -> time | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}:\d{2}", value):
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def _clock(value: object) -> datetime | None:
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=TIMEZONE)
        return stamp.astimezone(TIMEZONE)
    except (ValueError, TypeError, OverflowError):
        return None


def _base_quote(code: str, *, name: str = "", symbol: str | None = None) -> dict:
    return {
        "code": code,
        "name": name,
        **{key: None for key in _NUMERIC_KEYS},
        "date": None,
        "time": None,
        "source_url": BASE_URL + symbol if symbol else None,
        "raw_sha256": None,
        "retrieved_at": None,
        "status": "missing",
        "symbol": symbol,
    }


def _structural_errors(row: dict) -> list[str]:
    errors = []
    if not re.fullmatch(r"\d{6}", str(row.get("code", ""))):
        errors.append("invalid_code")
    if not row.get("name"):
        errors.append("missing_name")
    values = {key: _number(row.get(key)) for key in _NUMERIC_KEYS}
    if any(value is None for value in values.values()):
        errors.append("nonfinite_or_missing_numeric")
    elif any(value < 0 for value in values.values()):
        errors.append("negative_numeric")
    elif values["volume"] == 0 and values["amount"] == 0:
        # Zero activity is evidence of no trades, never proof of suspension.
        pass
    else:
        if values["volume"] <= 0 or values["amount"] <= 0:
            errors.append("inconsistent_activity")
        if any(values[key] <= 0 for key in ("open", "prev_close", "close", "high", "low")):
            errors.append("nonpositive_price")
        if (values["high"] < max(values["open"], values["close"], values["low"])
                or values["low"] > min(values["open"], values["close"], values["high"])):
            errors.append("invalid_ohlc_range")
    if _quote_date(row.get("date")) is None:
        errors.append("invalid_date")
    if _quote_time(row.get("time")) is None:
        errors.append("invalid_time")
    return errors


def parse_sina_quotes(raw: bytes) -> dict[str, dict]:
    """Parse Sina bytes into six-digit code keys without changing timestamps.

This pure helper computes the digest of the supplied bytes.  ``retrieved_at``
is left unset; only the collector knows when the response was actually read.
An explicit empty provider payload is retained with ``status='missing'``.
"""
    digest = hashlib.sha256(raw).hexdigest()
    result: dict[str, dict] = {}
    for symbol, payload in _QUOTE_RE.findall(raw.decode("gb18030", errors="replace")):
        code = symbol[2:]
        row = _base_quote(code, symbol=symbol)
        row["raw_sha256"] = digest
        fields = payload.split(",")
        row["field_count"] = len(fields) if payload else 0
        if not payload:
            row["parse_errors"] = ["provider_empty"]
        elif len(fields) < 32:
            row["status"] = "invalid"
            row["parse_errors"] = ["malformed_field_count"]
        else:
            row.update({
                "name": fields[0],
                "open": _number(fields[1]),
                "prev_close": _number(fields[2]),
                "close": _number(fields[3]),
                "high": _number(fields[4]),
                "low": _number(fields[5]),
                "volume": _number(fields[8]),
                "amount": _number(fields[9]),
                "date": fields[30],
                "time": fields[31],
                "provider_status": fields[32] if len(fields) > 32 else None,
            })
            row["parse_errors"] = _structural_errors(row)
            if row["parse_errors"]:
                row["status"] = "invalid"
            elif row["volume"] == 0 and row["amount"] == 0:
                row["status"] = "no_trades"
                row["trade_state_note"] = "Zero activity does not establish suspension."
            else:
                row["status"] = "valid"
        if code in result:
            # Do not silently choose between duplicate or conflicting symbols.
            row["status"] = "invalid"
            row["parse_errors"] = list(row.get("parse_errors", [])) + ["duplicate_code"]
        result[code] = row
    return result


def validate_quote(
    row: dict, target_date: str | date, phase: str, *, now: datetime | str | None = None,
) -> list[str]:
    """Return rejection reasons for an exact-date phase observation.

``close`` requires a timestamp at or after 15:00.  ``noon`` accepts only
11:29:00--11:30:59.  ``intraday`` requires a continuous trading session and a
non-future timestamp.  Its reference clock is explicit ``now`` or the actual
``retrieved_at`` on the row; absent both it fails with ``clock_unavailable``.
This helper never reads the system clock or rewrites provider dates/times.
"""
    if phase not in {"close", "noon", "intraday"}:
        raise ValueError(f"Unsupported quote phase: {phase}")
    if isinstance(target_date, datetime):
        target = target_date.date()
    elif isinstance(target_date, date):
        target = target_date
    else:
        target = _quote_date(target_date)
    if target is None:
        raise ValueError("target_date must be an ISO calendar date")
    status = row.get("status")
    if status == "missing":
        return ["missing"]
    reasons = []
    if status == "no_trades":
        reasons.append("no_trades")
    elif status != "valid":
        reasons.append("invalid")
    reasons.extend(_structural_errors(row))
    observation_date = _quote_date(row.get("date"))
    observation_time = _quote_time(row.get("time"))
    if observation_date is not None and observation_date != target:
        reasons.append("date_mismatch")
    if observation_time is not None:
        if phase == "close" and observation_time < time(15):
            reasons.append("not_close")
        elif phase == "noon" and not time(11, 29) <= observation_time <= time(11, 30, 59):
            reasons.append("not_noon")
        elif phase == "intraday" and not (
            time(9, 30) <= observation_time <= time(11, 30, 59)
            or time(13) <= observation_time <= time(15, 0, 59)
        ):
            reasons.append("outside_trading_session")
    reference_value = now if now is not None else row.get("retrieved_at")
    if reference_value is None:
        if phase == "intraday":
            reasons.append("clock_unavailable")
    else:
        reference = _clock(reference_value)
        if reference is None:
            reasons.append("invalid_clock")
        elif observation_date is not None and observation_time is not None:
            observation = datetime.combine(observation_date, observation_time, tzinfo=TIMEZONE)
            if observation > reference:
                reasons.append("future_timestamp")
    return list(dict.fromkeys(reasons))


def _identity(record: dict) -> tuple[str, str]:
    code = str(record.get("code", "")).strip()
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError(f"Universe code is not six digits: {code!r}")
    exchange = str(record.get("exchange", "")).upper()
    if exchange in {"SH", "SSE", "XSHG"}:
        prefix = "sh"
    elif exchange in {"SZ", "SZSE", "XSHE"}:
        prefix = "sz"
    elif not exchange and code.startswith(("6", "0", "3")):
        prefix = "sh" if code.startswith("6") else "sz"
    else:
        raise ValueError(f"Unsupported沪深 exchange for {code}: {exchange!r}")
    return code, prefix + code


def fetch_quotes(
    universe: list[dict], output: Path, *, timeout: float = 12, workers: int = 6,
) -> tuple[dict[str, dict], dict]:
    """Fetch all requested codes in batches of 100 with at most one retry.

Every input code is present in the returned mapping, including failed batches
and explicit empty quotes.  Duplicate or malformed universe identifiers fail
before fetching rather than being silently dropped.  Each received response,
including HTTP-error bodies, is preserved byte-for-byte with its actual hash.
"""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive finite number")
    if not isinstance(workers, int) or isinstance(workers, bool) or workers < 1:
        raise ValueError("workers must be a positive integer")
    workers = min(workers, MAX_WORKERS)
    identified = [(*_identity(record), record) for record in universe]
    codes = [item[0] for item in identified]
    if len(set(codes)) != len(codes):
        raise ValueError("Universe contains duplicate codes")
    sources = Path(output) / "quote_sources"
    sources.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(TIMEZONE).isoformat()
    run_key = datetime.now(TIMEZONE).strftime("%Y%m%dT%H%M%S%f") + "_" + uuid4().hex[:8]
    batches = [identified[start:start + BATCH_SIZE] for start in range(0, len(identified), BATCH_SIZE)]

    def collect(index: int, batch: list[tuple]) -> tuple[int, dict, dict]:
        url = BASE_URL + ",".join(item[1] for item in batch)
        expected_symbols = {item[1] for item in batch}
        attempts, parsed, latest_evidence = [], {}, {}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            raw, error, http_status = None, None, None
            try:
                with urlopen(Request(url, headers=HEADERS), timeout=timeout) as response:
                    raw = response.read()
                    http_status = getattr(response, "status", None)
            except HTTPError as exc:
                http_status = exc.code
                try:
                    raw = exc.read()
                except OSError:
                    raw = None
                error = f"HTTPError: {exc.code} {exc.reason}"
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            retrieved_at = datetime.now(TIMEZONE).isoformat()
            evidence = {"attempt": attempt, "source_url": url, "retrieved_at": retrieved_at,
                        "http_status": http_status, "raw_file": None,
                        "raw_sha256": None, "bytes": None, "error": error}
            if raw is not None:
                raw_path = sources / f"sina_{run_key}_batch_{index:04d}_attempt_{attempt}.raw"
                raw_path.write_bytes(raw)
                evidence.update({"raw_file": str(raw_path), "bytes": len(raw),
                                 "raw_sha256": hashlib.sha256(raw).hexdigest()})
            if error is None:
                if not raw:
                    error = "empty_response"
                else:
                    candidate = parse_sina_quotes(raw)
                    parsed = {code: row for code, row in candidate.items()
                              if row.get("symbol") in expected_symbols}
                    if not parsed:
                        error = "no_requested_quotes_in_response"
                evidence["error"] = error
            attempts.append(evidence)
            latest_evidence = evidence
            (sources / f"sina_{run_key}_batch_{index:04d}_attempt_{attempt}.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            if error is None:
                break
        rows = {}
        batch_failed = bool(latest_evidence.get("error"))
        for code, symbol, record in batch:
            row = dict(parsed.get(code, _base_quote(code, name=record.get("name", ""), symbol=symbol)))
            if batch_failed:
                row["status"] = "missing"
                row["fetch_error"] = latest_evidence["error"]
            elif code not in parsed:
                row["fetch_error"] = "symbol_absent_from_response"
            if not row.get("name"):
                row["name"] = record.get("name", "")
            row.update({key: latest_evidence[key] for key in
                        ("source_url", "retrieved_at", "raw_file", "raw_sha256")})
            rows[code] = row
        return index, rows, {"batch": index, "requested_count": len(batch),
                             "returned_count": len(parsed), "failed": batch_failed,
                             "source_url": url, "attempts": attempts}

    result, batch_metadata = {}, []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(collect, index, batch) for index, batch in enumerate(batches)]
        for future in as_completed(futures):
            _, rows, metadata = future.result()
            result.update(rows)
            batch_metadata.append(metadata)
    result = {code: result[code] for code in codes}
    batch_metadata.sort(key=lambda item: item["batch"])
    status_counts = Counter(row["status"] for row in result.values())
    errors = [{"batch": item["batch"], "attempt": attempt["attempt"], "error": attempt["error"]}
              for item in batch_metadata for attempt in item["attempts"] if attempt["error"]]
    metadata = {
        "source": SOURCE, "started_at": started_at,
        "completed_at": datetime.now(TIMEZONE).isoformat(),
        "requested_count": len(codes), "returned_count": len(result),
        "status_counts": {status: status_counts[status] for status in
                          ("valid", "no_trades", "invalid", "missing")},
        "batch_size": BATCH_SIZE, "batch_count": len(batches), "workers": workers,
        "timeout_seconds": timeout, "max_attempts": MAX_ATTEMPTS,
        "failed_batches": sum(item["failed"] for item in batch_metadata),
        "errors": errors, "batches": batch_metadata,
        "units": {"volume": "shares", "amount": "CNY", "price": "CNY per share, unadjusted"},
        "time_policy": "Provider date/time retained; validate exact target date and report phase separately.",
        "activity_policy": "Cumulative quote volume; no same-time volume strength or suspension inference.",
    }
    return result, metadata
