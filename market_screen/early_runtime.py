"""Bounded live discovery using verified daily history; no full-history downloads."""
from __future__ import annotations

import argparse
from datetime import datetime, time
import gzip
import hashlib
import json
from pathlib import Path
import statistics
from time import monotonic

from .early import DEFAULTS, VERSION, build, quote_errors
from .history import canonical_bytes, import_seed, load_cache, write_json
from .runner import TZ, resolve_dates


def hydrate_states(root, records, target, include_vcp=False):
    """Upgrade legacy records only from hash-verified local raw history."""
    from .technicals import calculate
    root = Path(root)
    path = root / "output/early/state/feature_cache.json.gz"
    cached = json.loads(gzip.decompress(path.read_bytes())) if path.exists() else {}
    from .vcp import VERSION as VCP_VERSION
    if (cached.get("market_date") != target or cached.get("method_version") != VERSION
            or (include_vcp and cached.get("vcp_version") != VCP_VERSION)):
        cached = {"market_date": target, "method_version": VERSION, "vcp_version": VCP_VERSION, "records": {}}
    missing = [r for r in records if r.get("status") == "screened"
               and (not (r.get("indicators", {}).get("early_state") or {}).get("available")
                    or (include_vcp and r.get("indicators", {}).get("early_state", {}).get("vcp_next_session", {}).get("version") != VCP_VERSION))]
    if not missing:
        return {"rehydrated": 0, "unavailable": 0}
    cache_root = root / "output/boll/state/history"
    needed = [r for r in missing if r["code"] not in cached["records"]]
    if needed:
        import_seed(root / "output/boll/bootstrap/history.jsonl.gz", cache_root, target)
    upgraded, unavailable = 0, 0
    for row in missing:
        i, code = row["indicators"], row["code"]
        saved = cached["records"].get(code)
        if saved and saved.get("price") == i["price"] and saved.get("last_bar") == i["last_bar"]:
            i["early_state"] = saved["early_state"]; upgraded += 1
            continue
        raw = load_cache(cache_root / (code + ".json.gz"), code, target)
        if not raw or raw["bars"][-1]["day"] != target:
            unavailable += 1; continue
        recalculated = calculate(raw["bars"], target)
        if (recalculated["last_bar"] != i["last_bar"] or recalculated["bar_count"] != i["bar_count"]
                or any(abs(recalculated["boll"][k] - i["boll"][k]) > 1e-9 for k in ("mid", "upper", "lower"))):
            unavailable += 1; continue
        i["early_state"] = recalculated["early_state"]
        cached["records"][code] = {"price": i["price"], "last_bar": i["last_bar"],
                                   "early_state": i["early_state"], "raw_history_sha256": raw["history_sha256"]}
        upgraded += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(canonical_bytes(cached), mtime=0))
    return {"rehydrated": upgraded, "unavailable": unavailable}


