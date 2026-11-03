"""Hash-bound public research episodes. Repeated reports never reset an episode."""
from __future__ import annotations

from datetime import datetime, time
import hashlib
import json
import math
import re
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
ROLES = {"comprehensive", "technical", "shadow"}


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("timestamp_requires_timezone")
    return result.astimezone(TZ)


def number(value):
    if isinstance(value, bool):
        raise ValueError("boolean_is_not_a_price")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError("invalid_positive_price")
    return result


def identifier(code, method, strategy, window):
    return hashlib.sha256(json.dumps([code, method, strategy, window], ensure_ascii=False).encode()).hexdigest()[:24]


def frontmatter(text):
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.S)
    out = {}
    if not match:
        return out
    for line in match.group(1).splitlines():
        item = re.match(r"^([a-z_]+):\s*(.*?)\s*$", line)
        if not item:
            continue
        key, value = item.groups()
        try:
            out[key] = json.loads(value)
        except (ValueError, TypeError):
            out[key] = value
    return out


def normalize_signal(value, available_at, report_ref, now):
    code = str(value.get("code", ""))
    if not re.fullmatch(r"(?:000|001|002|003|300|301|302|600|601|603|605|688)\d{3}", code):
        raise ValueError("unsupported_security_code")
    issued, available = stamp(value["first_issued_at"]), stamp(available_at)
    end = stamp(value["valid_until"])
    if not issued <= available <= now or end < issued:
        raise ValueError("signal_time_chain_invalid")
    # A card cannot backdate public availability to its original research window.
    rule = value.get("entry_rule", "observation_only")
    if rule not in {"observation_only", "next_daily_open"}:
        raise ValueError("intraday_trigger_requires_separate_timestamped_execution_evidence")
    roles = sorted(set(value.get("roles", [])))
    if not roles or not set(roles) <= ROLES:
        raise ValueError("signal_roles_invalid")
    method, strategy = str(value["method_version"]), str(value["strategy"])
    original = {"first_issued_at": issued.isoformat(), "valid_until": end.isoformat()}
    signal_id = identifier(code, method, strategy, original)
    if value.get("signal_id") not in (None, signal_id):
        raise ValueError("signal_id_does_not_match_original_window")
    return {"signal_id": signal_id, "code": code, "method_version": method, "strategy": strategy,
            "roles": roles, "first_issued_at": issued.isoformat(), "available_at": available.isoformat(),
            "valid_until": end.isoformat(), "entry_rule": rule,
            "invalidation_price": number(value["invalidation_price"]) if value.get("invalidation_price") is not None else None,
            "reference_price": number(value["reference_price"]) if value.get("reference_price") is not None else None,
            "reference_asof": value.get("reference_asof"), "sources": [report_ref],
            "state": "watching" if rule == "observation_only" else "pending_entry",
            "scope": "public_research_not_user_position", "outcomes": {}}


def upsert(episodes, incoming):
    prior = episodes.get(incoming["signal_id"])
    if prior is None:
        episodes[incoming["signal_id"]] = incoming
        return True
    anchors = ("code", "method_version", "strategy", "first_issued_at", "valid_until", "entry_rule", "invalidation_price")
    if any(prior.get(k) != incoming.get(k) for k in anchors):
        raise ValueError("refuse_to_reset_original_episode_contract")
    prior["roles"] = sorted(set(prior["roles"]) | set(incoming["roles"]))
    for source in incoming["sources"]:
        if source not in prior["sources"]:
            prior["sources"].append(source)
    return False


def import_reports(root, episodes, manifest, now):
    added, rejected, legacy = 0, [], 0
    for entry in sorted(manifest.get("reports", []), key=lambda e: (e.get("report_date", ""), e.get("selected_file", ""))):
        relative = entry.get("selected_file", "")
        path = (root / relative).resolve()
        if not path.is_relative_to(root / "reports/archive") or not path.is_file():
            continue
        try:
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if entry.get("sha256") != digest:
                continue
            from report_support.index import validate_body
            validate_body(raw.decode(), entry["report_date"], entry["report_type"])
            ref = {"file": relative, "sha256": digest}
            meta = frontmatter(raw.decode())
            sidecar = path.with_name(path.stem + "-handoff.json")
            supplied = json.loads(sidecar.read_text()) if sidecar.exists() else {}
            if supplied and supplied.get("body_sha256") != digest:
                raise ValueError("signal_sidecar_body_hash_mismatch")
            available = supplied.get("available_at") or meta.get("archived_at")
            if not available or stamp(available) > now:
                continue
            signals = supplied.get("research_signals", [])
            if not isinstance(signals, list):
                raise ValueError("research_signals_must_be_an_array")
            for signal in signals:
                candidate = normalize_signal(signal, available, ref, now)
                added += upsert(episodes, candidate)
            if signals:
                continue
            # Legacy prose is not executable. Keep observations without inventing
            # trigger prices, expiry dates, fills, or retrospective success rates.
            for prefix, role in (("focus", "comprehensive"), ("technical", "technical")):
                code = str(meta.get(prefix + "_stock_code", ""))
                if not re.fullmatch(r"\d{6}", code):
                    continue
                window = meta.get(prefix + "_original_window") or "legacy_window_unknown"
                method = str(meta.get("research_method") or "legacy_manual_review")
                sid = identifier(code, method, "legacy_observation", window)
                if sid not in episodes:
                    episodes[sid] = {"signal_id": sid, "code": code, "method_version": method,
                        "strategy": "legacy_observation", "roles": [role], "original_window_raw": window,
                        "first_issued_at": available, "available_at": available, "valid_until": None,
                        "entry_rule": "observation_only", "invalidation_price": None,
                        "sources": [ref], "state": "observation_only_unscored", "outcomes": {},
                        "gaps": ["legacy_trigger_and_expiry_not_machine_verified"],
                        "scope": "observation_not_trade"}
                    legacy += 1
                else:
                    ep = episodes[sid]
                    ep["roles"] = sorted(set(ep["roles"]) | {role})
                    if ref not in ep["sources"]:
                        ep["sources"].append(ref)
        except (ValueError, KeyError, TypeError, OSError, UnicodeError) as exc:
            rejected.append({"file": relative, "reason": str(exc)})
    return {"new_contracts": added, "new_legacy_observations": legacy, "rejected": rejected}


