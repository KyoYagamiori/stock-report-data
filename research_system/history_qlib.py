"""Account-free immutable Qlib community release adapter, explicitly price-only."""
from __future__ import annotations

from datetime import date
from datetime import datetime
import gzip
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import struct
import tarfile
import time
from urllib.request import urlopen
from urllib.parse import urlencode

from .history_source import TZ, digest, read_capture, select_cohort, write

FIELDS = ("open", "high", "low", "close", "volume", "amount", "factor")
METADATA = ("calendars/day.txt", "calendars/day_future.txt", "instruments/all.txt",
            "instruments/csi300.txt", "instruments/csi500.txt", "instruments/csi800.txt",
            "instruments/csi1000.txt", "instruments/csiall.txt")


def file_digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def verify_archive(archive, manifest, config):
    if (manifest.get("release_tag") != config["release_tag"]
            or manifest.get("target_trade_date") != config["history_end"]
            or manifest.get("archive_sha256") != "sha256:" + config["release_archive_sha256"]
            or manifest.get("archive_size_bytes") != config["release_archive_bytes"]
            or manifest.get("dolt_commit") != config["release_dolt_commit"]
            or manifest.get("qlib_commit") != "b87a2c294d364a33fb739359886acffe8ec907d1"
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", manifest.get("image_digest") or "")):
        raise ValueError("public_release_manifest_identity_mismatch")
    if Path(archive).stat().st_size != config["release_archive_bytes"] or file_digest(archive) != config["release_archive_sha256"]:
        raise ValueError("public_release_archive_bytes_mismatch")


def safe_member(member, seen):
    name = member.name.rstrip("/")
    path = PurePosixPath(name)
    if (not name or name.startswith("/") or "\\" in name or ".." in path.parts
            or "." in path.parts or str(path) != name or path.parts[0] != "qlib_bin"
            or name in seen or not (member.isfile() or member.isdir())
            or member.size > 64 * 1024 * 1024 or getattr(member, "sparse", None)):
        raise ValueError("unsafe_public_release_member")
    seen.add(name)
    return name


def decode_binary(raw, calendar):
    if len(raw) < 8 or len(raw) % 4:
        raise ValueError("invalid_qlib_binary_length")
    values = struct.unpack("<" + "f" * (len(raw) // 4), raw)
    start = values[0]
    if not math.isfinite(start) or start != int(start) or start < 0 or start + len(values) - 1 > len(calendar):
        raise ValueError("invalid_qlib_calendar_offset")
    return dict(zip(calendar[int(start):int(start) + len(values) - 1], values[1:]))


def crosscheck_recent(root, manifest):
    """Small independent price/unit check; cannot certify the entire history."""
    root = Path(root)
    config, results = manifest["config"], []
    for code in manifest["selected_codes"][:3]:
        result = {"code": code, "compared_dates": 0, "price_mismatches": [], "volume_mismatches": 0}
        try:
            symbol = code.replace(".", "")
            query = urlencode({"param": symbol + ",day,2024-01-01," + config["history_end"] + ",640,"})
            url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + query
            with urlopen(url, timeout=15) as response:
                raw = response.read(2 * 1024 * 1024)
            payload = json.loads(raw)
            if payload.get("code") != 0:
                raise ValueError("crosscheck_quote_provider_error")
            observations = payload["data"][symbol]["day"]
            evidence_path = root / "output/history_pilot/crosscheck" / (digest(raw) + ".json.gz")
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_bytes(gzip.compress(raw, mtime=0))
            result.update(quote_file=evidence_path.relative_to(root).as_posix(), quote_sha256=digest(evidence_path.read_bytes()),
                          response_sha256=digest(raw), original_file=manifest["stocks"][code])
            original = {r["date"]: r for r in read_capture(root, manifest["stocks"][code])["rows"]}
            eligible = [r for r in observations if r[0] <= config["history_end"] and r[0] in original][-30:]
            for row in eligible:
                day = row[0]
                result["compared_dates"] += 1
                for column, position in (("open", 1), ("close", 2), ("high", 3), ("low", 4)):
                    if abs(original[day][column] - float(row[position])) > .0051:
                        result["price_mismatches"].append({"date": day, "field": column,
                            "release": original[day][column], "quote": row[position]})
                expected_volume = float(row[5]) * 100
                if abs(original[day]["volume"] - expected_volume) > max(2., expected_volume * .001):
                    result["volume_mismatches"] += 1
        except (ValueError, KeyError, OSError, TypeError) as exc:
            result["error"] = str(exc)[:200]
        results.append(result)
    mismatch = any(r["price_mismatches"] or r["volume_mismatches"] for r in results)
    complete = len(results) == 3 and all(not r.get("error") and r["compared_dates"] >= 15 for r in results)
    receipt = {"status": "mismatch" if mismatch else "passed_sample_crosscheck" if complete else "partial_unverified",
        "generated_at": datetime.now(TZ).isoformat(), "results": results,
        "scope": "recent_sample_price_and_volume_units_only_not_full_history_or_exchange_audit"}
    path = root / "output/research/latest/history_price_crosscheck.json"
    write(path, receipt)
    if mismatch:
        raise ValueError("public_history_independent_price_or_volume_mismatch")
    return {"status": receipt["status"], "file": path.relative_to(root).as_posix(), "sha256": file_digest(path)}


class QlibRelease:
    provider = "qlib_public_release"
    status_basis = "unavailable_st_price_only_research"

    def __init__(self, root, config):
        self.root, self.config = Path(root).resolve(), config
        date.fromisoformat(config["release_tag"])
        self.base_url = "https://github.com/chenditc/investment_data/releases/download/" + config["release_tag"] + "/"

    def __enter__(self):
        c = self.config
        cache = self.root / ".work/public_history" / c["release_tag"]
        cache.mkdir(parents=True, exist_ok=True)
        archive = Path(os.environ.get("STOCK_QLIB_ARCHIVE", cache / "qlib_bin.tar.gz"))
        manifest_path = archive.with_name("qlib_bin.manifest.json")
        if not manifest_path.exists():
            with urlopen(self.base_url + "qlib_bin.manifest.json", timeout=30) as response:
                manifest_path.write_bytes(response.read(16384))
        manifest = json.loads(manifest_path.read_bytes())
        if not archive.exists():
            target, started, count = archive.with_suffix(".part"), time.monotonic(), 0
            with urlopen(self.base_url + "qlib_bin.tar.gz", timeout=45) as response, target.open("wb") as stream:
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    stream.write(block)
                    count += len(block)
                    if count > c["release_archive_bytes"] or time.monotonic() - started > 300:
                        raise ValueError("public_release_download_budget_exceeded")
            target.replace(archive)
        verify_archive(archive, manifest, c)
        directory = self.root / "output/history_pilot/qlib_source" / c["release_tag"]
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "qlib_bin.manifest.json").write_bytes(manifest_path.read_bytes())
        blobs, seen = {}, set()
        with tarfile.open(archive, "r|gz") as tar:
            for member in tar:
                name = safe_member(member, seen)
                if len(seen) > 100000:
                    raise ValueError("public_archive_member_count_exceeded")
                relative = name.removeprefix("qlib_bin/")
                if relative in METADATA and member.isfile():
                    blobs[relative] = tar.extractfile(member).read()
        if set(blobs) != set(METADATA):
            raise ValueError("public_release_metadata_missing")
        self.calendar = blobs["calendars/day.txt"].decode().splitlines()
        future = blobs["calendars/day_future.txt"].decode().splitlines()
        if (self.calendar != sorted(set(self.calendar)) or self.calendar[-1] != c["history_end"]
                or future[:len(self.calendar)] != self.calendar or len(future) <= len(self.calendar)
                or future[len(self.calendar)] != manifest["future_start_date"] or future[-1] != manifest["future_end_date"]):
            raise ValueError("public_release_calendar_mismatch")
        for day in self.calendar + future:
            date.fromisoformat(day)
        self.intervals = []
        for line in blobs["instruments/all.txt"].decode().splitlines():
            symbol, first, last = line.split("\t")
            if not re.fullmatch(r"(SH|SZ|BJ)\d{6}", symbol) or not first <= last <= c["history_end"]:
                raise ValueError("public_release_instrument_interval_invalid")
            date.fromisoformat(first)
            date.fromisoformat(last)
            self.intervals.append((symbol, first, last))
        origin = c["cohort_date"]
        members = [{"code": s[:2].lower() + "." + s[2:]} for s in sorted({s for s, a, z in self.intervals if a <= origin <= z})]
        codes = select_cohort(members, c["sample_size"], c["seed"])
        symbols = {code.replace(".", "") for code in codes + [c["benchmark_code"]]}
        refs = {}
        for relative, raw in blobs.items():
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            refs[relative] = {"file": path.relative_to(self.root).as_posix(), "sha256": digest(raw)}
        self.binary = {}
        with tarfile.open(archive, "r|gz") as tar:
            for member in tar:
                parts = member.name.split("/")
                if (member.isfile() and len(parts) == 4 and parts[:2] == ["qlib_bin", "features"]
                        and parts[2] in symbols and parts[3] in {f + ".day.bin" for f in FIELDS}):
                    raw = tar.extractfile(member).read()
                    key = "/".join(parts[1:])
                    path = directory / key
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                    self.binary[(parts[2], parts[3].split(".")[0])] = raw
                    refs[key] = {"file": path.relative_to(self.root).as_posix(), "sha256": digest(raw)}
        missing = [(s, f) for s in symbols for f in FIELDS if (s, f) not in self.binary]
        if missing:
            raise ValueError("public_release_selected_field_missing:" + str(missing[:5]))
        receipt = {"archive_url": self.base_url + "qlib_bin.tar.gz", "archive_sha256": c["release_archive_sha256"],
                   "archive_size_bytes": c["release_archive_bytes"], "manifest_sha256": digest(manifest_path.read_bytes()),
                   "source_manifest": manifest, "captured_members": refs,
                   "normalization_source": "microsoft/qlib@b87a2c294d364a33fb739359886acffe8ec907d1:scripts/data_collector/yahoo/collector.py",
                   "price_reconstruction": "normalized_price/factor; volume*factor*100; amount*1000",
                   "status_fields": "ST unavailable; positive-volume observations are not an exchange halt audit"}
        receipt_path = directory / "extraction_receipt.json"
        write(receipt_path, receipt)
        self.provenance = {"release_tag": c["release_tag"], "archive_sha256": c["release_archive_sha256"],
                           "extraction_receipt_file": receipt_path.relative_to(self.root).as_posix(),
                           "extraction_receipt_sha256": file_digest(receipt_path)}
        print({"public_archive_verified": True, "members": len(seen), "selected_codes": len(codes)}, flush=True)
        return self

    def __exit__(self, *args):
        return False

    def query(self, request):
        method, kwargs = request["method"], request["kwargs"]
        if method == "query_all_stock":
            day = kwargs["day"]
            return [{"code": s[:2].lower() + "." + s[2:]} for s in sorted({s for s, a, z in self.intervals if a <= day <= z})]
        if method == "query_trade_dates":
            return [{"calendar_date": d, "is_trading_day": "1"} for d in self.calendar if kwargs["start_date"] <= d <= kwargs["end_date"]]
        if method != "query_history_k_data_plus" or kwargs["adjustflag"] != "3" or kwargs["frequency"] != "d":
            raise ValueError("unsupported_public_release_query")
        code, rows, previous = kwargs["code"], [], None
        symbol = code.replace(".", "")
        columns = {f: decode_binary(self.binary[(symbol, f)], self.calendar) for f in FIELDS}
        for day in self.calendar:
            values = {f: columns[f].get(day, math.nan) for f in FIELDS}
            if any(not math.isfinite(v) for v in values.values()) or any(values[f] <= 0 for f in ("open", "high", "low", "close", "factor")):
                continue
            factor = values["factor"]
            # Qlib stores float32; recover the A-share cent tick before OHLC checks.
            prices = {f: round(values[f] / factor, 2) for f in ("open", "high", "low", "close")}
            row = {"date": day, "code": code, **prices, "volume": max(0., values["volume"] * factor * 100),
                   "amount": max(0., values["amount"] * 1000), "adjustflag": "3",
                   "tradestatus": "1" if values["volume"] > 0 else "0", "isST": "unknown",
                   "preclose": previous["close"] * previous["factor"] / factor if previous else prices["close"],
                   "preclose_basis": "derived_release_factor_chain_not_exchange_quote"}
            previous = {"close": prices["close"], "factor": factor}
            if kwargs["start_date"] <= day <= kwargs["end_date"]:
                rows.append(row)
        if not rows:
            raise ValueError("public_release_history_empty:" + code)
        return rows
