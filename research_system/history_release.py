"""Concrete promotion checks. Training completion never means production approval."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import statistics

from .early_model import block_interval
from .history_source import TZ,canonical,digest,write
from .history_training import verify_completed


def check_performance(result, policy):
    kind=result["selected_model"]
    stats=result["development_comparison"][kind]
    costs=stats["diagnostics"]["round_trip_cost_bps_sensitivity"]
    days=result["out_of_fold_daily_results"][kind]
    net_interval=block_interval([r["net_excess_pct"] for r in days])
    delta_interval=block_interval([r["paired_improvement_pct"] for r in days])
    fold_values=[f["models"][kind]["paired_early_rule_improvement_pct"] for f in result["rolling_folds"]]
    fraction=sum(v>0 for v in fold_values)/len(fold_values) if fold_values else 0
    checks={"positive_at_all_required_costs":all(costs[str(b)]["date_balanced_mean_net_excess_pct"]>policy["minimum_net_excess_pct"] for b in policy["required_round_trip_cost_bps"]),
            "positive_net_interval_lower_bound":net_interval is not None and net_interval[0]>0,
            "positive_improvement_interval_lower_bound":delta_interval is not None and delta_interval[0]>policy["minimum_improvement_interval_lower_pct"],
            "rolling_improvement_consistency":fraction>=policy["minimum_rolling_positive_improvement_fraction"]}
    return {"state":"passed" if all(checks.values()) else "failed", "checks":checks,
            "positive_fold_fraction":fraction,"net_5_signal_date_block_95_interval":net_interval,
            "improvement_5_signal_date_block_95_interval":delta_interval,
            "cost_means_pct":{str(b):costs[str(b)]["date_balanced_mean_net_excess_pct"] for b in policy["required_round_trip_cost_bps"]},
            "scope":"retrospective_development_screen_not_independent_final_test"}


def load_evidence(root, registration, key, candidate):
    ref=registration.get(key)
    if not ref:return None
    path=(root/ref["file"]).resolve()
    if not path.is_relative_to(root/"output/research/release_evidence") or digest(path.read_bytes())!=ref["sha256"]:
        raise ValueError("release_evidence_path_or_hash_invalid:"+key)
    value=json.loads(path.read_bytes())
    if value.get("candidate_sha256")!=candidate:
        raise ValueError("release_evidence_belongs_to_another_model:"+key)
    # A reviewed summary must retain actual source artifacts, not just passed flags.
    if not value.get("source_refs"):raise ValueError("release_evidence_has_no_source_artifacts:"+key)
    for source in value["source_refs"]:
        p=(root/source["file"]).resolve()
        if not p.is_relative_to(root/"output/research/release_evidence") or digest(p.read_bytes())!=source["sha256"]:
            raise ValueError("release_source_artifact_invalid:"+key)
    return value


def check_forward(forward, policy, now):
    days=forward.get("daily_results",[])
    dates=[r["date"] for r in days]
    if dates!=sorted(set(dates)):raise ValueError("forward_dates_not_unique_and_ordered")
    frozen=datetime.fromisoformat(forward["model_frozen_at"])
    for row in days:
        issued=datetime.fromisoformat(row["prediction_registered_at"])
        features=datetime.fromisoformat(row["features_known_at"])
        entry=datetime.fromisoformat(row["entry_at"])
        known=datetime.fromisoformat(row["outcome_known_at"])
        if any(t.tzinfo is None for t in (frozen,issued,features,entry,known)) or not frozen<=issued<entry<known<=now or features>issued or issued.date().isoformat()!=row["date"]:
            raise ValueError("forward_prediction_time_chain_invalid")
    matured=sum(r.get("matured_signals",0) for r in days)
    mature_dates=sum(r.get("matured_signals",0)>0 for r in days)
    ci=block_interval([r["net_excess_pct"]-r["baseline_net_excess_pct"] for r in days])
    valid=len(days)>=policy["minimum_forward_sessions"] and matured>=policy["minimum_matured_signals"] and mature_dates>=policy["minimum_matured_signal_dates"] and ci is not None and ci[0]>0
    valid=valid and forward.get("previously_inspected_dates_used") is False and forward.get("unresolved_exit_count")==0
    return {"state":"passed" if valid else "failed","sessions":len(days),"matured_signals":matured,"matured_signal_dates":mature_dates,"improvement_95_interval":ci,
            "operations_20_sessions_met":len(days)>=policy["operational_forward_sessions"]}


def run(root):
    root=Path(root).resolve()
    policy=json.loads((root/"config/model_release_policy.json").read_bytes())
    gates={}
    out={"generated_at":datetime.now(TZ).isoformat(),"policy_version":policy["version"],"gates":gates,
         "production_activation":False,"ready_for_assisted_ranking_review":False,
         "legacy_midline_rule_enabled":False,"policy":policy}
    try:
        base=json.loads((root/"output/research/latest/history_pilot_status.json").read_bytes())
        verify_completed(root,base)
        v=json.loads((root/"output/research/latest/vcp_pilot_status.json").read_bytes())
        if v["source_experiment_sha256"]!=base["result_sha256"]:raise ValueError("release_model_generation_mismatch")
        candidate=v["result_sha256"]
        path=(root/v["result_file"]).resolve()
        if not path.is_relative_to(root/"output/history_pilot") or digest(path.read_bytes())!=candidate:
            raise ValueError("release_model_artifact_hash_mismatch")
        result=json.loads(path.read_bytes())
        out.update(candidate_sha256=candidate,selected_model=result["selected_model"],sample_size=base["sample_size"],training_rows=base["training_rows"])
        enough=base["sample_size"]>=policy["minimum_training_codes"] and result["development_feature_dates"]>=policy["minimum_development_feature_dates"]
        gates["training_and_artifacts"]={"state":"passed" if enough else "failed","development_feature_dates":result["development_feature_dates"]}
        gates["cost_and_stability"]=check_performance(result,policy)
        reg_path=root/"config/model_release_evidence.json"
        reg=json.loads(reg_path.read_bytes()) if reg_path.exists() else {}
        audit=load_evidence(root,reg,"source_and_execution_review",candidate)
        required={"historical_universe_scope","official_benchmark","corporate_actions","historical_ST_halts_limits","live_feature_parity","T_plus_1_and_gap_fills","portfolio_overlap_cash_and_drawdown"}
        good=bool(audit) and required<=set(audit.get("verified_checks",[])) and audit.get("unresolved_exit_count") == 0 and audit.get("max_drawdown_increase_pct",float("inf"))<=policy["maximum_drawdown_increase_pct"]
        gates["source_execution_and_portfolio_risk"]={"state":"passed" if good else "failed" if audit else "missing",
            "missing_checks":sorted(required-set((audit or {}).get("verified_checks",[])))}
        forward=load_evidence(root,reg,"sealed_forward_review",candidate)
        if forward:
            gates["sealed_forward_validation"]=check_forward(forward,policy,datetime.now(TZ))
        else:gates["sealed_forward_validation"]={"state":"missing","reason":"need_real_frozen_model_predictions_and_matured_outcomes; elapsed_time_alone_is_not_evidence"}
        exits_path=root/"output/research/latest/exit_policy_status.json"
        exits=json.loads(exits_path.read_bytes()) if exits_path.exists() else {}
        current=exits.get("source_model_sha256")==candidate and exits.get("status")=="exit_policy_replay_completed_research_only"
        x=exits.get("result",{})
        xci=x.get("paired_5_signal_date_block_95_interval")
        censored=sum(n for name,n in x.get("state_counts",{}).items() if name.startswith("censored"))
        exit_ok=current and xci is not None and xci[0]>0 and censored==0 and all(x.get("round_trip_cost_bps_sensitivity",{}).get(str(b),float("-inf"))>0 for b in policy["required_round_trip_cost_bps"])
        gates["exit_policy_replay"]={"state":"passed" if exit_ok else "failed" if current else "missing",
                                    "research_replay_completed":current,"reference_levels_available":True,
                                    "unresolved_or_censored_paths":censored,"live_execution_approved":False}
        out["ready_for_assisted_ranking_review"]=all(g["state"]=="passed" for g in gates.values())
        out["status"]="ready_for_assisted_ranking_review" if out["ready_for_assisted_ranking_review"] else "blocked_pending_evidence_or_performance"
    except (ValueError,KeyError,TypeError,OSError,ImportError) as exc:
        out.update(status="blocked_release_check",reason=str(exc)[:400])
    write(root/"output/research/latest/model_release_status.json",out)
    return out


if __name__=="__main__":
    print(json.dumps(run(Path(__file__).resolve().parents[1]),ensure_ascii=False),flush=True)
