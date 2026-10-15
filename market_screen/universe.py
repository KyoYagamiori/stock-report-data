"""Official Shanghai/Shenzhen ordinary A-share universe with auditable fallbacks.

The live exchange lists define membership, including ST and suspended listings.
Trading eligibility belongs to the later screening stage. A cached/seed list is
usable for collection, but is always labelled unrefreshed in the provenance.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from email.utils import parsedate_to_datetime
import hashlib
import html
import io
import json
import math
from pathlib import Path
import re
from typing import Any
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = 1
SSE_ENDPOINT = "https://query.sse.com.cn/sseQuery/commonQuery.do"
SZSE_JSON_URL = (
    "https://www.szse.cn/api/report/ShowReport/data?"
    "SHOWTYPE=JSON&CATALOGID=1110&TABKEY=tab1&PAGENO=1"
)
SZSE_XLSX_URL = (
    "https://www.szse.cn/api/report/ShowReport?"
    "SHOWTYPE=xlsx&CATALOGID=1110&TABKEY=tab1"
)
CODE_PATTERNS = {
    "SH": re.compile(r"(?:600|601|603|605|688)\d{3}\Z"),
    "SZ": re.compile(r"(?:000|001|002|003|300|301|302)\d{3}\Z"),
}


def _sse_url(stock_type: str) -> str:
    return SSE_ENDPOINT + "?" + urllib.parse.urlencode({
        "STOCK_TYPE": stock_type, "REG_PROVINCE": "", "CSRC_CODE": "",
        "STOCK_CODE": "", "sqlId": "COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L",
        "COMPANY_STATUS": "2,4,5,7,8", "type": "inParams",
        "isPagination": "true", "pageHelp.cacheSize": 1,
        "pageHelp.beginPage": 1, "pageHelp.pageSize": 10000,
        "pageHelp.pageNo": 1, "pageHelp.endPage": 1,
    })


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _version_date(value: Any) -> str | None:
    """Return a source-supplied date, never fill one in from the request date."""
    if value in (None, "", "-"):
        return None
    value = str(value).strip()
    if re.fullmatch(r"\d{8}", value):
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:\s|T|$)", value)
    if not match:
        raise ValueError(f"invalid source date: {value!r}")
    return date.fromisoformat(match.group(1)).isoformat()


def _count(value: Any, field: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        raise ValueError(f"invalid {field}: {value!r}")
    count = int(value)
    if count < (0 if allow_zero else 1):
        raise ValueError(f"invalid {field}: {value!r}")
    return count


def validate_universe(records: list[dict], expected_total: int | None = None) -> dict:
    """Raise ValueError on duplicate/non-ordinary codes or malformed membership.

    Return count evidence for the validated normalized list. This intentionally
    does not filter ST, suspended, new or loss-making ordinary A shares.
    """
    if not isinstance(records, list) or not records:
        raise ValueError("ordinary A-share universe is empty or not a list")
    seen: set[str] = set()
    exchange_counts = {"SH": 0, "SZ": 0}
    board_counts: dict[str, int] = {}
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            raise ValueError(f"universe row {index} is not an object")
        code, exchange = row.get("code"), row.get("exchange")
        if (not isinstance(code, str) or exchange not in CODE_PATTERNS
                or not CODE_PATTERNS[exchange].fullmatch(code)):
            raise ValueError(f"invalid ordinary A-share code/exchange: {code!r}/{exchange!r}")
        if code in seen:
            raise ValueError(f"duplicate universe code: {code}")
        seen.add(code)
        if row.get("security_type", "A_SHARE") != "A_SHARE":
            raise ValueError(f"non-ordinary security in universe: {code}")
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"missing name for {code}")
        board = row.get("board")
        expected_board = ("star" if code.startswith("688") else "main") if exchange == "SH" else (
            "chinext" if code.startswith(("300", "301", "302")) else "main")
        if board != expected_board:
            raise ValueError(f"code/board mismatch: {code}/{board!r}")
        if row.get("listing_date") is not None:
            listed = _version_date(row["listing_date"])
            if listed != row["listing_date"]:
                raise ValueError(f"listing date is not normalized: {code}")
        exchange_counts[exchange] += 1
        board_counts[f"{exchange}_{board}"] = board_counts.get(f"{exchange}_{board}", 0) + 1
    if expected_total is not None and len(records) != expected_total:
        raise ValueError(f"universe incomplete: {len(records)}/{expected_total}")
    return {
        "total": len(records), "combined_total": len(records),
        "exchange_counts": exchange_counts, "board_counts": board_counts,
        "unique_codes": len(seen), "duplicates": [], "complete": True,
    }


def _excluded(row: dict) -> str | None:
    code = row.get("code", "")
    if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
        return None
    if code.startswith("689") or row.get("security_type") == "CDR":
        return "CDR"
    if code.startswith(("200", "900")) or row.get("security_type") == "B_SHARE":
        return "B_SHARE"
    if row.get("exchange") in ("BJ", "BSE") or code.startswith(("4", "8", "92")):
        return "BSE"
    return None


def _ordinary(records: list[dict]) -> tuple[list[dict], list[dict]]:
    rows, excluded = [], []
    seen = set()
    for row in records:
        code = row.get("code")
        if isinstance(code, str):
            if code in seen:
                raise ValueError(f"duplicate source universe code: {code}")
            seen.add(code)
        reason = _excluded(row)
        if reason:
            excluded.append({"code": row.get("code"), "reason": reason})
            continue
        rows.append(dict(row))
    rows.sort(key=lambda row: str(row.get("code", "")))
    validate_universe(rows)
    return rows, excluded


def _parse_sse(payload: bytes, board: str) -> tuple[list[dict], dict]:
    obj = json.loads(payload)
    if not isinstance(obj, dict) or obj.get("actionErrors") or obj.get("fieldErrors"):
        raise ValueError(f"SSE {board}: invalid/error response")
    rows, page = obj.get("result"), obj.get("pageHelp")
    if not isinstance(rows, list) or not isinstance(page, dict):
        raise ValueError(f"SSE {board}: missing result/pageHelp")
    total = _count(page.get("total"), "SSE total")
    page_no = _count(page.get("pageNo"), "SSE pageNo")
    page_count = _count(page.get("pageCount"), "SSE pageCount")
    if page_no != 1 or page_count != 1 or len(rows) != total:
        raise ValueError(
            f"SSE {board} official pages incomplete: received {len(rows)}/{total}, "
            f"page {page_no}/{page_count}")
    source_date = _version_date(obj.get("queryDate"))
    result = []
    for row in rows:
        code = str(row.get("A_STOCK_CODE", "")).strip()
        result.append({
            "code": code, "name": str(row.get("SEC_NAME_CN") or "").strip(),
            "exchange": "SH", "board": board,
            "security_type": "CDR" if code.startswith("689") else "A_SHARE",
            "listing_date": _version_date(row.get("LIST_DATE")),
            "industry": row.get("CSRC_CODE_DESC"), "industry_code": row.get("CSRC_CODE"),
            "industry_source": "SSE official listed company industry class",
            "official_state_code": row.get("STATE_CODE"),
            "official_stock_state_code": row.get("STATE_CODE_STOCK"),
            "official_product_status": row.get("PRODUCT_STATUS"),
            "universe_source": SSE_ENDPOINT, "official_version_date": source_date,
        })
    return result, {
        "reported_total": total, "downloaded_rows": len(rows), "page_no": page_no,
        "page_count": page_count, "pages_complete": True, "source_version_date": source_date,
        "source_version_note": None if source_date else "SSE response supplies no version date; retrieval date is separate.",
    }


def _xlsx_rows(payload: bytes) -> list[dict[str, str]]:
    """Read the official plain XLSX table using stdlib, retaining leading zeros."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(node.itertext()) for node in root.findall("{*}si")]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.find("{*}sheets")
        if sheets is None or not list(sheets):
            raise ValueError("SZSE XLSX has no worksheet")
        relation_id = next((value for key, value in list(sheets)[0].attrib.items()
                            if key.endswith("}id")), None)
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next((item.get("Target") for item in relations
                       if item.get("Id") == relation_id), None)
        if not target:
            raise ValueError("SZSE XLSX worksheet relation missing")
        if target.startswith("/"):
            member = target.lstrip("/")
        else:
            member = "xl/" + target
        if ".." in member.split("/"):
            raise ValueError("unsafe XLSX worksheet path")
        root = ET.fromstring(archive.read(member))
        data = root.find("{*}sheetData")
        if data is None:
            raise ValueError("SZSE XLSX sheetData missing")
        grid = []
        for row in data:
            cells = {}
            for cell in row:
                column = re.sub(r"\d", "", cell.get("r", ""))
                if not column:
                    raise ValueError("SZSE XLSX cell has no coordinate")
                kind = cell.get("t")
                value = cell.findtext("{*}v", "")
                if kind == "s":
                    value = strings[int(value)]
                elif kind == "inlineStr":
                    inline = cell.find("{*}is")
                    value = "".join(inline.itertext()) if inline is not None else ""
                cells[column] = value.strip()
            if any(cells.values()):
                grid.append(cells)
        if not grid:
            raise ValueError("SZSE XLSX empty")
        headers = {column: re.sub(r"\s+", "", value) for column, value in grid[0].items()}
        required = {"板块", "A股代码", "A股简称", "A股上市日期", "所属行业"}
        if not required.issubset(set(headers.values())):
            raise ValueError("SZSE XLSX required headers missing")
        return [{headers[column]: row.get(column, "") for column in headers} for row in grid[1:]]


