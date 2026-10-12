from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.contracts import (
    ContractError,
    canonical_json_bytes,
    load_json,
    sha256_bytes,
    sha256_file,
    validate_manifest,
    validate_snapshot,
)
from pipeline.manifest import apply_pointer, build_pointer, new_manifest, update_report_readiness, empty_readiness
from pipeline.render import render_health, render_manifest, render_snapshot


QUALITY_RANK = {"F": 0, "B": 1, "A": 2}
FIXED_TYPES = {"early", "noon", "close", "evening"}


@dataclass(frozen=True)
class PublishResult:
    published: bool
    reason: str
    archive_path: Path | None
    manifest_path: Path | None


def should_publish_fixed(candidate: dict[str, Any], current: dict[str, Any] | None) -> bool:
    if candidate.get("snapshot_type") not in FIXED_TYPES:
        return False
    if candidate.get("quality_grade") == "F":
        return False
    if current is None:
        return True
    if candidate["snapshot_type"] != current.get("snapshot_type"):
        return False
    if candidate["report_cycle"] > current["report_cycle"]:
        return True
    if candidate["report_cycle"] < current["report_cycle"]:
        return False
    candidate_rank = QUALITY_RANK[candidate["quality_grade"]]
    current_rank = QUALITY_RANK[current["quality_grade"]]
    if candidate_rank != current_rank:
        return candidate_rank > current_rank
    if _sort_time(candidate.get("quote_time_max")) != _sort_time(current.get("quote_time_max")):
        return _sort_time(candidate.get("quote_time_max")) > _sort_time(current.get("quote_time_max"))
    if _core_count(candidate) != _core_count(current):
        return _core_count(candidate) > _core_count(current)
    return candidate.get("published_at", "") > current.get("published_at", "")


def should_publish_intraday(candidate: dict[str, Any], current: dict[str, Any] | None) -> bool:
    if candidate.get("snapshot_type") != "intraday":
        return False
    if candidate.get("quality_grade") == "F":
        return False
    if current is None:
        return True
    if candidate["market_date"] != current["market_date"]:
        return candidate["market_date"] > current["market_date"]
    if _sort_time(candidate.get("quote_time_max")) != _sort_time(current.get("quote_time_max")):
        return _sort_time(candidate.get("quote_time_max")) > _sort_time(current.get("quote_time_max"))
    candidate_rank = QUALITY_RANK[candidate["quality_grade"]]
    current_rank = QUALITY_RANK[current["quality_grade"]]
    if candidate_rank != current_rank:
        return candidate_rank > current_rank
    return candidate.get("published_at", "") > current.get("published_at", "")


def publish_snapshot(
    snapshot: dict[str, Any], root: Path, calendar: dict[str, Any]
) -> PublishResult:
    if snapshot.get("quality_grade") == "F":
        return PublishResult(False, "F-grade snapshots are never published", None, None)

    validate_snapshot(snapshot)
    payload_bytes = canonical_json_bytes(snapshot)
    digest = sha256_bytes(payload_bytes)
    archive_path = _archive_path(root, snapshot)
    _write_bytes_atomic(archive_path, payload_bytes, immutable=True)
    archive_markdown_path = archive_path.with_suffix(".md")
    markdown_bytes = render_snapshot(snapshot).encode("utf-8")
    _write_bytes_atomic(archive_markdown_path, markdown_bytes, immutable=True)

    manifest_path = root / "output" / "latest" / "manifest.json"
    manifest = _load_or_create_manifest(manifest_path, calendar, snapshot["published_at"])
    current_pointer = manifest["snapshots"].get(snapshot["snapshot_type"])
    try:
        current_snapshot = _load_pointer_snapshot(root, current_pointer)
    except (ContractError, OSError):
        current_snapshot = None
    comparator = should_publish_intraday if snapshot["snapshot_type"] == "intraday" else should_publish_fixed
    if not comparator(snapshot, current_snapshot):
        return PublishResult(False, "candidate did not beat current authoritative snapshot", archive_path, manifest_path)

    relative_archive = archive_path.relative_to(root).as_posix()
    pointer = build_pointer(snapshot, relative_archive, digest)
    latest_path = root / pointer["latest_alias"]
    _write_bytes_atomic(latest_path, payload_bytes)
    _write_bytes_atomic(latest_path.with_suffix(".md"), markdown_bytes)

    legacy_json_path = root / "output" / "latest" / "report_data.json"
    _write_bytes_atomic(legacy_json_path, payload_bytes)
    _write_bytes_atomic(legacy_json_path.with_suffix(".md"), markdown_bytes)

    manifest["calendar"] = dict(calendar)
    apply_pointer(manifest, pointer, snapshot)
    validate_manifest(manifest)
    _write_bytes_atomic(manifest_path, canonical_json_bytes(manifest))
    _write_bytes_atomic(manifest_path.with_suffix(".md"), render_manifest(manifest).encode("utf-8"))
    return PublishResult(True, "published", archive_path, manifest_path)


