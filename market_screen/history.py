"""Resumable unadjusted daily history with safe single-session quote updates."""
from __future__ import annotations

from datetime import date, datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .technicals import normalize_bars

TZ = ZoneInfo("Asia/Shanghai")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def canonical_bytes(rows):
    return json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def save_cache(path, code, bars, meta):
    payload = {"code": code, "adjustment": "unadjusted", "bars": bars,
               "history_sha256": hashlib.sha256(canonical_bytes(bars)).hexdigest(), "source": meta}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(gzip.compress(canonical_bytes(payload), mtime=0))
    tmp.replace(path)
    return payload


def load_cache(path, code, target_date):
    if not path.exists():
        return None
    try:
        payload = json.loads(gzip.decompress(path.read_bytes()))
        if not isinstance(payload, dict):
            return None
        if payload.get("code") != code or payload.get("adjustment") != "unadjusted":
            return None
        if hashlib.sha256(canonical_bytes(payload["bars"])).hexdigest() != payload.get("history_sha256"):
            return None
        rows = normalize_bars(payload["bars"], target_date)
        view_digest = hashlib.sha256(canonical_bytes(rows)).hexdigest()
        return {**payload, "bars": rows, "stored_history_sha256": payload["history_sha256"],
                "history_sha256": view_digest}
    except (ValueError, TypeError, KeyError, OSError, EOFError, AttributeError):
        return None


def import_evidence(import_root, cache_root, target_date):
    """Import existing raw evidence, recomputing hashes and never trusting scores."""
    imported = 0
    if not import_root:
        return imported
    for path in sorted((Path(import_root) / "raw").glob("*.json.gz")):
        code = path.name[:6]
        target = cache_root / (code + ".json.gz")
        if load_cache(target, code, target_date):
            continue
        try:
            rows = normalize_bars(json.loads(gzip.decompress(path.read_bytes())), target_date)
            record = json.loads((Path(import_root) / "records" / (code + ".json")).read_text())
            if record.get("adjustment") != "unadjusted" or record.get("fetch_status") != "success":
                continue
            save_cache(target, code, rows, {
                "method": "validated_existing_unadjusted_evidence",
                "source_url": record.get("source_url"), "retrieved_at": record.get("fetched_at"),
                "original_response_sha256": record.get("raw_response_sha256"),
                "imported_at": datetime.now(TZ).isoformat(),
            })
            imported += 1
        except (ValueError, KeyError, OSError, TypeError):
            continue
    return imported