def _clean_html(value: Any) -> str:
    return html.unescape(re.sub(r"<[^>]*>", "", str(value or ""))).strip()


def _parse_szse(metadata_payload: bytes, xlsx_payload: bytes) -> tuple[list[dict], dict]:
    obj = json.loads(metadata_payload)
    if not isinstance(obj, list):
        raise ValueError("SZSE metadata is not a list")
    tabs = [tab for tab in obj if isinstance(tab, dict)
            and tab.get("metadata", {}).get("tabkey") == "tab1"]
    if len(tabs) != 1 or tabs[0].get("error"):
        raise ValueError("SZSE A-share tab1 missing or returned error")
    tab = tabs[0]
    meta = tab["metadata"]
    if str(meta.get("catalogid")) != "1110":
        raise ValueError("SZSE wrong catalog id")
    total = _count(meta.get("recordcount"), "SZSE recordcount")
    page_size = _count(meta.get("pagesize"), "SZSE pagesize")
    page_count = _count(meta.get("pagecount"), "SZSE pagecount")
    page_no = _count(meta.get("pageno"), "SZSE pageno")
    sample = tab.get("data")
    if (page_no != 1 or page_count != math.ceil(total / page_size)
            or not isinstance(sample, list) or len(sample) != min(total, page_size)):
        raise ValueError("SZSE official page metadata/sample incomplete")
    source_date = _version_date(meta.get("subname"))
    if source_date is None:
        raise ValueError("SZSE official source version date missing")
    source_rows = _xlsx_rows(xlsx_payload)
    if len(source_rows) != total:
        raise ValueError(f"SZSE official XLSX incomplete: {len(source_rows)}/{total}")
    codes = [row["A股代码"] for row in source_rows]
    if len(codes) != len(set(codes)):
        raise ValueError("SZSE official XLSX duplicate codes")
    source_index = {row["A股代码"]: row for row in source_rows}
    sample_codes = []
    for row in sample:
        code = str(row.get("agdm", "")).strip()
        sample_codes.append(code)
        xlsx_row = source_index.get(code)
        if (xlsx_row is None or _clean_html(row.get("agjc")) != xlsx_row["A股简称"]
                or _version_date(row.get("agssrq")) != _version_date(xlsx_row["A股上市日期"])):
            raise ValueError(f"SZSE JSON/XLSX sample disagrees: {code}")
    if len(sample_codes) != len(set(sample_codes)):
        raise ValueError("SZSE official JSON sample duplicate codes")
    result = []
    for row in source_rows:
        board_name = row["板块"]
        if board_name not in ("主板", "创业板"):
            raise ValueError(f"SZSE unknown A-share board: {board_name!r}")
        result.append({
            "code": row["A股代码"], "name": row["A股简称"].strip(), "exchange": "SZ",
            "board": "chinext" if board_name == "创业板" else "main", "security_type": "A_SHARE",
            "listing_date": _version_date(row["A股上市日期"]), "industry": row["所属行业"] or None,
            "industry_code": row["所属行业"][:1] or None,
            "industry_source": "SZSE official listed company industry class",
            "universe_source": SZSE_XLSX_URL, "official_version_date": source_date,
        })
    return result, {
        "reported_total": total, "downloaded_rows": len(source_rows), "page_no": page_no,
        "page_count": page_count, "page_size": page_size, "xlsx_complete": True,
        "json_sample_rows": len(sample), "json_xlsx_sample_agrees": True,
        "source_version_date": source_date,
    }


