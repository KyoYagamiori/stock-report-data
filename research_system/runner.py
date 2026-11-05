"""CI integration: verify current sources, preserve episodes, publish a small receipt."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess

from report_support.index import write_json
from .ledger import TZ, evaluate_episode, identifier, import_reports, normalize_signal, stamp, summarize, upsert


def hashed(root, reference, prefix="output/boll/archive"):
    relative = reference.get("file", reference.get("selected_file", ""))
    path = (root / relative).resolve()
    if not path.is_relative_to(root / prefix):
        raise ValueError("research_source_outside_allowed_archive")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference.get("sha256"):
        raise ValueError("research_source_sha256_mismatch:" + relative)
    return json.loads(raw), path


def hydrate(root):
    """Sparse checkout only the referenced versions and small research state."""
    from market_screen.workflow_io import archive_directory
    manifest = json.loads((root / "output/boll/latest/manifest.json").read_text())
    patterns = {archive_directory(p["selected_file"]) for key in ("latest_screen", "latest_complete_screen", "latest_noon_overlay")
                if (p := manifest.get(key, {})).get("selected_file")}
    sparse = subprocess.run(["git", "config", "--bool", "core.sparseCheckout"], cwd=root, capture_output=True, text=True)
    if sparse.stdout.strip() == "true" and patterns:
        subprocess.run(["git", "sparse-checkout", "add", "--stdin"], input="\n".join(sorted(patterns)) + "\n", cwd=root, text=True, check=True)
    return sorted(patterns)


def load_current(root, now):
    manifest = json.loads((root / "output/boll/latest/manifest.json").read_text())
    pointer = manifest.get("latest_complete_screen") or manifest.get("latest_screen", {})
    screen, path = hashed(root, pointer)
    if stamp(screen["published_at"]) > now or not screen.get("technical_screen_complete") or screen.get("unresolved_count") != 0:
        raise ValueError("research_requires_published_complete_producer_screen")
    records, seen = [], set()
    for ref in screen["record_shards"]:
        part, _ = hashed(root, ref)
        if len(part["records"]) != ref["count"]:
            raise ValueError("research_record_count_mismatch")
        for row in part["records"]:
            if row["code"] in seen or row.get("market_date") != screen["market_date"]:
                raise ValueError("duplicate_or_wrong_date_research_record")
            seen.add(row["code"])
            records.append(row)
    if len(records) != screen["universe_count"]:
        raise ValueError("research_universe_count_mismatch")
    shadow_ref = screen.get("research_shadow")
    shadow = hashed(root, shadow_ref)[0] if shadow_ref else None
    if shadow and (shadow.get("market_date") != screen["market_date"] or shadow.get("evaluated_count") != len(records)):
        raise ValueError("research_projection_source_identity_mismatch")
    return pointer, screen, records, shadow


def add_shadow_episodes(episodes, screen, shadow, calendar, now):
    if not shadow or screen.get("phase") != "close":
        return 0
    source = {"file": screen["research_shadow"]["selected_file"], "sha256": screen["research_shadow"]["sha256"]}
    issued = screen["published_at"]
    # Replayed historical close data must not be published as an old prediction.
    if stamp(issued).date().isoformat() != screen["market_date"]:
        return 0
    future = [d for d in calendar if d > screen["market_date"]]
    if len(future) < 6:
        return 0
    added = 0
    for pool, candidates in shadow["pools"].items():
        for row in candidates:
            active = any(ep["code"] == row["code"] and ep["strategy"] == pool and ep["method_version"] == shadow["experiment_id"]
                         and ep.get("valid_until") and stamp(ep["valid_until"]) >= stamp(issued) for ep in episodes.values())
            if active:
                continue
            raw = {"code": row["code"], "roles": ["shadow"], "strategy": pool,
                   "method_version": shadow["experiment_id"], "first_issued_at": issued,
                   "valid_until": future[5] + "T15:00:00+08:00", "entry_rule": "next_daily_open",
                   "invalidation_price": row["features"].get("support_low_5d"),
                   "reference_price": row["price"], "reference_asof": screen["market_date"] + "T15:00:00+08:00"}
            ep = normalize_signal(raw, issued, source, now)
            added += upsert(episodes, ep)
    return added


def capture_noon(root, manifest, now):
    from market_screen.quotes import validate_quote
    pointer = manifest.get("latest_noon_overlay", {})
    if not pointer:
        return {"status": "unavailable"}
    overlay, _ = hashed(root, pointer)
    if stamp(pointer["published_at"]) > now or overlay.get("phase") != "noon":
        raise ValueError("noon_reference_not_published")
    quotes = {}
    for ref in overlay.get("quote_shards", []):
        part, _ = hashed(root, ref)
        for row in part["records"]:
            q = row.get("quote") or {}
            if q.get("code") == row["code"] and validate_quote(q, overlay["market_date"], "noon", now=now) == []:
                quotes[row["code"]] = {"volume": q["volume"], "amount": q["amount"], "price": q["close"], "time": q["time"]}
    data = {"market_date": overlay["market_date"], "cutoff": "11:30", "quotes": quotes,
            "full_market_complete": overlay.get("full_market_overlay_complete", False), "source": pointer}
    path = root / "output/research/noon" / (overlay["market_date"] + ".json")
    prior = json.loads(path.read_text()) if path.exists() else {}
    if not prior or len(quotes) > len(prior.get("quotes", {})):
        write_json(path, data)
    return {"status": "recorded", "market_date": overlay["market_date"], "valid_quotes": len(quotes),
            "full_market_complete": data["full_market_complete"]}


def run(root, now=None):
    root = Path(root).resolve()
    now = now or datetime.now(TZ)
    config = json.loads((root / "config/research_v2.json").read_text())
    state_path = root / "output/research/state/episodes.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"schema_version": "1.0", "episodes": {}, "feature_sessions": []}
    episodes = state["episodes"]
    index_path = root / "reports/latest/manifest.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    imports = import_reports(root, episodes, index, now)
    calendar_data = json.loads((root / "output/cache/trade_calendar.json").read_text())
    calendar = sorted(set(calendar_data["trade_dates"]))
    if not calendar_data.get("source") or "fallback" in calendar_data["source"] or not calendar[0] <= now.date().isoformat() < calendar[-1]:
        raise ValueError("research_calendar_unverified_or_out_of_range")
    errors, pointer, screen, records, shadow = [], None, None, [], None
    try:
        pointer, screen, records, shadow = load_current(root, now)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        errors.append(str(exc))
    prospective = bool(screen and screen["market_date"] >= config["forward_start_date"]
                       and screen.get("phase") == "close" and stamp(screen["published_at"]).date().isoformat() == screen["market_date"])
    new_shadow = add_shadow_episodes(episodes, screen, shadow, calendar, now) if prospective else 0
    if (prospective and shadow and shadow.get("feature_available_count", 0) > 0
            and shadow["feature_available_count"] == screen.get("status_counts", {}).get("screened", 0)):
        state["feature_sessions"] = sorted(set(state.get("feature_sessions", [])) | {shadow["market_date"]})
    tape_index_path = root / "output/research/latest/tape_index.json"
    tape_index = json.loads(tape_index_path.read_text()) if tape_index_path.exists() else {}
    needed = {e["code"] for e in episodes.values() if e["entry_rule"] != "observation_only" and e["state"] != "matured"}
    if screen:
        bars = {}
        for row in records:
            if row["code"] not in needed or row.get("status") != "screened":
                continue
            i = row["indicators"]
            bar = i["last_bar"]
            if bar["day"] != screen["market_date"]:
                raise ValueError("tape_bar_date_mismatch")
            previous = (i.get("previous_bar") or {}).get("close")
            quoted_previous = (row.get("quote") or {}).get("prev_close")
            bars[row["code"]] = {**bar, "previous_close": previous,
                "basis_change": bool((row.get("source") or {}).get("corporate_action_basis_change")
                                     or previous and quoted_previous and abs(previous - quoted_previous) > .011),
                "below_mid_last_two": i.get("below_mid_last_two", False)}
        if bars:
            payload = {"market_date": screen["market_date"], "source": pointer, "bars": bars}
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            path = root / "output/research/tape" / screen["market_date"] / (digest + ".json")
            write_json(path, payload)
            tape_index[screen["market_date"]] = {"file": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    tape = {}
    for day, ref in tape_index.items():
        if day <= now.date().isoformat():
            tape[day] = hashed(root, ref, "output/research/tape")[0]["bars"]
    for ep in episodes.values():
        # Matured outcomes are immutable forward records; reruns do not re-score.
        if ep["state"] != "matured":
            evaluate_episode(ep, tape, calendar, now, config["round_trip_cost_bps_assumption"])
    try:
        noon = capture_noon(root, json.loads((root / "output/boll/latest/manifest.json").read_text()), now)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        noon = {"status": "unavailable", "reason": str(exc)}
    results = summarize(episodes)
    sessions = len(state.get("feature_sessions", []))
    summary = {"schema_version": "1.0", "generated_at": now.isoformat(), "experiment_id": config["experiment_id"],
        "mode": "shadow", "production_strategy": "boll_v1", "new_shadow_episodes": new_shadow,
        "report_import": imports, "episode_count": len(episodes), "feature_sessions": sessions,
        "required_shadow_sessions": config["minimum_shadow_sessions"],
        "activation_status": "blocked_pending_qualified_history_benchmarks_and_manual_review",
        "readiness": {"shadow_minimum_sessions_met": sessions >= config["minimum_shadow_sessions"],
                      "historical_point_in_time_dataset": "not_supplied", "official_benchmark_history": "not_supplied",
                      "corporate_action_adjusted_history": "not_supplied", "out_of_sample_model": "not_trained",
                      "production_activation": False},
        "screen_source": pointer, "research_shadow": screen.get("research_shadow") if screen else None,
        "data_errors": errors, "noon_baseline": noon, **results}
    from .early_model import run_registered
    try:
        summary["early_model_comparison"] = run_registered(root)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        summary["early_model_comparison"] = {"status": "blocked", "reason": str(exc)[:300],
                                            "production_activation": False, "probabilities_enabled": False}
    write_json(state_path, state)
    write_json(tape_index_path, tape_index)
    write_json(root / "output/research/latest/summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("hydrate", "run"), default="run", nargs="?")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = hydrate(args.root) if args.mode == "hydrate" else run(args.root)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
