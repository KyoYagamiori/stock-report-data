"""Index complete orphan reports without making claims about chat delivery.

The full historical manifest is retained. Readers use the small handoff.json;
only this program needs to merge the historical ledger.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
CYCLES = {"early": "早报", "noon": "午报", "evening": "晚报"}
SECTION = re.compile(r"^##\s+([1-7])[.、．\s].*$", re.M)
ARCHIVE = re.compile(r"reports/archive/(\d{4})/(\d{2})/(\d{2})/(early|noon|evening)(?:[._][^/]*)?\.md\Z")


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)
    return True


def validate_body(text: str, day: str, cycle: str):
    # Reports may start with public YAML metadata. Validate the FIRST H1 rather
    # than requiring the title at byte zero or accepting a later decoy title.
    heading = re.search(r"^#\s+([^\n]+)$", text, re.M)
    if not heading or not re.match(re.escape(day) + r"\s+" + CYCLES[cycle] + r"(?:\s|$)", heading.group(1)):
        raise ValueError("report_title_date_or_cycle_mismatch")
    if [int(m.group(1)) for m in SECTION.finditer(text)] != list(range(1, 8)):
        raise ValueError("complete_ordered_seven_sections_required")
    if "本报告不构成投资建议" not in text:
        raise ValueError("report_disclaimer_missing")


def sections(text: str):
    hits = list(SECTION.finditer(text))
    return {int(hit.group(1)): text[hit.start(): hits[i + 1].start() if i + 1 < len(hits) else len(text)].strip()
            for i, hit in enumerate(hits)}


def _rank(entry):
    path = entry.get("selected_file", "")
    return entry.get("report_date", ""), bool("revision" in path), path


def _resolve_body(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to((root / "reports/archive").resolve()) or not ARCHIVE.fullmatch(relative):
        raise ValueError("invalid_report_archive_path")
    return path


def sync_index(root: Path, *, moment=None):
    root = Path(root).resolve()
    now = (moment or datetime.now(TZ)).astimezone(TZ).isoformat()
    path = root / "reports/latest/manifest.json"
    # A corrupt index is an error, never permission to discard history.
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "schema_version": "1.0", "timezone": "Asia/Shanghai", "reports": [], "latest_by_cycle": {}}
    if not isinstance(manifest.get("reports"), list) or not isinstance(manifest.get("latest_by_cycle"), dict):
        raise ValueError("invalid_existing_report_index")
    known = {entry.get("selected_file") for entry in manifest["reports"]}
    added, rejected = [], []
    for body in sorted((root / "reports/archive").glob("*/*/*/*.md")):
        relative = body.relative_to(root).as_posix()
        match = ARCHIVE.fullmatch(relative)
        if not match or relative in known:
            continue
        year, month, day, cycle = match.groups()
        report_date = f"{year}-{month}-{day}"
        try:
            datetime.fromisoformat(report_date)
            raw = body.read_bytes()
            text = raw.decode("utf-8")
            validate_body(text, report_date, cycle)
            if report_date > now[:10]:
                raise ValueError("future_report_date")
            entry = {"report_date": report_date, "report_type": cycle,
                     "title": f"{report_date} {CYCLES[cycle]}", "selected_file": relative,
                     "archived_at": now, "indexed_at": now, "body_archived_at": None,
                     "sha256": hashlib.sha256(raw).hexdigest(), "body_raw_bytes": len(raw),
                     "body_raw_sha256_verified": True, "archive_index_status": "complete",
                     "chat_delivery_status": "unverified", "metadata_source": "validated_archive_body",
                     "structured_metadata_status": "not_supplied"}
            sidecar = body.with_name(body.stem + "-handoff.json")
            if sidecar.exists():
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
                if (meta.get("report_date") != report_date or meta.get("report_type") != cycle
                        or meta.get("body_sha256") != entry["sha256"]):
                    raise ValueError("report_sidecar_identity_or_hash_mismatch")
                # Exact public research fields, never arbitrary task/user data.
                allowed = {"body_archived_at", "market_cutoff", "news_cutoff", "indicator_cutoff",
                           "snapshot_file", "snapshot_id", "snapshot_quality_grade", "quality",
                           "active_pool", "card_codes", "locked_codes", "focus_stock_code", "focus_status",
                           "focus_reason", "technical_stock_code", "technical_status", "technical_reason",
                           "technical_secondary_code", "research_method", "focus_conditions",
                           "technical_conditions", "technical_secondary_conditions", "market_screen",
                           "research_signals", "available_at"}
                entry.update({key: value for key, value in meta.items() if key in allowed})
                entry["structured_metadata_status"] = "body_hash_bound_sidecar"
            manifest["reports"].append(entry)
            known.add(relative)
            added.append(relative)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            rejected.append({"selected_file": relative, "reason": str(exc)})
    # Retain all existing history and rich fields; only advance pointers.
    for entry in manifest["reports"]:
        cycle = entry.get("report_type")
        if cycle not in CYCLES:
            continue
        prior = manifest["latest_by_cycle"].get(cycle)
        if not prior or _rank(entry) > _rank(prior):
            manifest["latest_by_cycle"][cycle] = entry
    if added:
        manifest["updated_at"] = now
    changed = write_json(path, manifest)
    handoff = {"schema_version": "1.0", "timezone": "Asia/Shanghai",
               "index_updated_at": manifest.get("updated_at"), "history_count": len(manifest["reports"]),
               "archive_does_not_prove_chat_delivery": True, "latest_by_cycle": {}}
    for cycle, entry in manifest["latest_by_cycle"].items():
        try:
            raw = _resolve_body(root, entry["selected_file"]).read_bytes()
            text = raw.decode("utf-8")
            validate_body(text, entry["report_date"], cycle)
            digest = hashlib.sha256(raw).hexdigest()
            if entry.get("sha256") and entry["sha256"] != digest:
                raise ValueError("indexed_body_sha256_mismatch")
            parts = sections(text)
            keep = ("report_date", "report_type", "title", "selected_file", "archived_at", "body_archived_at",
                    "market_cutoff", "news_cutoff", "indicator_cutoff", "snapshot_id", "quality",
                    "focus_stock_code", "focus_status", "technical_stock_code", "technical_status",
                    "active_pool", "card_codes", "research_method", "structured_metadata_status")
            handoff["latest_by_cycle"][cycle] = {
                **{key: entry[key] for key in keep if key in entry}, "sha256": digest,
                "body_raw_bytes": len(raw), "body_raw_sha256_verified": True,
                "chat_delivery_status": "unverified",
                "core_conclusions_markdown": parts[1], "carry_forward_markdown": parts[7]}
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            handoff["latest_by_cycle"][cycle] = {"selected_file": entry.get("selected_file"),
                                                   "status": "invalid", "reason": str(exc)}
    handoff_changed = write_json(root / "reports/latest/handoff.json", handoff)
    return {"added": added, "rejected": rejected, "history_count": len(manifest["reports"]),
            "manifest_changed": changed, "handoff_changed": handoff_changed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = sync_index(args.root)
    print(json.dumps(result, ensure_ascii=False))
    # Legacy unindexed drafts use other formats; retain them untouched and
    # disclose the warning. An invalid current/future report remains fatal.
    today = datetime.now(TZ).date().isoformat()
    return 1 if any("-".join(ARCHIVE.fullmatch(row["selected_file"]).groups()[:3]) >= today
                    for row in result["rejected"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