def import_seed(seed_path, cache_root, target_date):
    if not seed_path or not Path(seed_path).exists():
        return 0
    seed_path = Path(seed_path)
    manifest_path = seed_path.parent / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("sha256") != hashlib.sha256(seed_path.read_bytes()).hexdigest():
            raise ValueError("bootstrap_file_hash_mismatch")
    count = 0
    with gzip.open(seed_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            code = payload["code"]
            path = cache_root / (code + ".json.gz")
            if load_cache(path, code, target_date):
                continue
            if payload.get("adjustment") != "unadjusted":
                raise ValueError("seed_adjustment_mismatch")
            if hashlib.sha256(canonical_bytes(payload["bars"])).hexdigest() != payload["history_sha256"]:
                raise ValueError("seed_history_hash_mismatch:" + code)
            bars = normalize_bars(payload["bars"], target_date)
            save_cache(path, code, bars, payload["source"])
            count += 1
    return count


def preserve_bootstrap(root, universe, market_date):
    """Keep a public, hash-verified restart point when cache coverage grows."""
    directory = root / "output/boll/bootstrap"
    manifest_path = directory / "manifest.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    cache = root / "output/boll/state/history"
    present = sum((cache / (stock["code"] + ".json.gz")).exists() for stock in universe)
    if ((directory / "history.jsonl.gz").exists() and present <= old.get("record_count", 0)
            and market_date <= old.get("market_date", "")):
        return old
    if present == 0:
        return None
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "history.jsonl.gz"
    temporary = directory / "history.jsonl.gz.tmp"
    count = current = 0
    with temporary.open("wb") as file:
        with gzip.GzipFile(fileobj=file, mode="wb", mtime=0) as packed:
            for stock in sorted(universe, key=lambda item: item["code"]):
                payload = load_cache(cache / (stock["code"] + ".json.gz"), stock["code"], market_date)
                if not payload:
                    continue
                packed.write(canonical_bytes(payload) + b"\n")
                count += 1
                current += payload["bars"][-1]["day"] == market_date
    temporary.replace(destination)
    meta = {"schema_version": "1.0", "market_date": market_date, "adjustment": "unadjusted",
            "record_count": count, "current_history_count": current, "universe_count": len(universe),
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "bytes": destination.stat().st_size,
            "note": "Restart history evidence, not company diligence or a coverage acceptance flag."}
    write_json(manifest_path, meta)
    return meta


def append_completed_quote(cached, quote, target_date, previous_session):
    """Only append the immediately next session with a compatible price basis."""
    from .quotes import validate_quote
    if (cached.get("code") != quote.get("code")
            or not previous_session or date.fromisoformat(previous_session) >= date.fromisoformat(target_date)
            or validate_quote(quote, target_date, "close")):
        return None
    bars = cached["bars"]
    if not bars or bars[-1]["day"] != previous_session:
        return None
    # A reset previous close may signal dividend/split mechanics. Fetch history
    # and flag it for corporate-action review instead of silently splicing it.
    if abs(bars[-1]["close"] - quote["prev_close"]) > .011:
        return None
    row = {"day": target_date, **{key: quote[key] for key in ("open", "high", "low", "close", "volume", "amount")}}
    return normalize_bars([*bars, row], target_date)


def fetch_history(stock, target_date, cache_root, *, previous_session=None, quote=None, timeout=12, retry_count=1):
    code = stock["code"]
    path = cache_root / (code + ".json.gz")
    cached = load_cache(path, code, target_date)
    if cached and cached["bars"][-1]["day"] == target_date:
        return {**cached, "fetch_status": "success", "update_method": "cache_hit"}
    action_gap = bool(cached and quote and quote.get("date") == target_date and quote.get("prev_close")
                      and cached["bars"][-1]["day"] == previous_session
                      and abs(cached["bars"][-1]["close"] - quote["prev_close"]) > .011)
    if cached and quote and previous_session:
        rows = append_completed_quote(cached, quote, target_date, previous_session)
        if rows:
            meta = {"method": "next_session_completed_quote_append", "prior_source": cached["source"],
                    "source_url": quote["source_url"], "retrieved_at": quote["retrieved_at"],
                    "original_response_sha256": quote["raw_sha256"], "previous_session": previous_session}
            # Keep provenance bounded instead of recursively growing every day.
            meta["prior_source"] = {key: cached["source"].get(key) for key in ("method", "source_url", "retrieved_at", "original_response_sha256")}
            result = save_cache(path, code, rows, meta)
            return {**result, "fetch_status": "success", "update_method": "quote_append"}
    symbol = ("sh" if stock["exchange"] == "SH" else "sz") + code
    url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/CN_MarketDataService.getKLineData?" + urlencode(
        {"symbol": symbol, "scale": 240, "ma": "no", "datalen": 180})
    errors = []
    for _ in range(retry_count + 1):
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"})
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
            match = re.search(rb"\(\s*(\[.*\])\s*\)", raw, re.S)
            if not match:
                raise ValueError("missing_history_array")
            rows = normalize_bars(json.loads(match.group(1)), target_date)
            meta = {"method": "sina_unadjusted_daily", "source_url": url,
                    "retrieved_at": datetime.now(TZ).isoformat(),
                    "original_response_sha256": hashlib.sha256(raw).hexdigest(),
                    "earlier_errors": errors, "corporate_action_basis_change": action_gap}
            result = save_cache(path, code, rows, meta)
            return {**result, "fetch_status": "success", "update_method": "history_fetch"}
        except Exception as exc:
            errors.append(type(exc).__name__ + ": " + str(exc)[:250])
    return {"code": code, "fetch_status": "failed", "errors": errors, "source_url": url,
            "bars": cached["bars"] if cached else [], "source": cached.get("source", {}) if cached else {},
            "update_method": "failed", "retrieved_at": datetime.now(TZ).isoformat()}