def update_observations(data, state, calendar, now):
    """Preserve first public observation and original expiry across report periods."""
    episodes = state.setdefault("episodes", {})
    valid_sessions = data.get("valid_sessions", DEFAULTS["valid_sessions"])
    future = [d for d in calendar if d >= data["report_date"]]
    if len(future) < valid_sessions + 1:
        raise ValueError("early_episode_calendar_does_not_cover_original_window")
    for row in data["shortlist"]:
        contracts = []
        for setup in row["setups"]:
            key = hashlib.sha256(canonical_bytes([VERSION, row["code"], setup["pool"], setup["origin"]])).hexdigest()[:24]
            if key not in episodes:
                episodes[key] = {"signal_id": key, "code": row["code"], "strategy": setup["pool"],
                    "signal_origin_session": setup["origin"], "first_seen_at": now.isoformat(),
                    "valid_until": future[valid_sessions] + "T15:00:00+08:00",
                    "initial_stage": row["stage"], "initial_price": row["price"],
                    "initial_distance_to_mid_atr": row["features"]["distance_to_mid_atr"],
                    "entry_rule": "observation_only", "returns_included": False}
            ep = episodes[key]
            if datetime.fromisoformat(ep["first_seen_at"]) > now:
                raise ValueError("episode_first_seen_in_future")
            ep["last_seen_at"] = now.isoformat()
            if row.get("exit_plan", {}).get("status") == "conditional_reference_plan" and "exit_plan" not in ep:
                ep["exit_plan"] = {**row["exit_plan"], "first_issued_at": now.isoformat()}
            ep["state"] = "expired_untriggered" if now > datetime.fromisoformat(ep["valid_until"]) else "observing_unconfirmed"
            contracts.append({k: ep[k] for k in ("signal_id", "first_seen_at", "valid_until", "state")})
        row["original_contracts"] = contracts
        plans = [episodes[c["signal_id"]].get("exit_plan") for c in contracts]
        plans = [p for p in plans if p]
        if plans:
            row["exit_plan"] = min(plans, key=lambda p: p["first_issued_at"])
        row["actionable_window_open"] = any(x["state"] != "expired_untriggered" for x in contracts)
    original_count = len(data["shortlist"])
    data["shortlist"] = [r for r in data["shortlist"] if r["actionable_window_open"]]
    data["active_shortlist_count"] = len(data["shortlist"])
    data["expired_suppressed_count"] = original_count - len(data["shortlist"])
    for ep in episodes.values():
        if now > datetime.fromisoformat(ep["valid_until"]):
            ep["state"] = "expired_untriggered"
    # VCP observations retain their first published pivot and expiry separately.
    vcp_episodes = state.setdefault("vcp_episodes", {})
    shadow = data.get("vcp_shadow", {})
    active, expired = [], 0
    for row in shadow.get("watchlist", []):
        v = row["vcp_shadow"]
        key = hashlib.sha256(canonical_bytes([v["version"], row["code"], v["origin"]])).hexdigest()[:24]
        if key not in vcp_episodes:
            vcp_episodes[key] = {"signal_id": key, "code": row["code"], "origin": v["origin"],
                "first_seen_at": now.isoformat(), "first_stage": v["stage"], "original_pivot": v["pivot"],
                "original_reference_low": v["invalidation_below"],
                "valid_until": future[valid_sessions] + "T15:00:00+08:00", "observation_only": True}
        ep = vcp_episodes[key]
        if datetime.fromisoformat(ep["first_seen_at"]) > now:
            raise ValueError("vcp_episode_first_seen_in_future")
        ep["last_seen_at"] = now.isoformat()
        if row.get("exit_plan", {}).get("status") == "conditional_reference_plan" and "exit_plan" not in ep:
            ep["exit_plan"] = {**row["exit_plan"], "first_issued_at": now.isoformat()}
        if ep.get("exit_plan"):
            row["exit_plan"] = ep["exit_plan"]
        if now > datetime.fromisoformat(ep["valid_until"]):
            expired += 1
        else:
            row["original_contract"] = {k: ep[k] for k in ("signal_id", "first_seen_at", "original_pivot",
                                                          "original_reference_low", "valid_until")}
            active.append(row)
    if shadow:
        shadow.update(watchlist=active, active_watchlist_count=len(active), expired_suppressed_count=expired)
    data["episode_audit"] = {"episodes": len(episodes), "observation_only": True,
                            "vcp_episodes": len(vcp_episodes), "not_a_trade_success_or_win_rate": True}
    return state


def live_session(now):
    t = now.time().replace(tzinfo=None)
    return time(9, 30) <= t <= time(11, 30) or time(13) <= t <= time(15)


