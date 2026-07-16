from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


class ContractError(ValueError):
    pass


def validate_payload(payload: dict[str, Any], schema_name: str) -> None:
    try:
        from jsonschema import FormatChecker
        from jsonschema.validators import validator_for
    except ImportError:  # pragma: no cover - lightweight offline fallback
        _manual_validate(payload, schema_name)
        return
    schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator = validator_class(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        details = []
        for error in errors[:12]:
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            details.append(f"{location}: {error.message}")
        raise ContractError("; ".join(details))


def _manual_validate(payload: dict[str, Any], schema_name: str) -> None:
    if not isinstance(payload, dict):
        raise ContractError("Payload must be an object")
    common = {"schema_version", "strategy_id"}
    required = (
        common
        | {"scan_id", "phase", "report_date", "market_date", "started_at", "completed_at", "quality", "market_environment", "directions", "top10", "primary_candidate", "signal_shards"}
        if schema_name == "ma5_screen.schema.json"
        else common | {"generated_at", "scans", "report_readiness"}
    )
    missing = sorted(required - set(payload))
    if missing:
        raise ContractError(f"Missing required fields: {', '.join(missing)}")
    if payload.get("schema_version") != "1.0.0" or payload.get("strategy_id") != "ma5_concentrated_v1":
        raise ContractError("MA5 contract identity mismatch")
    if schema_name == "ma5_screen.schema.json":
        if payload.get("phase") not in {"preclose", "close"}:
            raise ContractError("Invalid screen phase")
        if len(payload.get("top10", [])) > 10:
            raise ContractError("Top10 cannot contain more than ten cards")
    else:
        if set(payload.get("scans", {})) != {"preclose", "close"}:
            raise ContractError("Manifest scans must contain preclose and close")


def validate_screen(payload: dict[str, Any]) -> None:
    validate_payload(payload, "ma5_screen.schema.json")
    if payload["phase"] not in payload["scan_id"]:
        raise ContractError("scan_id must include phase")


def validate_manifest(payload: dict[str, Any]) -> None:
    validate_payload(payload, "ma5_manifest.schema.json")
    for phase, pointer in payload["scans"].items():
        if pointer is None:
            continue
        if pointer["scan_id"] not in pointer["selected_file"]:
            raise ContractError(f"{phase} selected_file must be immutable")
