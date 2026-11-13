"""Audit VCP's incremental contribution on the exact expanded BOLL candidate cohort."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime
import gzip
import json
from pathlib import Path

from market_screen import vcp
from .early_model import FEATURES, MODELS, block_interval, fit
from .history_dataset import causal_adjust, normalize
from .history_review import review
from .history_source import TZ, canonical, digest, read_capture, write
from .history_training import verify_completed


def augment(root, data, manifest):
    result = deepcopy(data)
    groups = {}
    for row in result["rows"]:
        groups.setdefault(row["code"], []).append(row)
    counts = Counter()
    for source_code, reference in manifest["stocks"].items():
        code = source_code.split(".")[1]
        if code not in groups:
            continue
        adjusted = causal_adjust(normalize(read_capture(root, reference)["rows"], allow_unknown_status=True))
        indices = {b["day"]: i for i, b in enumerate(adjusted)}
        for row in groups[code]:
            i = indices[row["date"]]
            # The extractor receives no bar later than the feature date.
            observed = vcp.analyze(adjusted[max(0, i-120):i+1])
            row["features"].update(vcp.feature_values(observed))
            row["vcp_shadow"] = {k: observed.get(k) for k in ("version", "stage", "available", "matched", "origin",
                "pivot", "invalidation_below", "distance_to_pivot_atr", "contraction_depths_pct", "dry_volume_ratio")}
            counts[observed["stage"]] += 1
    if any(any(f not in row["features"] for f in vcp.FEATURES) for row in result["rows"]):
        raise ValueError("incomplete_vcp_feature_augmentation")
    result["metadata"].update(vcp_feature_version=vcp.VERSION, vcp_policy=vcp.POLICY,
        vcp_scope="incremental_features_within_existing_early_candidate_cohort_not_full_vcp_strategy")
    return result, dict(counts)


def ablation(base, enhanced):
    comparison = {}
    for kind in MODELS:
        before = {r["date"]: r for r in base["out_of_fold_daily_results"][kind]}
        after = {r["date"]: r for r in enhanced["out_of_fold_daily_results"][kind]}
        if set(before) != set(after):
            raise ValueError("vcp_ablation_requires_identical_test_dates")
        delta = [after[d]["net_excess_pct"] - before[d]["net_excess_pct"] for d in sorted(before)]
        import statistics
        comparison[kind] = {"paired_signal_dates": len(delta),
            "mean_incremental_net_excess_pct": statistics.mean(delta) if delta else None,
            "incremental_5_signal_date_block_95_interval": block_interval(delta),
            "without_vcp": base["development_comparison"][kind]["rolling_test"],
            "with_vcp": enhanced["development_comparison"][kind]["rolling_test"]}
    return {"models": comparison, "selection": "descriptive_ablation_not_used_to_activate_or_tune_thresholds",
            "cohort": "same_stock_date_setup_cost_and_execution_assumptions",
            "independent_final_test": False, "production_activation": False}


def run(root):
    root = Path(root).resolve()
    config = json.loads((root / "config/history_training.json").read_bytes())
    status_path = root / "output/research/latest/vcp_pilot_status.json"
    status = {"generated_at": datetime.now(TZ).isoformat(), "feature_version": vcp.VERSION,
              "model_status": "not_trained", "status": "building_vcp_review", "production_activation": False,
              "probabilities_enabled": False, "parameter_ownership": "our_preregistered_proxy_not_jlaw_exact_rules"}
    try:
        source_status = json.loads((root / "output/research/latest/history_pilot_status.json").read_bytes())
        if source_status["config_sha256"] != digest(canonical(config)) or source_status.get("model_status") != "trained_pilot_only":
            raise ValueError("vcp_requires_completed_current_expanded_experiment")
        verify_completed(root, source_status)
        manifest = json.loads(gzip.decompress((root / source_status["source_manifest_file"]).read_bytes()))
        data = json.loads(gzip.decompress((root / source_status["dataset_file"]).read_bytes()))
        base = json.loads((root / source_status["result_file"]).read_bytes())
        identity = digest(canonical({"base_result_sha256": source_status["result_sha256"],
            "policy": vcp.POLICY, "features": vcp.FEATURES, "version": vcp.VERSION,
            "feature_code_sha256": digest(Path(vcp.__file__).read_bytes()),
            "review_code_sha256": digest(Path(__file__).read_bytes())}))
        directory = (root / source_status["result_file"]).parent / "vcp" / identity[:16]
        directory.mkdir(parents=True, exist_ok=True)
        if "out_of_fold_daily_results" not in base:
            # Older archives saved summaries only. Replay the identical frozen
            # experiment to recover paired daily observations, not a new trial.
            recovered = review(data, config["evaluation_policy"])
            if (recovered["selected_model"] != base["selected_model"] or
                    recovered["validation_comparison"] != base["validation_comparison"]):
                raise ValueError("baseline_daily_replay_did_not_reproduce_frozen_selection")
            write(directory / "baseline_daily_replay.json", recovered)
            base = recovered
        enhanced, stages = augment(root, data, manifest)
        dataset_path = directory / "dataset.json.gz"
        dataset_path.write_bytes(gzip.compress(canonical(enhanced), mtime=0))
        fitter = lambda kind, train, valid: fit(kind, train, valid, feature_names=FEATURES + vcp.FEATURES)
        result = review(enhanced, config["evaluation_policy"], fitter=fitter)
        comparison = ablation(base, result)
        path = directory / "model_result.json"
        write(path, result)
        status.update(status="vcp_shadow_ablation_completed_not_production_qualified", model_status=result["model_status"],
            sample_size=config["sample_size"], training_rows=len(enhanced["rows"]), feature_dates=result["feature_dates"],
            selected_model=result["selected_model"], feature_stage_counts=stages, ablation=comparison,
            source_experiment_file=source_status["result_file"], source_experiment_sha256=source_status["result_sha256"],
            dataset_file=dataset_path.relative_to(root).as_posix(), dataset_sha256=digest(dataset_path.read_bytes()),
            result_file=path.relative_to(root).as_posix(), result_sha256=digest(path.read_bytes()),
            prospective_status=result["prospective_status"], prospective_start_date=result["prospective_start_date"],
            deployment_decision="retain_existing_early_rules_vcp_observation_only",
            limitations=["same_boll_cohort_only_not_full_universe_vcp_entry_backtest", "not_a_jlaw_performance_replication",
                         "historical_st_limits_corporate_actions_and_benchmark_not_fully_audited",
                         "retrospective_development_review_not_independent_final_test"])
        write(directory / "status.json", status)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, ImportError) as exc:
        status.update(status="blocked_vcp_source_or_review", reason=str(exc)[:400], error_type=type(exc).__name__)
    write(status_path, status)
    return status


if __name__ == "__main__":
    print(json.dumps(run(Path(__file__).resolve().parents[1]), ensure_ascii=False), flush=True)
