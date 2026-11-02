"""Freeze official membership separately from history and quote collection."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path

from .history import write_json
from .universe import load_universe, membership_current, validate_universe

SOURCE_KEYS = {"sse_main", "sse_star", "szse_metadata", "szse_xlsx"}


def read_frozen_universe(root, report_date, moment):
    """Return this date's immutable, byte-verified official list or raise.

    A later successful download cannot establish pre-cutoff availability. No
    previous-date seed or unchecked fresh=True flag is accepted here.
    """
    root = Path(root).resolve()
    manifest = json.loads((root / "output/boll/latest/manifest.json").read_text())
    pointer = manifest.get("latest_universe", {})
    if pointer.get("report_date") != report_date:
        raise ValueError("same_day_frozen_universe_missing")
    published = datetime.fromisoformat(pointer["published_at"])
    if published.tzinfo is None or published > moment:
        raise ValueError("frozen_universe_not_yet_published")
    path = (root / pointer["universe_file"]).resolve()
    if not path.is_relative_to(root / "output/boll/archive"):
        raise ValueError("frozen_universe_outside_archive")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pointer.get("universe_sha256"):
        raise ValueError("frozen_universe_sha256_mismatch")
    data = json.loads(raw)
    rows, meta = data["records"], data["provenance"]
    validate_universe(rows, pointer["universe_count"])
    # Check the dated source contract even for a previous live result.
    dated = {**meta, "fresh": False}
    if not membership_current(dated, report_date) or not SOURCE_KEYS.issubset(meta.get("sources", {})):
        raise ValueError("frozen_official_membership_not_current")
    for key in SOURCE_KEYS:
        source = meta["sources"][key]
        stamp = datetime.fromisoformat(source["retrieved_at"])
        if stamp.tzinfo is None or stamp > moment:
            raise ValueError("frozen_official_source_from_future")
        source_path = (root / source["raw_file"]).resolve()
        if not source_path.is_relative_to(path.parent / "universe_sources"):
            raise ValueError("frozen_official_source_outside_version")
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("frozen_official_source_sha256_mismatch")
    return rows, {**meta, "fresh": False, "mode": "same_day_immutable_official",
                  "frozen_source": pointer, "source_bytes_verified": True,
                  "reuse_note": "Same-day official source evidence reused; not a new live refresh."}


def freeze_membership(root, moment=None):
    """Publish membership without fetching or recomputing any daily bars."""
    from .runner import TZ, archive_universe_sources, resolve_dates

    root = Path(root).resolve()
    now = moment or datetime.now(TZ)
    dates = resolve_dates(root, now, "early")
    if not dates["is_trading_day"]:
        return {"accepted": False, "status": "not_applicable", "report_date": dates["report_date"]}
    rows, meta = load_universe(root, dates["report_date"], refresh=True)
    validate_universe(rows)
    directory = root / "output/boll/archive" / dates["report_date"] / (now.strftime("%Y%m%dT%H%M%S%f") + "-membership")
    directory.mkdir(parents=True, exist_ok=False)
    meta, evidence = archive_universe_sources(root, directory, meta)
    dated = {**meta, "fresh": False}
    accepted = (membership_current(dated, dates["report_date"]) and SOURCE_KEYS.issubset(evidence)
                and all(evidence[key]["status"] == "archived" for key in SOURCE_KEYS))
    path = directory / "universe.json"
    write_json(path, {"records": rows, "provenance": meta})
    published = moment or datetime.now(TZ)
    pointer = {"report_date": dates["report_date"], "published_at": published.isoformat(),
               "universe_file": path.relative_to(root).as_posix(),
               "universe_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
               "universe_count": len(rows), "accepted": accepted}
    manifest_path = root / "output/boll/latest/manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"schema_version": "1.0"}
    old = manifest.get("latest_universe", {})
    if accepted and (pointer["report_date"], pointer["published_at"]) >= (old.get("report_date", ""), old.get("published_at", "")):
        manifest["latest_universe"] = pointer
        write_json(manifest_path, manifest)
    result = {**pointer, "status": "ready" if accepted else "incomplete", "source_evidence": evidence,
              "freshness_reasons": meta.get("freshness_reasons", [])}
    write_json(directory / "membership_check.json", result)
    return result


def main():
    result = freeze_membership(Path(__file__).resolve().parents[1])
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["accepted"] or result["status"] == "not_applicable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