def run(root, now=None, quote_collector=None, allow_closed=False):
    from .completed_source import load_completed_records
    from .membership import read_frozen_universe
    from .quotes import fetch_quotes
    root = Path(root).resolve()
    start = monotonic()
    now = now or datetime.now(TZ)
    if now.tzinfo is None:
        raise ValueError("early_runtime_requires_timezone")
    now = now.astimezone(TZ)
    dates = resolve_dates(root, now, "intraday")
    if not dates["is_trading_day"] or not live_session(now):
        if not allow_closed:
            return {"status": "outside_live_session", "checked_at": now.isoformat()}
        dates["phase"] = "early"
    mapping, source, _ = load_completed_records(root, dates["market_date"], now)
    if not source.get("accepted"):
        raise ValueError("early_discovery_requires_accepted_current_daily_source:" + str(source.get("reasons")))
    records = list(mapping.values())
    universe, membership = read_frozen_universe(root, dates["report_date"], now)
    if {r["code"] for r in universe} != set(mapping):
        raise ValueError("early_current_membership_differs_from_completed_store")
    settings = {**json.loads((root / "config/boll_screen.json").read_text()),
                **DEFAULTS, **json.loads((root / "config/early_signals.json").read_text())}
    hydrated = hydrate_states(root, records, dates["market_date"], include_vcp=True)
    directory = root / "output/early/archive" / dates["report_date"] / now.strftime("%H%M%S%f")
    directory.mkdir(parents=True, exist_ok=False)
    quotes, qmeta = ({}, {}) if dates["phase"] == "early" else (quote_collector or fetch_quotes)(
        universe, directory, timeout=8, max_seconds=90)
    published = now if quote_collector else datetime.now(TZ)
    data = build(records, dates, published, settings, quotes)
    rows = data.pop("evaluations")
    valid, no_trade, ages = 0, 0, []
    if dates["phase"] == "intraday":
        for code, q in quotes.items():
            errors = quote_errors(q, code, dates, published, settings)
            if not errors:
                valid += 1
                ages.append((published - datetime.fromisoformat(q["date"] + "T" + q["time"] + "+08:00")).total_seconds())
            elif errors == ["no_trades"]:
                no_trade += 1
    expected = sum(r.get("status") == "screened" for r in records)
    reasonable_rejections = {"risk_warning_name", "low_liquidity_proxy", "corporate_action_basis_conflict", "no_trades"}
    reasonable = sum(mapping[r["code"]].get("status") == "screened" and "features" not in r
                     and bool(r["rejection_reasons"]) and set(r["rejection_reasons"]) <= reasonable_rejections for r in rows)
    complete = data["feature_available_count"] + reasonable == expected
    if dates["phase"] == "intraday":
        complete = complete and valid + no_trade == len(universe)
    data["coverage"] = {"universe_count": len(universe), "expected_feature_count": expected,
        "reasonable_feature_exclusions": reasonable,
        "unresolved_feature_count": expected - data["feature_available_count"] - reasonable,
        "valid_quotes": valid, "no_trade_quotes": no_trade,
        "quote_gaps": len(universe) - valid - no_trade if dates["phase"] == "intraday" else None,
        "full_market_early_scan_complete": complete, "membership_asof": dates["report_date"],
        "daily_source": source, "feature_hydration": hydrated}
    data["coverage"]["unresolved_feature_details"] = [
        {"code": r["code"], "reasons": r["rejection_reasons"]}
        for r in rows if mapping[r["code"]].get("status") == "screened" and "features" not in r
        and not (bool(r["rejection_reasons"]) and set(r["rejection_reasons"]) <= reasonable_rejections)]
    data["latency"] = {"collection_started_at": now.isoformat(), "published_at": published.isoformat(),
        "elapsed_seconds": round(monotonic() - start, 3), "max_accepted_quote_age_seconds": max(ages) if ages else None,
        "median_accepted_quote_age_seconds": statistics.median(ages) if ages else None,
        "target_refresh_seconds": settings["target_refresh_seconds"],
        "service_level": "measured_best_effort_not_guaranteed_5min"}
    state_path = root / "output/early/state/episodes.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    update_observations(data, state, dates["expected_sessions"], published)
    write_json(state_path, state)
    refs = []
    for n in range(0, len(rows), 100):
        part = rows[n:n + 100]
        path = directory / "records" / (part[0]["code"] + "-" + part[-1]["code"] + ".json")
        write_json(path, {"method_version": VERSION, "records": part})
        refs.append({"file": path.relative_to(root).as_posix(), "count": len(part),
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    data["record_shards"] = refs
    # Keep the report reader bounded; detailed provider batches and request
    # lists belong to the hash-bound audit rather than every report's context.
    audit_path = directory / "quote_audit.json"
    write_json(audit_path, qmeta)
    data["quote_source"] = {"file": audit_path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        "note": "Full provider collection audit; raw quote evidence retained in this version."}
    path = directory / "queue.json"
    write_json(path, data)
    pointer = {"selected_file": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
               "report_date": dates["report_date"], "market_date": dates["market_date"],
               "phase": dates["phase"], "published_at": published.isoformat(), "complete": complete,
               "method_version": VERSION, "coverage": data["coverage"], "latency": data["latency"]}
    latest_path = root / "output/early/latest/manifest.json"
    manifest = json.loads(latest_path.read_text()) if latest_path.exists() else {}
    prior = manifest.get("latest_snapshot", {})
    if pointer["published_at"] <= prior.get("published_at", ""):
        raise ValueError("refuse_to_replace_newer_early_snapshot")
    manifest.update(schema_version="1.0", latest_snapshot=pointer, last_attempt=pointer)
    if complete:
        manifest["latest_complete_snapshot"] = pointer
    write_json(latest_path, manifest)
    return {"status": "complete" if complete else "partial", **pointer,
            "pool_counts": data["pool_counts"], "shortlist_count": len(data["shortlist"])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--allow-closed", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args.root, allow_closed=args.allow_closed)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        result = {"status": "failed", "reason": str(exc), "checked_at": datetime.now(TZ).isoformat()}
        write_json(args.root / "output/early/latest/last_failure.json", result)
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