def _fetch(url: str, timeout: int, path: Path) -> tuple[bytes, dict]:
    referer = "https://www.sse.com.cn/" if "sse.com.cn/" in url and "szse.cn/" not in url else "https://www.szse.cn/"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": referer})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
        status = response.status
        headers = {key.lower(): value for key, value in response.headers.items()
                   if key.lower() in ("date", "content-type", "content-length", "last-modified", "etag")}
    if status != 200 or not payload:
        raise ValueError(f"empty/non-200 official response: {status}")
    retrieved_at = datetime.now(TZ).isoformat()
    _write_bytes(path, payload)
    evidence = {"url": url, "retrieved_at": retrieved_at, "http_status": status,
                "http_headers": headers, "bytes": len(payload), "sha256": _sha256(payload),
                "raw_file": path.as_posix()}
    _write_bytes(path.with_suffix(path.suffix + ".meta.json"), _json_bytes(evidence))
    return payload, evidence


def _live(root: Path, asof: str, timeout: int) -> tuple[list[dict], dict]:
    state = root / "output/boll/state"
    attempt_at = datetime.now(TZ)
    source_dir = state / "universe_sources" / attempt_at.strftime("%Y%m%dT%H%M%S%f%z")
    inputs = {
        "sse_main": (_sse_url("1"), "sse_main.json"),
        "sse_star": (_sse_url("8"), "sse_star.json"),
        "szse_metadata": (SZSE_JSON_URL, "szse_metadata.json"),
        "szse_xlsx": (SZSE_XLSX_URL, "szse.xlsx"),
    }
    # Four independent exchange responses, one bounded attempt per response.
    with ThreadPoolExecutor(max_workers=4) as executor:
        tasks = {key: executor.submit(_fetch, url, timeout, source_dir / filename)
                 for key, (url, filename) in inputs.items()}
        outputs, errors = {}, []
        for key, task in tasks.items():
            try:
                outputs[key] = task.result()
            except Exception as exc:
                errors.append(f"{key}: {type(exc).__name__}: {exc}")
    if errors:
        _write_bytes(source_dir / "attempt_errors.json", _json_bytes({
            "attempted_at": attempt_at.isoformat(), "errors": errors,
            "sources": {key: value[1] for key, value in outputs.items()},
        }))
        raise ValueError("; ".join(errors))
    sh_main, main_audit = _parse_sse(outputs["sse_main"][0], "main")
    sh_star, star_audit = _parse_sse(outputs["sse_star"][0], "star")
    sz, sz_audit = _parse_szse(outputs["szse_metadata"][0], outputs["szse_xlsx"][0])
    rows, excluded = _ordinary(sh_main + sh_star + sz)
    audits = {"sse_main": main_audit, "sse_star": star_audit, "szse": sz_audit}
    reported_total = sum(audit["reported_total"] for audit in audits.values())
    counts = validate_universe(rows, reported_total - len(excluded))
    sources = {key: value[1] for key, value in outputs.items()}
    for evidence in sources.values():
        evidence["raw_file"] = str(Path(evidence["raw_file"]).relative_to(root))
    for key in ("sse_main", "sse_star"):
        sources[key].update(audits[key])
    for key in ("szse_metadata", "szse_xlsx"):
        sources[key].update(sz_audit)
    reasons = []
    version = sz_audit["source_version_date"]
    if version < asof:
        reasons.append(f"SZSE source version {version} precedes requested asof {asof}")
    if version > attempt_at.date().isoformat():
        reasons.append(f"SZSE source version {version} is later than retrieval date")
    # A cached HTTP response from a preceding date must not become fresh merely
    # because it was downloaded again today. HTTP Date is not a version date.
    for key, evidence in sources.items():
        http_date = evidence.get("http_headers", {}).get("date")
        if http_date:
            try:
                server_date = parsedate_to_datetime(http_date).astimezone(TZ).date().isoformat()
            except (TypeError, ValueError, OverflowError):
                reasons.append(f"{key}: unparseable HTTP Date")
            else:
                evidence["http_server_date"] = server_date
                if server_date < asof:
                    reasons.append(f"{key}: HTTP response date {server_date} precedes asof {asof}")
    return rows, {
        "schema_version": SCHEMA_VERSION, "mode": "official_live", "asof": asof,
        "version_date": version, "retrieved_at": datetime.now(TZ).isoformat(),
        "fresh": not reasons, "freshness_reasons": reasons,
        "point_in_time_compatible": version <= asof,
        "source_version_dates": {key: audit["source_version_date"] for key, audit in audits.items()},
        "sse_source_version_unknown": any(audits[key]["source_version_date"] is None for key in ("sse_main", "sse_star")),
        "counts": counts, "total": len(rows), "combined_total": len(rows),
        "official_reported_total_including_exclusions": reported_total,
        "source_counts": {key: audit["reported_total"] for key, audit in audits.items()},
        "sources": sources, "source_audits": audits, "excluded": excluded,
        "ordinary_A_share_policy": "All official listing states retained; ST, suspension, liquidity and history filtering occurs later.",
    }


