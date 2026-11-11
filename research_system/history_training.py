"""Historical pilot acquisition -> audited samples -> actual chronological model fit."""
from __future__ import annotations

import argparse
from datetime import datetime
import gzip
import json
from pathlib import Path

from .history_dataset import REMAINING_GAPS, build
from .history_source import BaoStock, TZ, canonical, collect, digest, write


def run(root, client_factory=BaoStock):
    root = Path(root).resolve()
    config = json.loads((root / "config/history_training.json").read_bytes())
    if config.get("minimum_feature_sessions") != 720 or config.get("locked_holdout_sessions") != 120:
        raise ValueError("pilot_preregistered_history_and_holdout_windows_cannot_be_lowered")
    run_key = digest(canonical(config))[:16]
    archive = root / "output/history_pilot/experiments" / run_key
    archive.mkdir(parents=True, exist_ok=True)
    status = {"schema_version": "1.0", "generated_at": datetime.now(TZ).isoformat(),
        "config_sha256": digest(canonical(config)), "scope": "pilot", "status": "collecting",
        "model_status": "not_trained", "formal_model_status": "not_trained",
        "sample_size": config["sample_size"], "history_start": config["history_start"], "history_end": config["history_end"],
        "production_activation": False, "probabilities_enabled": False, "remaining_gaps": REMAINING_GAPS}
    receipt_path = root / "output/research/latest/history_pilot_status.json"
    write(receipt_path, status)
    try:
        # Reuse an immutable completed experiment; never evaluate a locked holdout twice.
        completed_path = archive / "status.json"
        if completed_path.exists():
            completed = json.loads(completed_path.read_bytes())
            if completed.get("model_status") == "trained_pilot_only":
                model_path = root / completed["result_file"]
                if digest(model_path.read_bytes()) != completed["result_sha256"]:
                    raise ValueError("completed_pilot_result_hash_mismatch")
                write(receipt_path, completed)
                return completed
        cached = root / "output/history_pilot/source_manifest.json"
        manifest = json.loads(cached.read_bytes()) if cached.exists() else {}
        if manifest.get("config_sha256") != digest(canonical(config)) or not manifest.get("cohort_complete"):
            with client_factory() as client:
                manifest = collect(root, config, client)
        dataset, audits, coverage = build(root, manifest)
        status.update(coverage)
        for name, value in (("dataset", dataset), ("execution_audit", audits), ("source_manifest", manifest)):
            path = archive / (name + ".json.gz")
            path.write_bytes(gzip.compress(canonical(value), mtime=0))
            status[name + "_file"] = path.relative_to(root).as_posix()
            status[name + "_sha256"] = digest(path.read_bytes())
        # Validate reference contents, not merely the shape of hash strings.
        by_hash = {a["sha256"]: a["evidence"] for a in audits}
        for row in dataset["rows"]:
            evidence = by_hash[row["execution_audit_sha256"]]
            if digest(canonical(evidence)) != row["execution_audit_sha256"] or evidence["signal_date"] != row["date"]:
                raise ValueError("execution_evidence_identity_mismatch")
        status.update(status="dataset_ready", next_action="chronological_ridge_lightgbm_comparison")
        write(receipt_path, status)
        from .early_model import experiment
        result = experiment(dataset, scope="pilot")
        path = archive / "model_result.json"
        write(path, result)
        status.update(status=result["status"], model_status=result["model_status"],
            result_file=path.relative_to(root).as_posix(), result_sha256=digest(path.read_bytes()),
            selected_model=result.get("selected_model"), final_holdout=result.get("final_holdout"),
            locked_holdout_start=result.get("locked_holdout_start"),
            next_action="expand_historical_universe_and_independently_audit_execution_and_sources"
                if result["model_status"] == "trained_pilot_only" else "increase_fixed_origin_cohort_or_complete_missing_history")
        # A completed pilot is immutable and remains separate from formal registration.
        write(completed_path, status)
    except (ValueError, KeyError, OSError, RuntimeError, ImportError, TypeError) as exc:
        status.update(status="blocked_source_or_dataset", error_type=type(exc).__name__, reason=str(exc)[:400],
            next_action="repair_reported_source_or_dataset_gap_then_resume_cached_requests")
        write(archive / "last_failed_attempt.json", status)
    status["generated_at"] = datetime.now(TZ).isoformat()
    write(receipt_path, status)
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = run(args.root)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
