"""Visible daily-model trial: frozen models, own-data feedback, bounded report reader."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import gzip
import hashlib
import json
import math
from pathlib import Path

from market_screen.early import POOLS
from market_screen.history import TZ, canonical_bytes, write_json
from market_screen.vcp import FEATURES as VCP_FEATURES, feature_values
from .daily_model_data import checked, feedback, load_bars, next_entry, settle, summarize

VERSION = "daily_forward_trial_20261117_v1"
DATA_ERRORS = (ValueError, OSError, KeyError, TypeError)
RUN_ERRORS = (*DATA_ERRORS, ImportError, StopIteration)
# Relative-market fields use incompatible index/median references. Alpha101's
# additive .001 denominator changes with the historical adjustment scale.
# Exclude both rather than silently scoring different definitions.
FEATURES = ("mid_slope_5d_atr", "distance_to_mid_atr", "bandwidth_percentile_120",
    "return_5d_pct", "return_20d_pct", "volume_vs_previous20_median", "signal_age_sessions") + VCP_FEATURES


def immutable(root, path, payload):
    raw = canonical_bytes(payload) + b"\n"
    if path.exists() and path.read_bytes() != raw:
        raise ValueError("refuse_to_replace_frozen_daily_model_evidence")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"file": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}


def load_calendar(root, now):
    value = json.loads((root / "output/cache/trade_calendar.json").read_bytes())
    dates = value["trade_dates"]
    if (dates != sorted(set(dates)) or not value.get("source") or "fallback" in value["source"]
            or not dates[0] <= now.date().isoformat() < dates[-1]):
        raise ValueError("daily_model_calendar_unverified")
    return dates


def ensure_models(root, config, now):
    """Freeze once; new data cannot silently refit an already published model."""
    from .early_model import fit, split, validate
    pointer_path = root / "output/research/daily_model/active_model.json"
    if pointer_path.exists():
        ref = json.loads(pointer_path.read_bytes())
        artifact = json.loads(checked(root, ref, "output/research/daily_model/models"))
        if artifact["version"] != config["version"] or artifact["feature_names"] != list(FEATURES):
            raise ValueError("daily_model_version_requires_explicit_new_registration")
        return ref, artifact
    raw = checked(root, config["training_dataset"], "output/history_pilot/experiments")
    data = json.loads(gzip.decompress(raw))
    rows = validate(data, scope="pilot")
    cutoff = config["exclude_reviewed_from"]
    development = [r for r in rows if r["date"] < cutoff and r["label_end_date"] < cutoff]
    dates = sorted({r["date"] for r in development})
    if len(dates) < config["minimum_development_sessions"]:
        raise ValueError("daily_model_insufficient_development_dates")
    train, valid = split(development, dates, len(dates) - 1)
    if not train or not valid:
        raise ValueError("daily_model_no_purged_training_split")
    models = {kind: fit(kind, train, valid, feature_names=FEATURES) for kind in ("ridge", "lightgbm")}
    artifact = {"version": config["version"], "feature_names": list(FEATURES),
        "model_frozen_at": now.isoformat(), "models": models,
        "training_dataset": config["training_dataset"], "training_cutoff_exclusive": cutoff,
        "development_dates": len(dates), "training_rows": len(train), "validation_rows": len(valid),
        "training_feature_start": min(r["date"] for r in train),
        "training_label_end": max(r["label_end_date"] for r in train),
        "validation_feature_start": min(r["date"] for r in valid),
        "validation_label_end": max(r["label_end_date"] for r in valid),
        "feature_contract": "same_dimensionless_definitions;relative_market_and_scale_sensitive_alpha_excluded",
        "price_basis_gap": "historical_causal_adjusted_vs_live_raw_action_window_requires_review",
        "selection": "fixed_lightgbm_trial_and_ridge_control_no_new_claim_of_superiority",
        "scope": "512_origin_mainboard_pilot_not_full_market_or_intraday_model",
        "probabilities_enabled": False, "automatic_trading": False}
    digest = hashlib.sha256(canonical_bytes(artifact)).hexdigest()
    ref = immutable(root, root / "output/research/daily_model/models" / (digest + ".json"), artifact)
    write_json(pointer_path, ref)
    return ref, artifact


def completed_market_date(calendar, now):
    return next((day for day in reversed(calendar)
                 if datetime.fromisoformat(day + "T15:00:00+08:00") <= now), None)


def screen_pointers(root, target, now):
    """Bounded references for one completed session, including legacy manifests."""
    try:
        manifest = json.loads((root / "output/boll/latest/manifest.json").read_bytes())
    except (OSError, ValueError):
        manifest = {}
    for key in ("latest_completed_daily_screen", "latest_complete_screen", "latest_screen"):
        pointer = manifest.get(key) if isinstance(manifest, dict) else None
        if (isinstance(pointer, dict) and pointer.get("market_date", target) == target
                and pointer.get("phase", "early") in {"early", "close"}
                and isinstance(pointer.get("selected_file"), str) and pointer.get("sha256")):
            yield pointer
    # Before the producer publishes its independent pointer, reuse the exact
    # same-session input of the last successful model run and recheck its bytes.
    try:
        prior = json.loads((root / "output/research/latest/daily_model_status.json").read_bytes())
        if prior["market_date"] == target and datetime.fromisoformat(prior["published_at"]) <= now:
            source = prior["source"]
            yield {"selected_file": source["screen_file"], "sha256": source["screen_sha256"]}
    except DATA_ERRORS:
        return


def load_queue(root, now, calendar):
    target = completed_market_date(calendar, now)
    errors = []
    for pointer in screen_pointers(root, target, now):
        try:
            screen = json.loads(checked(root, pointer, "output/boll/archive"))
            validate_completed_screen(screen, now)
            if screen["market_date"] != target:
                raise ValueError("daily_model_daily_baseline_stale:" + screen["market_date"])
        except DATA_ERRORS as exc:
            errors.append(str(exc))
            continue
        break
    else:
        detail = ("; " + errors[0]) if errors else ""
        raise ValueError(f"daily_model_requires_completed_verified_daily_screen:{target}{detail}")
    source = screen["early_signals"]
    ref = {"file": source["reader_file"], "sha256": source["reader_sha256"]}
    queue = json.loads(checked(root, ref, "output/boll/archive"))
    if (queue["market_date"] != screen["market_date"] or queue["phase"] != screen["phase"]
            or queue.get("published_at") != screen["published_at"]):
        raise ValueError("daily_model_queue_identity_mismatch")
    # Report queues retain pool code lists, not all duplicate feature rows.
    # Reconstitute only those bounded candidates from producer record shards.
    wanted = {code for codes in queue.get("pool_codes", {}).values() for code in codes}
    if len(wanted) > 80:
        raise ValueError("daily_model_source_candidate_budget_exceeded")
    records = {}
    for source_ref in screen.get("record_shards", []):
        stem = Path(source_ref["file"]).stem
        low, high = stem.split("-")
        if not any(low <= code <= high for code in wanted):
            continue
        part = json.loads(checked(root, source_ref, "output/boll/archive"))
        if len(part["records"]) != source_ref["count"]:
            raise ValueError("daily_model_record_count_mismatch")
        for row in part["records"]:
            if row["code"] in wanted:
                if row["code"] in records or row["market_date"] != screen["market_date"]:
                    raise ValueError("daily_model_record_identity_mismatch")
                records[row["code"]] = row
    if set(records) != wanted:
        raise ValueError("daily_model_candidate_records_missing")
    for row in records.values():
        indicators = row.get("indicators") or {}
        if (indicators.get("bar_date") != screen["market_date"]
                or not indicators.get("history_current")
                or indicators.get("last_bar", {}).get("day") != screen["market_date"]
                or indicators.get("early_state", {}).get("asof") != screen["market_date"]
                or not indicators.get("early_state", {}).get("points")
                or indicators["early_state"]["points"][-1].get("day") != screen["market_date"]):
            raise ValueError("daily_model_candidate_daily_date_mismatch")
    from market_screen.early import build
    settings = json.loads((root / "config/early_signals.json").read_bytes())
    rebuilt = build(list(records.values()), {"phase": "close", "market_date": screen["market_date"],
        "report_date": screen["report_date"]}, now, settings)
    evaluated = {r["code"]: r for r in rebuilt["evaluations"]}
    queue["pools"] = {p: [evaluated[code] for code in codes] for p, codes in queue.get("pool_codes", {}).items()}
    return queue, {**ref, "published_at": screen["published_at"],
        "screen_file": pointer["selected_file"], "screen_sha256": pointer["sha256"],
        "producer_phase": screen["phase"], "bar_contract": "completed_1500_daily_not_intraday"}, screen


def validate_completed_screen(screen, now):
    """The producer's early role can publish completed daily bars after 15:00.

    Its role label is not bar status. Require the exact completed daily cutoff,
    publication after that cutoff and all-code accounting; never accept overlays.
    """
    cutoff = datetime.fromisoformat(screen["market_date"] + "T15:00:00+08:00")
    published = datetime.fromisoformat(screen["published_at"])
    if (screen.get("phase") not in {"early", "close"}
            or not screen.get("technical_screen_complete") or screen.get("unresolved_count") != 0
            or not screen.get("all_codes_accounted_for")
            or screen.get("market_cutoff") != cutoff.isoformat()
            or published.tzinfo is None or not cutoff <= published <= now):
        raise ValueError("daily_model_requires_completed_verified_daily_screen")


def candidates(queue, config):
    rows, rejections, seen = [], Counter(), set()
    for pool in POOLS:
        for row in queue.get("pools", {}).get(pool, []):
            if row["code"] in seen:
                continue
            seen.add(row["code"])
            if not row["code"].startswith(("00", "60")):
                rejections["outside_historical_mainboard_scope"] += 1
                continue
            if row.get("band_status") != "completed" or not row.get("structure_eligible"):
                rejections["unfinished_or_ineligible_structure"] += 1
                continue
            setup = next((s for s in row["setups"] if s["pool"] == pool), None)
            if setup is None:
                rejections["missing_setup_identity"] += 1
                continue
            features = {**row["features"], **feature_values(row.get("vcp_shadow", {})),
                        "signal_age_sessions": setup["signal_age_sessions"]}
            if any(isinstance(features.get(f), bool) or not isinstance(features.get(f), (int, float))
                   or not math.isfinite(features[f]) for f in FEATURES):
                rejections["incomplete_model_features"] += 1
                continue
            # The historical extractor requires evaluable VCP observations too.
            if not row.get("vcp_shadow", {}).get("available"):
                rejections["vcp_feature_state_missing"] += 1
                continue
            rows.append({"code": row["code"], "name": row.get("name"), "date": queue["market_date"],
                "setup": setup["pool"], "origin": setup["origin"], "features": {f: features[f] for f in FEATURES},
                "price": row["price"], "price_asof": row["price_asof"], "stage": row["stage"],
                "vcp_stage": row["vcp_shadow"]["stage"], "exit_plan": row.get("exit_plan"),
                "source_gaps": row.get("evidence_gaps", []), "target_t3_net_excess_pct": 0})
    if len(rows) > config["maximum_candidates"]:
        raise ValueError("daily_model_candidate_budget_exceeded")
    return rows, dict(rejections), len(seen)


def score_rows(rows, artifact):
    from .early_model import predictions
    if not rows:
        return []
    for kind in ("ridge", "lightgbm"):
        scores = predictions(artifact["models"][kind], rows)
        for row, value in zip(rows, scores):
            if not math.isfinite(value):
                raise ValueError("daily_model_nonfinite_score")
            row.setdefault("scores", {})[kind] = float(value)
    for pool in POOLS:
        group = [r for r in rows if r["setup"] == pool]
        for kind in ("ridge", "lightgbm", "early_rule"):
            ordered = sorted(group, key=(lambda r: (r["features"]["signal_age_sessions"],
                abs(r["features"]["distance_to_mid_atr"]), r["code"])) if kind == "early_rule" else
                (lambda r: (-r["scores"][kind], r["code"])))
            for rank, row in enumerate(ordered, 1):
                row.setdefault("ranks", {})[kind] = rank
                if rank == 1:
                    row.setdefault("selected_by", []).append(kind)
    return rows


def register(root, rows, state, model_ref, queue_ref, calendar, now, config):
    episodes = state.setdefault("episodes", {})
    entry = next_entry(calendar, now, config["minimum_publication_lead_minutes"])
    expiry = calendar[calendar.index(entry) + config["valid_sessions"] - 1] + "T15:00:00+08:00"
    cohort = hashlib.sha256(canonical_bytes([model_ref["sha256"], queue_ref["sha256"], now.isoformat()])).hexdigest()[:24]
    new = []
    for row in rows:
        key = hashlib.sha256(canonical_bytes([model_ref["sha256"], row["code"], row["setup"], row["origin"]])).hexdigest()[:24]
        if key not in episodes:
            ep = {"signal_id": key, "model_sha256": model_ref["sha256"], "cohort_id": cohort,
                "code": row["code"], "name": row["name"], "setup": row["setup"], "origin": row["origin"],
                "feature_date": row["date"], "features": row["features"], "scores": row["scores"], "ranks": row["ranks"],
                "selected_by": row.get("selected_by", []), "prediction_registered_at": now.isoformat(),
                "feature_source": queue_ref, "entry_date": entry, "valid_until": expiry,
                "entry_rule": "next_eligible_session_open_after_registration_plus_30min_daily_price_proxy",
                "observation_only": True, "real_trade": False, "outcomes": {},
                "reference_price": row["price"], "exit_plan": row["exit_plan"]}
            ref = immutable(root, root / "output/research/daily_model/predictions" / (key + ".json"), ep)
            ep["prediction_file"] = ref
            episodes[key] = ep
            new.append(key)
        ep = episodes[key]
        row["original_prediction"] = {k: ep[k] for k in ("signal_id", "prediction_registered_at", "valid_until", "entry_date")}
        row["original_scores"] = ep["scores"]
        row["exit_plan"] = ep["exit_plan"]
        row["active"] = now <= datetime.fromisoformat(ep["valid_until"])
    return new


def publish_failure(root, exc, now, **details):
    result = {"status": "blocked", "reason": str(exc)[:400], "checked_at": now.isoformat(),
              "automatic_trading": False, "probabilities_enabled": False, **details}
    write_json(root / "output/research/latest/daily_model_last_failure.json", result)
    return result


def run(root, now=None):
    root = Path(root).resolve()
    now = now or datetime.now(TZ)
    if now.tzinfo is None:
        raise ValueError("daily_model_timezone_required")
    now = now.astimezone(TZ)
    config = json.loads((root / "config/daily_model.json").read_bytes())
    calendar = load_calendar(root, now)
    state_path = root / "output/research/daily_model/state.json"
    state = json.loads(state_path.read_bytes()) if state_path.exists() else {"version": VERSION, "episodes": {}}
    verify_predictions(root, state["episodes"], now)
    for ep in state["episodes"].values():
        if datetime.fromisoformat(ep["prediction_registered_at"]) > now:
            raise ValueError("daily_model_prediction_registered_in_future")
    scoring_error = None
    needed = {ep["code"] for ep in state["episodes"].values()}
    try:
        queue, queue_ref, screen = load_queue(root, now, calendar)
        model_ref, artifact = ensure_models(root, config, now)
        if datetime.fromisoformat(artifact["model_frozen_at"]) > now:
            raise ValueError("daily_model_model_frozen_in_future")
        rows, rejections, pool_size = candidates(queue, config)
        # The frozen scoring path has no access to forward label data.
        rows = score_rows(rows, artifact)
        needed.update(row["code"] for row in rows)
    except RUN_ERRORS as exc:
        scoring_error = exc
    histories, own_ref = load_bars(root, needed, now)
    if scoring_error is None:
        new = register(root, rows, state, model_ref, queue_ref, calendar, now, config)
    settle(state["episodes"], histories, calendar, now, config, own_ref)
    results = summarize(state["episodes"])
    samples = feedback(state["episodes"])
    feedback_path = root / "output/research/daily_model/feedback/samples.jsonl.gz"
    feedback_path.parent.mkdir(parents=True, exist_ok=True)
    feedback_path.write_bytes(gzip.compress(b"".join(canonical_bytes(r) + b"\n" for r in samples), mtime=0))
    write_json(state_path, state)
    if scoring_error is not None:
        return publish_failure(root, scoring_error, now, settlement={
            "status": "completed", "history_market_date": own_ref["market_date"],
            "unique_prediction_count": len(state["episodes"]), "matured_feedback_rows": len(samples),
            "outcomes": {h: item["states"] for h, item in results["horizons"].items()},
        })
    active = [r for r in rows if r["active"]]
    active.sort(key=lambda r: (r["ranks"][config["primary_model"]], POOLS.index(r["setup"]), r["code"]))
    watch = [{**{k: r[k] for k in ("code", "name", "setup", "stage", "price", "price_asof", "vcp_stage",
        "scores", "ranks", "original_scores", "original_prediction", "exit_plan")},
        "signal_age_sessions": r["features"]["signal_age_sessions"],
        "distance_to_mid_atr": r["features"]["distance_to_mid_atr"],
        "source_gaps": r["source_gaps"]} for r in active[:config["reader_limit"]]]
    receipt = {"schema_version": "1.0", "version": VERSION, "mode": "visible_daily_report_trial",
        "generated_at": now.isoformat(), "published_at": now.isoformat(), "market_date": screen["market_date"],
        "phase": "completed_daily_model", "model": model_ref, "model_frozen_at": artifact["model_frozen_at"],
        "source": queue_ref, "own_data": own_ref, "model_status": "trained_and_running_daily_trial",
        "coverage": {"source_early_pool_codes": pool_size, "scored_codes": len(rows), "rejections": rejections,
            "source_daily_universe": screen["universe_count"], "full_market_model_scoring": False,
            "scope": config["score_scope"]},
        "score_meaning": "uncalibrated_research_ranking_not_probability_or_promised_expected_return",
        "publication_note": "published_at_is_generation_time;public_availability_verified_on_next_repository_read_before_entry",
        "feature_contract": artifact["feature_contract"], "price_basis_gap": artifact["price_basis_gap"],
        "new_predictions": len(new), "unique_prediction_count": len(state["episodes"]),
        "matured_feedback_rows": len(samples), "forward_results": results,
        "shortlist": watch, "expired_suppressed": len(rows) - len(active),
        "report_use": "show_model_and_rule_rank_side_by_side_with_entry_and_exit_conditions;daily_scores_only_at_noon",
        "intraday_model_status": "not_trained_no_intraday_prediction_claim",
        "automatic_trading": False, "probabilities_enabled": False,
        "formal_production_promotion": False, "automatic_retraining": False,
        "next_action": "settle_future_1_3_5_session_prices_and_review_frozen_versions;benchmark_and_execution_audit_before_refit"}
    # Every report can recover its exact cutoff from a small immutable version.
    run_id = now.strftime("%Y%m%dT%H%M%S%f")
    ref = immutable(root, root / "output/research/daily_model/readers" / (run_id + ".json"), receipt)
    pointer = {**ref, "market_date": receipt["market_date"], "published_at": receipt["published_at"], "phase": receipt["phase"]}
    manifest_path = root / "output/research/latest/daily_model_manifest.json"
    manifest = json.loads(manifest_path.read_bytes()) if manifest_path.exists() else {"schema_version": "1.0", "daily": {}}
    manifest["latest"] = pointer
    manifest["daily"][receipt["market_date"]] = pointer
    manifest["daily"] = dict(sorted(manifest["daily"].items())[-10:])
    write_json(manifest_path, manifest)
    write_json(root / "output/research/latest/daily_model_status.json", {k: v for k, v in receipt.items() if k != "shortlist"})
    return {"status": "running", **pointer, "scored_codes": len(rows), "new_predictions": len(new),
            "unique_prediction_count": len(state["episodes"]), "matured_feedback_rows": len(samples)}


def verify_predictions(root, episodes, now):
    """Check frozen records and conservatively prove availability before entry."""
    import subprocess
    for ep in episodes.values():
        ref = ep["prediction_file"]
        frozen = json.loads(checked(root, ref, "output/research/daily_model/predictions"))
        if any(ep.get(k) != value for k, value in frozen.items() if k != "outcomes"):
            raise ValueError("daily_model_registered_prediction_was_modified")
        if ep.get("public_available_by"):
            continue
        result = subprocess.run(["git", "show", "HEAD:" + ref["file"]], cwd=root, capture_output=True)
        if result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == ref["sha256"]:
            ep["public_available_by"] = now.isoformat()
            ep["public_availability_commit"] = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def hydrate(root):
    """Only referenced current source versions, frozen model and rolling own history."""
    from market_screen.workflow_io import archive_directory
    root = Path(root).resolve()
    patterns = {"/output/boll/bootstrap/"}
    if not (root / "output/research/daily_model/active_model.json").exists():
        config = json.loads((root / "config/daily_model.json").read_bytes())
        patterns.add("/" + config["training_dataset"]["file"])
    now = datetime.now(TZ)
    target = completed_market_date(load_calendar(root, now), now)
    for pointer in screen_pointers(root, target, now):
        try:
            patterns.add(archive_directory(pointer["selected_file"]))
        except ValueError:
            continue
    import subprocess
    sparse = subprocess.run(["git", "config", "--bool", "core.sparseCheckout"], cwd=root, capture_output=True, text=True)
    if sparse.stdout.strip() == "true":
        subprocess.run(["git", "sparse-checkout", "add", "--stdin"], input="\n".join(sorted(patterns)) + "\n", cwd=root, text=True, check=True)
    return sorted(patterns)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("hydrate", "run"), default="run", nargs="?")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if args.mode == "hydrate":
        print(json.dumps(hydrate(args.root)))
        return 0
    try:
        result = run(args.root)
    except RUN_ERRORS as exc:
        result = publish_failure(args.root, exc, datetime.now(TZ))
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
