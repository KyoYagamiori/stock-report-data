from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ma5_system import SCHEMA_VERSION, STRATEGY_ID


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "ma5_strategy.json"


class StrategyConfigError(ValueError):
    pass


def load_strategy_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or DEFAULT_CONFIG
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StrategyConfigError(f"Missing strategy config: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise StrategyConfigError(f"Invalid strategy config: {exc}") from exc
    validate_strategy_config(payload)
    return payload


def validate_strategy_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != SCHEMA_VERSION:
        raise StrategyConfigError("MA5 schema_version mismatch")
    if config.get("strategy_id") != STRATEGY_ID:
        raise StrategyConfigError("MA5 strategy_id mismatch")
    candidate = config.get("candidate", {})
    if candidate.get("minimum_score") != 70 or candidate.get("a_plus_score") != 85:
        raise StrategyConfigError("Frozen v1 score gates must remain 70/85")
    if candidate.get("maximum_planned_risk_pct") != 5.0:
        raise StrategyConfigError("Frozen v1 maximum planned risk must remain 5%")
    weights = config.get("score_weights", {})
    if sum(int(value) for value in weights.values()) != 100:
        raise StrategyConfigError("Stock score weights must total 100")
    components = config.get("market", {}).get("components", {})
    if sum(int(value) for value in components.values()) != 100:
        raise StrategyConfigError("Market score components must total 100")
    if config.get("position", {}).get("levels") != [0, 40, 70, 100]:
        raise StrategyConfigError("Frozen v1 position levels must be 0/40/70/100")

