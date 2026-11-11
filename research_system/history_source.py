"""Bounded public-history acquisition; captured API rows are not original wire bytes."""
from __future__ import annotations

from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import re
import socket
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
FIELDS = "date,code,open,high,low,close,preclose,volume,amount,adjustflag,tradestatus,isST"
INDEX_FIELDS = "date,code,open,high,low,close,volume,amount"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(canonical(value) + b"\n")
    temp.replace(path)


def capture(root, request, rows, provider="baostock", provenance=None):
    payload = {"schema_version": "1.0", "provider": provider, "request": request,
               "acquired_at": datetime.now(TZ).isoformat(), "rows": rows,
               "evidence_kind": "captured_api_field_values_not_original_transport_bytes" if provider == "baostock" else "normalized_release_fields_bound_to_original_binary_members",
               "provenance": provenance}
    raw = canonical(payload)
    path = Path(root) / "output/history_pilot/raw" / (digest(raw) + ".json.gz")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(raw, mtime=0))
    return {"file": path.relative_to(root).as_posix(), "sha256": digest(path.read_bytes()),
            "payload_sha256": digest(raw), "rows": len(rows)}


def read_capture(root, reference):
    root = Path(root).resolve()
    path = (root / reference["file"]).resolve()
    if not path.is_relative_to(root / "output/history_pilot/raw"):
        raise ValueError("history_evidence_outside_allowed_directory")
    raw = path.read_bytes()
    if digest(raw) != reference["sha256"]:
        raise ValueError("history_compressed_evidence_hash_mismatch")
    payload = gzip.decompress(raw)
    if digest(payload) != reference["payload_sha256"]:
        raise ValueError("history_payload_hash_mismatch")
    result = json.loads(payload)
    if len(result["rows"]) != reference["rows"]:
        raise ValueError("history_evidence_row_count_mismatch")
    return result


def select_cohort(rows, size, seed):
    if not 2 <= size <= 128:
        raise ValueError("pilot_size_must_be_between_2_and_128")
    codes = [r["code"] for r in rows]
    if len(codes) != len(set(codes)):
        raise ValueError("duplicate_historical_membership_code")
    # Historical origin membership, not today's survivors, names or future returns.
    eligible = [c for c in codes if re.fullmatch(r"sh\.(600|601|603|605)\d{3}|sz\.(000|001|002|003)\d{3}", c)]
    if len(eligible) < size:
        raise ValueError("historical_membership_too_small")
    return sorted(eligible, key=lambda c: digest((seed + ":" + c).encode()))[:size]


class BaoStock:
    def __enter__(self):
        import baostock as bs
        self.bs = bs
        self.old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(12)
        result = bs.login()
        if result.error_code != "0":
            socket.setdefaulttimeout(self.old_timeout)
            raise RuntimeError("baostock_login:" + result.error_code + ":" + result.error_msg)
        return self

    def __exit__(self, *args):
        try:
            self.bs.logout()
        finally:
            socket.setdefaulttimeout(self.old_timeout)

    def query(self, request):
        method, kwargs = request["method"], request["kwargs"]
        if method not in {"query_all_stock", "query_trade_dates", "query_history_k_data_plus"}:
            raise ValueError("unsupported_public_history_request")
        result = getattr(self.bs, method)(**kwargs)
        rows = []
        if result.error_code != "0":
            raise RuntimeError(method + ":" + result.error_code + ":" + result.error_msg)
        while result.next():
            row = result.get_row_data()
            if len(row) != len(result.fields):
                raise ValueError("history_source_field_count_mismatch")
            rows.append(dict(zip(result.fields, row)))
        if result.error_code != "0":
            raise RuntimeError(method + ":" + result.error_code)
        if not rows:
            raise ValueError(method + ":empty_source_response")
        return rows


def collect(root, config, client):
    root = Path(root).resolve()
    start, end, origin = config["history_start"], config["history_end"], config["cohort_date"]
    if not start <= origin < end or end >= datetime.now(TZ).date().isoformat():
        raise ValueError("history_requires_fixed_completed_date_range")

    provider = getattr(client, "provider", "baostock")

    def acquire(method, **kwargs):
        request = {"method": method, "kwargs": kwargs}
        key = digest(canonical({"provider": provider, **request}))
        cache = root / "output/history_pilot/cache" / (key + ".json")
        if cache.exists():
            ref = json.loads(cache.read_bytes())
            if read_capture(root, ref)["request"] != request:
                raise ValueError("history_cache_request_identity_mismatch")
            return ref
        rows = client.query(request)
        ref = capture(root, request, rows, provider=provider, provenance=getattr(client, "provenance", None))
        write(cache, ref)
        return ref

    membership = acquire("query_all_stock", day=origin)
    codes = select_cohort(read_capture(root, membership)["rows"], config["sample_size"], config["seed"])
    calendar = acquire("query_trade_dates", start_date=start, end_date=end)
    benchmark = acquire("query_history_k_data_plus", code=config["benchmark_code"], fields=INDEX_FIELDS,
                        start_date=start, end_date=end, frequency="d", adjustflag="3")
    sources, failures = {}, {}
    for code in codes:
        try:
            sources[code] = acquire("query_history_k_data_plus", code=code, fields=FIELDS,
                                   start_date=start, end_date=end, frequency="d", adjustflag="3")
        except (OSError, ValueError, RuntimeError) as exc:
            failures[code] = str(exc)[:250]
        print(json.dumps({"history_code": code, "acquired": len(sources), "failed": len(failures)}), flush=True)
    result = {"schema_version": "1.0", "config": config, "config_sha256": digest(canonical(config)),
              "provider": provider, "status_basis": getattr(client, "status_basis", "provider_supplied"),
              "provenance": getattr(client, "provenance", None),
              "membership": membership, "calendar": calendar, "benchmark": benchmark,
              "selected_codes": codes, "stocks": sources, "source_failures": failures,
              "cohort_complete": not failures, "production_activation": False}
    write(root / "output/history_pilot/source_manifest.json", result)
    return result