def verify_pointer(root: Path, pointer: dict[str, Any]) -> dict[str, Any]:
    path = root / pointer["selected_file"]
    if not path.exists():
        raise ContractError(f"Manifest target does not exist: {path}")
    if sha256_file(path) != pointer["sha256"]:
        raise ContractError(f"Manifest target hash mismatch: {path}")
    payload = load_json(path)
    if payload.get("snapshot_id") != pointer.get("selected_snapshot_id"):
        raise ContractError("Manifest snapshot_id does not match target payload")
    validate_snapshot(payload)
    for key in ("snapshot_type", "report_cycle", "market_date", "quality_grade", "quality_profile", "schema_version"):
        if pointer.get(key) != payload.get(key):
            raise ContractError(f"Manifest {key} does not match target payload")
    if _archive_path(root, payload).relative_to(root).as_posix() != pointer["selected_file"]:
        raise ContractError("Manifest path does not match payload date/type/id")
    return payload


def refresh_manifest(root: Path, calendar: dict[str, Any], generated_at: str) -> Path:
    """Refresh availability even when collection fails; never redate market data."""
    path = root / "output/latest/manifest.json"
    manifest = _load_or_create_manifest(path, calendar, generated_at)
    # Historical repairs must not roll the current availability date backwards.
    if calendar["date"] >= manifest["calendar"]["date"]:
        manifest["calendar"] = dict(calendar)
    manifest["generated_at"] = max(manifest["generated_at"], generated_at)
    update_report_readiness(manifest)
    for kind, pointer in manifest["snapshots"].items():
        if not pointer:
            continue
        try:
            verify_pointer(root, pointer)
        except (ContractError, OSError) as exc:
            if kind in manifest["report_readiness"]:
                manifest["report_readiness"][kind] = empty_readiness(f"invalid target: {exc}")
    validate_manifest(manifest)
    _write_bytes_atomic(path, canonical_json_bytes(manifest))
    _write_bytes_atomic(path.with_suffix(".md"), render_manifest(manifest).encode("utf-8"))
    return path


def write_health(root: Path, health: dict[str, Any]) -> Path:
    path = root / "output" / "health" / "latest_run.json"
    _write_bytes_atomic(path, canonical_json_bytes(health))
    _write_bytes_atomic(path.with_suffix(".md"), render_health(health).encode("utf-8"))
    # Retain evidence per run as latest_run will be replaced by the next cycle.
    stamp = str(health.get("started_at", "unknown")).replace(":", "").replace("+", "_")
    kind = health.get("snapshot_type", "unknown")
    _write_bytes_atomic(root / "output/health/runs" / f"{stamp}-{kind}.json", canonical_json_bytes(health))
    manifest_path = root / "output/latest/manifest.json"
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        manifest["health"]["last_attempt"] = {key: health.get(key) for key in
            ("status", "snapshot_type", "planned_at", "started_at", "finished_at", "quality_grade", "published", "reason")}
        manifest["generated_at"] = max(manifest["generated_at"], health["finished_at"])
        if kind in manifest["report_readiness"] and manifest["report_readiness"][kind]["status"] == "not_ready":
            manifest["report_readiness"][kind]["reasons"].append(str(health.get("reason", "unavailable")))
        validate_manifest(manifest)
        _write_bytes_atomic(manifest_path, canonical_json_bytes(manifest))
        _write_bytes_atomic(manifest_path.with_suffix(".md"), render_manifest(manifest).encode("utf-8"))
    return path


def _archive_path(root: Path, snapshot: dict[str, Any]) -> Path:
    year, month, day = snapshot["report_date"].split("-")
    return (
        root
        / "output"
        / "archive"
        / year
        / month
        / day
        / snapshot["snapshot_type"]
        / f"{snapshot['snapshot_id']}.json"
    )


def _load_or_create_manifest(
    path: Path, calendar: dict[str, Any], generated_at: str
) -> dict[str, Any]:
    if not path.exists():
        return new_manifest(calendar, generated_at)
    manifest = load_json(path)
    validate_manifest(manifest)
    return manifest


def _load_pointer_snapshot(root: Path, pointer: dict[str, Any] | None) -> dict[str, Any] | None:
    if pointer is None:
        return None
    try:
        return verify_pointer(root, pointer)
    except ContractError:
        # An old invalid pointer must not block a new verified snapshot.
        return None


def _write_bytes_atomic(path: Path, data: bytes, immutable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        if path.read_bytes() != data:
            raise ContractError(f"Immutable snapshot already exists with different content: {path}")
        return
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _core_count(snapshot: dict[str, Any]) -> int:
    return int(snapshot.get("coverage", {}).get("core", {}).get("valid", 0))


def _sort_time(value: Any) -> str:
    return "" if value is None else str(value)
