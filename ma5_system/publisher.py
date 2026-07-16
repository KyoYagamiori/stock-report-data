from __future__ import annotations

import hashlib
import json
import os
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ma5_system import SCHEMA_VERSION, STRATEGY_ID
from ma5_system.contracts import validate_manifest, validate_screen
from ma5_system.render import render_screen_markdown


@dataclass(frozen=True)
class PublishResult:
    archive_file: Path
    markdown_file: Path
    manifest_file: Path
    sha256: str
    selected: bool
    reason: str


def publish_screen(screen: dict[str, Any], all_signals: list[dict[str, Any]], root: Path) -> PublishResult:
    phase = screen["phase"]
    report_date = screen["report_date"]
    year, month, day = report_date.split("-")
    archive_dir = root / "output" / "ma5" / "archive" / year / month / day / phase / screen["scan_id"]
    archive_dir.mkdir(parents=True, exist_ok=True)
    shards = _write_signal_shards(archive_dir, all_signals, root)
    final_screen = deepcopy(screen)
    final_screen["signal_shards"] = shards
    validate_screen(final_screen)
    json_bytes = _json_bytes(final_screen)
    markdown = render_screen_markdown(final_screen)
    json_path = archive_dir / "screen.json"
    markdown_path = archive_dir / "screen.md"
    _atomic_write(json_path, json_bytes)
    _atomic_write(markdown_path, markdown.encode("utf-8"))
    digest = hashlib.sha256(json_bytes).hexdigest()

    manifest_path = root / "output" / "ma5" / "latest" / "manifest.json"
    manifest = _load_manifest(manifest_path)
    current_pointer = manifest["scans"].get(phase)
    selected, reason = _should_select(final_screen, current_pointer, root)
    latest_dir = root / "output" / "ma5" / "latest" / phase
    latest_json = latest_dir / "screen.json"
    latest_md = latest_dir / "screen.md"
    if not selected:
        _write_attempt_health(root, final_screen, False, reason)
        return PublishResult(json_path, markdown_path, manifest_path, digest, False, reason)
    latest_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(latest_json, json_bytes)
    _atomic_write(latest_md, markdown.encode("utf-8"))
    pointer = {
        "scan_id": final_screen["scan_id"],
        "report_date": report_date,
        "market_date": final_screen["market_date"],
        "planned_at": final_screen["planned_at"],
        "started_at": final_screen["started_at"],
        "quote_time_max": final_screen.get("quote_time_max"),
        "selected_file": _relative(json_path, root),
        "latest_alias": _relative(latest_json, root),
        "sha256": digest,
        "grade": final_screen["quality"]["grade"],
        "actionable": final_screen["quality"]["actionable"],
        "market_score": final_screen["market_environment"]["score"],
        "market_regime": final_screen["market_environment"]["regime"],
        "maximum_position_pct": final_screen["market_environment"]["maximum_position_pct"],
        "top10": [
            {
                "code": card.get("code"),
                "name": card.get("name"),
                "score": card.get("score"),
                "a_plus": bool(card.get("a_plus")),
            }
            for card in final_screen["top10"]
        ],
        "signal_shards": final_screen["signal_shards"],
        "completed_at": final_screen["completed_at"],
    }
    manifest["generated_at"] = final_screen["completed_at"]
    manifest["latest_phase"] = phase
    manifest["scans"][phase] = pointer
    manifest["report_readiness"][phase] = {
        "status": final_screen["quality"]["report_readiness"],
        "grade": final_screen["quality"]["grade"],
        "actionable": final_screen["quality"]["actionable"],
        "reasons": final_screen["quality"].get("reasons", []),
    }
    validate_manifest(manifest)
    _atomic_write(manifest_path, _json_bytes(manifest))
    _write_attempt_health(root, final_screen, True, reason)
    return PublishResult(json_path, markdown_path, manifest_path, digest, True, reason)