def evaluate_episode(ep, tape, calendar, now, cost_bps=20.0):
    if ep["entry_rule"] == "observation_only":
        if ep.get("valid_until") and now > stamp(ep["valid_until"]):
            ep["state"] = "expired_untriggered"
        return ep
    available = stamp(ep["available_at"])
    sessions = [d for d in sorted(set(calendar)) if datetime.combine(datetime.fromisoformat(d).date(), time(9, 30), TZ) > available]
    if not sessions:
        ep["state"] = "awaiting_calendar"
        return ep
    entry_date = sessions[0]
    if datetime.fromisoformat(entry_date + "T09:30:00+08:00") > stamp(ep["valid_until"]):
        ep["state"] = "expired_untriggered"
        return ep
    entry = tape.get(entry_date, {}).get(ep["code"])
    if not entry:
        ep["state"] = "awaiting_entry_evidence"
        return ep
    if entry.get("basis_change"):
        ep["state"] = "blocked_corporate_action"
        return ep
    limit = .20 if ep["code"].startswith(("300", "301", "302", "688")) else .10
    prev = entry.get("previous_close")
    if entry.get("volume", 0) <= 0 or (prev and entry["open"] >= prev * (1 + limit - .001)):
        ep["state"] = "unfilled_entry"
        return ep
    if ep.get("invalidation_price") and entry["open"] <= ep["invalidation_price"]:
        ep["state"] = "invalid_before_entry"
        return ep
    price = entry["open"]
    ep["entry"] = {"date": entry_date, "price": price, "policy": "next_daily_open_strictly_after_publication",
                   "execution_status": "research_fill_assumption_not_broker_execution"}
    for horizon in (1, 3, 5):
        key = f"t_plus_{horizon}"
        if len(sessions) <= horizon:
            continue
        exit_date = sessions[horizon]
        if datetime.fromisoformat(exit_date + "T15:00:00+08:00") > now:
            continue
        path = [tape.get(d, {}).get(ep["code"]) for d in sessions[:horizon + 1]]
        if any(r is None for r in path):
            ep.setdefault("outcome_gaps", {})[key] = "missing_session_no_suspension_or_fill_inference"
            continue
        if any(r.get("basis_change") for r in path):
            ep.setdefault("outcome_gaps", {})[key] = "corporate_action_return_requires_adjusted_evidence"
            continue
        gross = (path[-1]["close"] / price - 1) * 100
        ep["outcomes"][key] = {"exit_date": exit_date, "gross_return_pct": gross,
            "net_return_pct": gross - cost_bps / 100, "cost_bps_assumption": cost_bps,
            "mae_pct": (min(r["low"] for r in path) / price - 1) * 100,
            "mfe_pct": (max(r["high"] for r in path) / price - 1) * 100,
            "measurement": "fixed_horizon_price_label_not_dynamic_stop_strategy_pnl",
            "official_benchmark_excess_pct": None, "industry_excess_pct": None}
    # Record the first failure without pretending a daily low gave an immediate fill.
    for d in sessions[:6]:
        row = tape.get(d, {}).get(ep["code"])
        if row and (row.get("below_mid_last_two") or ep.get("invalidation_price") and row["close"] <= ep["invalidation_price"]):
            ep.setdefault("first_failure", {"date": d, "kind": "two_completed_closes_below_dynamic_mid" if row.get("below_mid_last_two") else "structural_close_failure",
                "exit_execution": "requires_next_eligible_session_open; no same-day or stop-price fill assumed"})
            break
    ep["state"] = "matured" if "t_plus_5" in ep["outcomes"] else "tracking"
    return ep


def summarize(episodes):
    groups = {}
    for role in sorted(ROLES):
        selected = [e for e in episodes.values() if role in e["roles"]]
        measured = [e for e in selected if e.get("outcomes", {}).get("t_plus_3")]
        returns = [e["outcomes"]["t_plus_3"]["net_return_pct"] for e in measured]
        groups[role] = {"episodes": len(selected), "t_plus_3_matured": len(measured),
            "distinct_entry_dates": len({e["entry"]["date"] for e in measured}),
            "average_net_return_pct": sum(returns) / len(returns) if returns else None,
            "positive_return_fraction": sum(r > 0 for r in returns) / len(returns) if returns else None,
            "observation_only_excluded_from_returns": sum(e["entry_rule"] == "observation_only" for e in selected),
            "statistical_note": "Overlapping stocks/dates are correlated; raw episodes are not independent trials."}
    return {"role_results": groups, "portfolio_drawdown": None,
            "performance_scope": "fixed_horizon_research_labels; no portfolio allocation or validated win probability"}