def _persist(root: Path, rows: list[dict], meta: dict) -> None:
    state = root / "output/boll/state"
    payload = _json_bytes(rows)
    meta["universe_sha256"] = _sha256(payload)
    _write_bytes(state / "universe.json", payload)
    _write_bytes(state / "universe_meta.json", _json_bytes(meta))


def membership_current(meta: dict, report_date: str) -> bool:
    """Accept a live refresh or source-hashed official evidence from this date.

    A failed live refresh remains fresh=False. Reusing the same day's verified
    source documents does not turn that failure into a live refresh, but can
    supply a current membership baseline. Prior-date seeds never pass.
    """
    if meta.get("fresh"):
        return True
    if meta.get("version_date") != report_date:
        return False
    try:
        retrieved = datetime.fromisoformat(meta["retrieved_at"])
        if retrieved.tzinfo is None or retrieved.astimezone(TZ).date().isoformat() != report_date:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    sources = meta.get("sources", {})
    for key in ("sse_main", "sse_star", "szse_metadata", "szse_xlsx"):
        evidence = sources.get(key, {})
        if (evidence.get("http_status") != 200
                or not re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("sha256", "")))
                or evidence.get("http_server_date") != report_date):
            return False
    return all(sources[key].get("source_version_date") == report_date for key in ("szse_metadata", "szse_xlsx"))


