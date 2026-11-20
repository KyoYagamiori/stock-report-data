"""Collect forward close forecasts from report plans and fit a shadow calibration."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from market_screen.history import TZ, canonical_bytes, write_json
from .ledger import number, stamp


INPUT = Path("reports/forecasts")
STATE = Path("output/research/daily_model/report_forecasts.json")
READER = Path("output/research/latest/daily_model_report_feedback.json")
ROLES = {"comprehensive", "technical", "vcp"}
RELATIONS = {"below", "above", "between"}
ETF_CONTEXTS = {"supportive", "weak", "mixed", "unknown"}
CODE = re.compile(r"(?:000|001|002|003|300|301|302|600|601|603|605|688)\d{3}")
SOURCE = re.compile(r"\d{4}/\d{2}/\d{2}/(?:early|noon|evening|manual)\.json")
ACTIONS = {"buy", "wait", "hold", "reduce", "exit", "avoid"}


def load_state(root):
    path = root / STATE
    return json.loads(path.read_bytes()) if path.exists() else {"sources": {}, "calls": {}}


def normalize_vcp_checks(value, plan):
    if not isinstance(value, dict) or not set(value) <= {
            "daily_breakout", "stop_below_15m", "reduce_after_band_below_15m"}:
        raise ValueError("unsupported_vcp_check")
    result = {}
    for field, anchor in (("stop_below_15m", "stop"), ("reduce_after_band_below_15m", "reduce_low")):
        if field in value:
            if value[field] is not True or plan[anchor] is None:
                raise ValueError("vcp_check_requires_explicit_price")
            result[field] = True
    if "daily_breakout" in value:
        gate = value["daily_breakout"]
        volume = number(gate["min_volume_shares"])
        if volume != int(volume):
            raise ValueError("vcp_breakout_volume_requires_whole_shares")
        result["daily_breakout"] = {"pivot": number(gate["pivot"]), "min_volume_shares": int(volume)}
    return result


def normalize_plan(raw, issued):
    action = raw["action"]
    expiry = stamp(raw["valid_until"])
    if action not in ACTIONS or expiry < issued:
        raise ValueError("invalid_action_or_window")
    out = {"action": action, "valid_until": expiry.isoformat()}
    for field in ("buy_low", "buy_high", "reduce_low", "reduce_high", "stop", "profit_target"):
        out[field] = number(raw[field]) if raw.get(field) is not None else None
    for low, high in (("buy_low", "buy_high"), ("reduce_low", "reduce_high")):
        if (out[low] is None) != (out[high] is None) or out[low] is not None and out[low] > out[high]:
            raise ValueError("invalid_action_price_band")
    fraction = number(raw["reduce_fraction"]) if raw.get("reduce_fraction") is not None else None
    if fraction is not None and fraction > 1:
        raise ValueError("invalid_reduce_fraction")
    out["reduce_fraction"] = fraction
    for field in ("entry_rule", "exit_rule"):
        value = raw.get(field, "")
        if not isinstance(value, str) or len(value) > 260:
            raise ValueError("invalid_public_plan_rule")
        out[field] = value
    if "vcp_checks" in raw:
        try:
            out["vcp_checks"] = normalize_vcp_checks(raw["vcp_checks"], out)
        except (ValueError, TypeError, KeyError) as exc:
            out["vcp_checks_error"] = str(exc)[:120]
    return out


def normalize(payload, relative, now, calendar):
    issued = stamp(payload["issued_at"])
    phase = relative.stem
    if (payload.get("schema_version") != 1 or issued > now
            or issued.strftime("%Y/%m/%d") != relative.parent.as_posix()):
        raise ValueError("invalid_forecast_publication_date")
    raw_calls = payload["calls"]
    if not isinstance(raw_calls, list) or not 1 <= len(raw_calls) <= 6:
        raise ValueError("invalid_forecast_call_count")
    calls = []
    for raw in raw_calls:
        code, check_day, relation = raw["code"], raw["check_day"], raw["relation"]
        roles = sorted(set(raw["roles"]))
        context = raw.get("etf_context", "unknown")
        if (not CODE.fullmatch(code) or not roles or not set(roles) <= ROLES
                or relation not in RELATIONS or context not in ETF_CONTEXTS
                or check_day not in calendar):
            raise ValueError("invalid_forecast_identity")
        cutoff = stamp(check_day + "T15:00:00+08:00")
        quote_time = stamp(raw["quote_asof"])
        if not quote_time <= issued < cutoff:
            raise ValueError("forecast_must_precede_the_close_under_review")
        reference_price = number(raw["reference_price"])
        price = number(raw["price"])
        high = number(raw["high"]) if relation == "between" else None
        if high is not None and high <= price:
            raise ValueError("invalid_forecast_price_band")
        signal_id = hashlib.sha256(canonical_bytes([relative.as_posix(), code, check_day])).hexdigest()[:24]
        calls.append({"signal_id": signal_id, "code": code, "roles": roles, "check_day": check_day,
                      "issued_at": issued.isoformat(), "quote_asof": quote_time.isoformat(), "phase": phase,
                      "relation": relation, "price": price, "high": high, "etf_context": context,
                      "reference_price": reference_price, "plan": normalize_plan(raw["plan"], issued)})
    if len({call["signal_id"] for call in calls}) != len(calls):
        raise ValueError("duplicate_code_and_horizon_in_report")
    return calls


def read_published(root, relative):
    # A checkout of the public branch is the evidence of availability. An
    # uncommitted file or an issue timestamp printed by a report cannot prove it.
    ref = subprocess.run(["git", "show", "HEAD:" + relative.as_posix()], cwd=root,
                         capture_output=True, check=False)
    if ref.returncode:
        raise ValueError("forecast_file_not_observed_in_public_checkout")
    return ref.stdout


def register(root, now, calendar, state):
    rejected = []
    for path in sorted((root / INPUT).rglob("*.json")):
        relative = path.relative_to(root)
        name = relative.relative_to(INPUT)
        if not SOURCE.fullmatch(name.as_posix()):
            continue
        try:
            raw = path.read_bytes()
            if len(raw) > 16_384:
                raise ValueError("forecast_file_too_large")
            digest = hashlib.sha256(raw).hexdigest()
            existing = state["sources"].get(relative.as_posix())
            if existing is not None:
                if existing != digest:
                    raise ValueError("forecast_file_revised_after_registration")
                continue
            if raw != read_published(root, relative):
                raise ValueError("forecast_worktree_differs_from_published_bytes")
            calls = normalize(json.loads(raw), name, now, calendar)
            for call in calls:
                call.update(source=relative.as_posix(), source_sha256=digest, seen_at=now.isoformat())
                state["calls"][call["signal_id"]] = call
            state["sources"][relative.as_posix()] = digest
        except (ValueError, KeyError, TypeError, OSError) as exc:
            rejected.append({"file": relative.as_posix(), "reason": str(exc)[:160]})
    return rejected


def due_codes(state, now):
    return {call["code"] for call in state["calls"].values()
            if "outcome" not in call and stamp(call["seen_at"]) < close_time(call) <= now}


def close_time(call):
    return stamp(call["check_day"] + "T15:00:00+08:00")


def settle(state, histories, history_ref, now):
    for call in state["calls"].values():
        if "outcome" in call:
            continue
        cutoff = close_time(call)
        if now < cutoff:
            continue
        if stamp(call["seen_at"]) >= cutoff:
            call["outcome"] = {"status": "publication_unverified_before_close"}
            continue
        bar = histories.get(call["code"], {}).get(call["check_day"])
        if (not bar or bar.get("day") != call["check_day"] or bar.get("volume", 0) <= 0):
            # A late daily archive can still resolve a correctly frozen forecast.
            continue
        price = number(bar["close"])
        boundary = call["price"]
        relation = call["relation"]
        matched = {"below": price < boundary, "above": price > boundary,
                   "between": boundary <= price <= (call["high"] or boundary)}[relation]
        call["outcome"] = {"status": "hit" if matched else "miss", "close": price,
                           "settled_at": now.isoformat(), "source": history_ref}


def fit(calls):
    # Retain noon revisions for review and train with one verified close per
    # stock/day. Weight each date equally inside a calibration group.
    first = {}
    for call in sorted(calls, key=lambda row: (row["seen_at"], row["issued_at"], row["signal_id"])):
        if call.get("outcome", {}).get("status") in {"hit", "miss"}:
            first.setdefault((call["code"], call["check_day"]), call)
    grouped = defaultdict(lambda: defaultdict(list))
    for call in first.values():
        key = f'{call["relation"]}:{call["etf_context"]}'
        grouped[key][call["check_day"]].append(call["outcome"]["status"] == "hit")
    groups = {}
    for key, dates in sorted(grouped.items()):
        groups[key] = {"dates": len(dates), "rows": sum(map(len, dates.values())),
                       "smoothed_close_call_score": (1 + sum(map(statistics.mean, dates.values()))) / (2 + len(dates))}
    return {"state": "shadow_calibration" if first else "waiting_for_verified_closes",
            "rows": len(first), "dates": len({day for _, day in first}), "groups": groups,
            "scope": "raw_close_forecast_calibration_only_not_trade_return_or_formal_daily_model"}


def publish(root, state, rejected, now, history_error=None):
    calls = list(state["calls"].values())
    recent = sorted(calls, key=lambda call: (call["check_day"], call["seen_at"]), reverse=True)[:24]
    statuses = Counter(call.get("outcome", {}).get("status", "data_gap" if now >= close_time(call) else "pending")
                       for call in calls)
    reader = {"version": "public_close_plan_calibration_v1", "generated_at": now.isoformat(),
              "total_calls": len(calls), "statuses": dict(statuses), "model": fit(calls),
              "rejected_sources": rejected[:12], "history_error": history_error, "recent_calls": recent,
              "trade_execution_labels": 0, "formal_production_promotion": False}
    write_json(root / STATE, state)
    write_json(root / READER, reader)
    return reader


def run(root, now=None):
    from .daily_model import load_calendar
    from .daily_model_data import load_bars

    root = Path(root).resolve()
    now = stamp(now.isoformat()) if now is not None else datetime.now(TZ)
    calendar = load_calendar(root, now)
    state = load_state(root)
    rejected = register(root, now, calendar, state)
    codes = due_codes(state, now)
    histories, source, history_error = {}, None, None
    if codes:
        try:
            histories, source = load_bars(root, codes, now)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            history_error = str(exc)[:200]
    settle(state, histories, source, now)
    return publish(root, state, rejected, now, history_error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    reader = run(args.root)
    print(json.dumps({key: reader[key] for key in ("total_calls", "statuses", "model", "history_error")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
