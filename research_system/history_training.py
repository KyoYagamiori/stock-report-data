"""Historical pilot acquisition -> audited samples -> actual chronological model fit."""
from __future__ import annotations

import argparse
from datetime import datetime
import gzip
import json
from pathlib import Path

from .history_dataset import REMAINING_GAPS, build
from .history_source import BaoStock, TZ, canonical, collect, digest, read_capture, write


def verify_completed(root, status):
    """Reused model results retain their entire source and dataset evidence closure."""
    root = Path(root).resolve()

    def bound(relative, expected):
        path = (root / relative).resolve()
        if not path.is_relative_to(root / "output/history_pilot"):
            raise ValueError("completed_history_evidence_outside_allowed_directory")
        if digest(path.read_bytes()) != expected:
            raise ValueError("completed_history_evidence_hash_mismatch:" + relative)
        return path

    for name in ("dataset", "execution_audit", "source_manifest", "result"):
        bound(status[name + "_file"], status[name + "_sha256"])
    result = json.loads((root / status["result_file"]).read_bytes())
    if result.get("model_status") != status["model_status"]:
        raise ValueError("cached_model_state_mismatch")
    manifest = json.loads(gzip.decompress((root / status["source_manifest_file"]).read_bytes()))
    dataset = json.loads(gzip.decompress((root / status["dataset_file"]).read_bytes()))
    if manifest["config_sha256"] != status["config_sha256"] or dataset["metadata"]["config_sha256"] != status["config_sha256"]:
        raise ValueError("cached_training_config_identity_mismatch")
    for ref in [manifest["membership"], manifest["calendar"], manifest["benchmark"], *manifest["stocks"].values()]:
        read_capture(root, ref)
    provenance = manifest.get("provenance")
    if provenance:
        path = bound(provenance["extraction_receipt_file"], provenance["extraction_receipt_sha256"])
        for ref in json.loads(path.read_bytes())["captured_members"].values():
            bound(ref["file"], ref["sha256"])
    crosscheck = status.get("independent_price_check")
    if crosscheck and "/history_pilot/" in crosscheck["file"]:
        path = bound(crosscheck["file"], crosscheck["sha256"])
        for item in json.loads(path.read_bytes())["results"]:
            if item.get("quote_file"):
                bound(item["quote_file"], item["quote_sha256"])


def run(root, client_factory=None):
    root = Path(root).resolve()
    config = json.loads((root / "config/history_training.json").read_bytes())
    if client_factory is None:
        if config.get("provider") == "qlib_public_release":
            from .history_qlib import QlibRelease
            client_factory = lambda: QlibRelease(root, config)
        elif config.get("provider") == "baostock":
            client_factory = BaoStock
        else:
            raise ValueError("unsupported_historical_provider")
    if config.get("minimum_feature_sessions") != 720 or config.get("locked_holdout_sessions") != 120:
        raise ValueError("pilot_preregistered_history_and_holdout_windows_cannot_be_lowered")
    run_key = digest(canonical(config))[:16]
    archive = root / "output/history_pilot/experiments" / run_key
    archive.mkdir(parents=True, exist_ok=True)
    status = {"schema_version": "1.0", "generated_at": datetime.now(TZ).isoformat(),
        "config_sha256": digest(canonical(config)), "scope": "pilot", "status": "collecting",
        "provider": config["provider"],
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
                verify_completed(root, completed)
                write(receipt_path, completed)
                return completed
        cached = root / "output/history_pilot/source_manifest.json"
        manifest = json.loads(cached.read_bytes()) if cached.exists() else {}
        if manifest.get("config_sha256") != digest(canonical(config)) or not manifest.get("cohort_complete"):
            with client_factory() as client:
                manifest = collect(root, config, client)
        if manifest.get("provider") == "qlib_public_release":
            from .history_qlib import crosscheck_recent
            status["independent_price_check"] = crosscheck_recent(root, manifest)
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
        policy = config.get("evaluation_policy")
        if policy:
            from .history_review import review
            result = review(dataset, policy, scope="pilot")
        else:
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
        if policy:
            status.update(evaluation_mode=result.get("evaluation_mode"),
                development_feature_dates=result.get("development_feature_dates"),
                previously_reviewed_start_date=result.get("previously_reviewed_start_date"),
                previously_reviewed_rows_excluded=result.get("previously_reviewed_rows_excluded"),
                prospective_start_date=result.get("prospective_start_date"), prospective_status=result.get("prospective_status"),
                development_comparison=result.get("development_comparison"),
                deployment_decision=result.get("deployment_decision"), nonpromotion_reasons=result.get("nonpromotion_reasons"),
                next_action="complete_execution_source_audits_and_collect_preregistered_forward_predictions")
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

