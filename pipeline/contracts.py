from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline import SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
CONFIG_DIR = ROOT / "config"


class ContractError(ValueError):
    """Raised when a payload violates a frozen v1.6.1 contract."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContractError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"Top-level JSON value must be an object: {path}")
    return payload


def load_schema(name: str) -> dict[str, Any]:
    return load_json(SCHEMA_DIR / name)


def load_quality_profiles() -> dict[str, Any]:
    payload = load_json(CONFIG_DIR / "quality_profiles.json")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("quality_profiles.json schema_version mismatch")
    return payload


def load_report_pools() -> dict[str, Any]:
    payload = load_json(CONFIG_DIR / "report_pools.json")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("report_pools.json schema_version mismatch")
    _validate_report_pools(payload)
    return payload


def _validate_report_pools(payload: dict[str, Any]) -> None:
    seen: set[str] = set()
    for pool_name in ("core", "watch", "supplemental"):
        records = payload.get(pool_name)
        if not isinstance(records, list):
            raise ContractError(f"report_pools.{pool_name} must be an array")
        for record in records:
            if not isinstance(record, dict):
                raise ContractError(f"report_pools.{pool_name} entries must be objects")
            code = str(record.get("code", ""))
            name = str(record.get("name", "")).strip()
            if len(code) != 6 or not code.isdigit() or not name:
                raise ContractError(f"Invalid {pool_name} record: {record}")
            if code in seen:
                raise ContractError(f"Duplicate stock code across report pools: {code}")
            seen.add(code)
    if len(payload["core"]) != 10:
        raise ContractError("Core pool must contain exactly 10 stocks in v1.6.1")
    if len(payload["watch"]) != 14:
        raise ContractError("Watch pool must contain exactly 14 stocks in v1.6.1")
    locked = {record["code"] for record in payload["core"] if record.get("locked") is True}
    if "600584" not in locked:
        raise ContractError("600584 must remain locked in the Core pool")


def _jsonschema_modules():
    try:
        from jsonschema import FormatChecker
        from jsonschema.validators import validator_for
    except ImportError as exc:  # pragma: no cover - dependency failure path
        raise ContractError("jsonschema dependency is required for contract validation") from exc
    return FormatChecker, validator_for


def validate_against_schema(payload: dict[str, Any], schema_name: str) -> None:
    FormatChecker, validator_for = _jsonschema_modules()
    schema = load_schema(schema_name)
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator = validator_class(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        details = []
        for error in errors[:10]:
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            details.append(f"{location}: {error.message}")
        raise ContractError("; ".join(details))


def validate_snapshot(payload: dict[str, Any]) -> None:
    validate_against_schema(payload, "snapshot.schema.json")
    _validate_timezone_fields(
        payload,
        ("planned_at", "started_at", "published_at", "quote_time_min", "quote_time_max"),
    )
    expected_cycle = f"{payload['report_date']}-{payload['snapshot_type']}"
    if payload["report_cycle"] != expected_cycle:
        raise ContractError(f"report_cycle must equal {expected_cycle}")
    if payload["snapshot_type"] not in payload["snapshot_id"]:
        raise ContractError("snapshot_id must include snapshot_type")


def validate_manifest(payload: dict[str, Any]) -> None:
    validate_against_schema(payload, "manifest.schema.json")
    _validate_timezone_fields(payload, ("generated_at",))
    for snapshot_type, pointer in payload["snapshots"].items():
        if pointer is None:
            continue
        if pointer.get("snapshot_type") != snapshot_type:
            raise ContractError(f"Manifest pointer type mismatch: {snapshot_type}")
        if pointer.get("selected_snapshot_id") not in pointer.get("selected_file", ""):
            raise ContractError(f"Manifest selected_file is not immutable for {snapshot_type}")


def _validate_timezone_fields(payload: dict[str, Any], fields: tuple[str, ...]) -> None:
    for field in fields:
        value = payload.get(field)
        if value is None:
            continue
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError as exc:
            raise ContractError(f"{field} is not ISO 8601: {value}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ContractError(f"{field} must include an explicit timezone offset")


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())