def load_universe(root: Path, asof: str, refresh: bool = True, timeout: int = 12) -> tuple[list[dict], dict]:
    """Load official ordinary A-share records and their source/count provenance.

    Order: live SSE+SZSE (when requested), validated normalized cache, versioned
    config/boll_universe_seed.json. Fallbacks always return fresh=False with an
    explicit reason and retain original source/retrieval/version evidence.
    Raise ValueError if no complete validated source exists. Network operations
    perform at most four concurrent requests, each with the given timeout.
    """
    root = Path(root)
    asof = date.fromisoformat(asof).isoformat()
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ValueError("timeout must be positive")
    failures = []
    if refresh:
        try:
            rows, meta = _live(root, asof, timeout)
            _persist(root, rows, meta)
            return rows, meta
        except Exception as exc:
            failures.append(f"official_refresh_failed: {type(exc).__name__}: {exc}")
    else:
        failures.append("official_refresh_disabled")
    state = root / "output/boll/state"
    try:
        payload = (state / "universe.json").read_bytes()
        old_meta = json.loads((state / "universe_meta.json").read_text("utf-8"))
        if old_meta.get("universe_sha256") != _sha256(payload):
            raise ValueError("cached universe SHA-256 mismatch/missing")
        rows, excluded = _ordinary(json.loads(payload))
        expected_total = old_meta.get("counts", {}).get("total", old_meta.get("total"))
        if not isinstance(expected_total, int):
            raise ValueError("cached universe total missing")
        counts = validate_universe(rows, expected_total)
        meta = dict(old_meta)
        meta.update({"mode": "cache", "asof": asof, "fresh": False,
                     "freshness_reasons": failures, "counts": counts,
                     "loaded_at": datetime.now(TZ).isoformat(),
                     "cached_original_mode": old_meta.get("cached_original_mode", old_meta.get("mode")),
                     "excluded": old_meta.get("excluded", []) + excluded})
        return rows, meta
    except Exception as exc:
        failures.append(f"cache_unavailable: {type(exc).__name__}: {exc}")
    seed_path = root / "config/boll_universe_seed.json"
    try:
        seed_payload = seed_path.read_bytes()
        seed = json.loads(seed_payload)
        if not isinstance(seed, dict) or not isinstance(seed.get("records"), list):
            raise ValueError("seed must contain records array")
        version = _version_date(seed.get("version_date"))
        if version is None or not seed.get("sources"):
            raise ValueError("seed requires version_date and source evidence")
        rows, excluded = _ordinary(seed["records"])
        counts = validate_universe(rows, seed.get("expected_count", len(seed["records"]) - len(excluded)))
        meta = {
            "schema_version": SCHEMA_VERSION, "mode": "seed", "asof": asof,
            "version_date": version, "retrieved_at": seed.get("retrieved_at"),
            "loaded_at": datetime.now(TZ).isoformat(), "fresh": False,
            "freshness_reasons": failures + [f"using fixed seed version {version}; live membership not confirmed"],
            "counts": counts, "total": len(rows), "combined_total": len(rows),
            "sources": seed["sources"], "excluded": excluded,
            "seed_file": str(seed_path.relative_to(root)), "seed_sha256": _sha256(seed_payload),
            "point_in_time_compatible": version <= asof,
        }
        _persist(root, rows, meta)
        return rows, meta
    except Exception as exc:
        failures.append(f"seed_unavailable: {type(exc).__name__}: {exc}")
    raise ValueError("No validated complete official universe available: " + "; ".join(failures))