def verify_manifest_pointer(root: Path, phase: str) -> dict[str, Any]:
    manifest_path = root / "output" / "ma5" / "latest" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    pointer = manifest["scans"].get(phase)
    if pointer is None:
        raise ValueError(f"No MA5 pointer for {phase}")
    path = root / pointer["selected_file"]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != pointer["sha256"]:
        raise ValueError(f"MA5 pointer hash mismatch for {phase}")
    payload = json.loads(data.decode("utf-8"))
    validate_screen(payload)
    expected_top10 = [
        {
            "code": card.get("code"),
            "name": card.get("name"),
            "score": card.get("score"),
            "a_plus": bool(card.get("a_plus")),
        }
        for card in payload["top10"]
    ]
    if pointer["top10"] != expected_top10:
        raise ValueError(f"MA5 manifest Top10 summary mismatch for {phase}")
    if pointer["market_score"] != payload["market_environment"]["score"]:
        raise ValueError(f"MA5 manifest market score mismatch for {phase}")
    if pointer["signal_shards"] != payload["signal_shards"]:
        raise ValueError(f"MA5 manifest shard pointers mismatch for {phase}")
    for shard in pointer["signal_shards"]:
        shard_path = root / shard["file"]
        shard_data = shard_path.read_bytes()
        if hashlib.sha256(shard_data).hexdigest() != shard["sha256"]:
            raise ValueError(f"MA5 signal shard hash mismatch for {phase}: {shard['bucket']}")
    return payload


def _write_signal_shards(archive_dir: Path, signals: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for signal in signals:
        code = str(signal.get("code", ""))
        bucket = "sz00" if code.startswith("00") else "sz30" if code.startswith("30") else "sh60" if code.startswith("60") else "sh68" if code.startswith("68") else "other"
        compact = {
            key: signal.get(key)
            for key in (
                "code", "name", "industry", "latest", "pct_change", "score", "eligible", "a_plus",
                "ma5", "ma10", "ma20", "ma60", "distance_to_ma5_pct", "box_top", "box_bottom",
                "buy_zone_low", "buy_zone_high", "confirmation_price", "hard_invalidation", "target_2r",
                "planned_risk_pct", "reward_risk", "minute_vwap", "local_tail_high", "confirmation_met",
                "event_risk", "long_holiday_risk", "direction_retreating", "data_grade", "eligibility_failures"
            )
        }
        buckets.setdefault(bucket, []).append(compact)
    pointers = []
    for bucket, records in sorted(buckets.items()):
        path = archive_dir / f"signals-{bucket}.json"
        data = _json_bytes({"bucket": bucket, "records": records})
        _atomic_write(path, data)
        pointers.append({"bucket": bucket, "file": _relative(path, root), "sha256": hashlib.sha256(data).hexdigest(), "count": len(records)})
    return pointers


def _load_manifest(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": STRATEGY_ID,
        "generated_at": "1970-01-01T00:00:00+08:00",
        "latest_phase": "preclose",
        "scans": {"preclose": None, "close": None},
        "report_readiness": {"preclose": None, "close": None},
    }


def _should_select(candidate: dict[str, Any], current_pointer: dict[str, Any] | None, root: Path) -> tuple[bool, str]:
    if current_pointer is None:
        return True, "first scan for phase"
    if candidate["report_date"] > current_pointer["report_date"]:
        return True, "new report cycle"
    if candidate["report_date"] < current_pointer["report_date"]:
        return False, "older report cycle"
    try:
        current = json.loads((root / current_pointer["selected_file"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True, "current pointer unreadable"
    if candidate["phase"] == "preclose" and candidate["quality"]["actionable"] != current["quality"]["actionable"]:
        return candidate["quality"]["actionable"], "actionable preclose scan has priority"
    rank = {"F": 0, "B": 1, "A": 2}
    candidate_rank = rank[candidate["quality"]["grade"]]
    current_rank = rank[current["quality"]["grade"]]
    if candidate_rank != current_rank:
        return candidate_rank > current_rank, "higher quality grade selected"
    candidate_quote = str(candidate.get("quote_time_max") or "")
    current_quote = str(current.get("quote_time_max") or "")
    if candidate_quote != current_quote:
        return candidate_quote > current_quote, "newer quote time selected"
    return candidate["completed_at"] > current["completed_at"], "later equal-quality scan selected"


def _write_attempt_health(root: Path, screen: dict[str, Any], selected: bool, reason: str) -> None:
    path = root / "output" / "ma5" / "health" / "latest_attempt.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": STRATEGY_ID,
        "scan_id": screen["scan_id"],
        "phase": screen["phase"],
        "report_date": screen["report_date"],
        "completed_at": screen["completed_at"],
        "grade": screen["quality"]["grade"],
        "actionable": screen["quality"]["actionable"],
        "selected": selected,
        "reason": reason,
    }
    _atomic_write(path, _json_bytes(payload))


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()
