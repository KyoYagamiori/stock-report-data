"""Matched-entry exit-policy replay; daily proxies cannot establish broker fills or portfolio PnL."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import gzip
import json
from pathlib import Path
import statistics

from market_screen.exits import VERSION, POLICY, create_plan, initial_state, assess, record_fill
from .early_model import block_interval
from .history_dataset import causal_adjust, normalize
from .history_source import TZ, canonical, digest, read_capture, write
from .history_training import verify_completed


def atr20(bars, i):
    values = [max(bars[j]["high"]-bars[j]["low"], abs(bars[j]["high"]-bars[j-1]["close"]),
                  abs(bars[j]["low"]-bars[j-1]["close"])) for j in range(max(1, i-19), i+1)]
    return statistics.mean(values)


VARIANTS={"defense_and_profit":{"time_stop_action":"review"},
          "hard_time_stop_comparison":{"time_stop_action":"exit_all"},
          "structure_only_comparison":{"time_stop_action":"review","protect_after_r":1e9,"partial_at_r":1e9}}


def replay(row, raw, adjusted, calendar, benchmark, cutoff, horizon=10, policy_override=None):
    day, code = row["date"], row["code"]
    t = calendar.index(day)
    if t + 1 + horizon >= len(calendar) or calendar[t+1+horizon] >= cutoff:
        return {"state": "immature_or_cross_review_boundary", "date": day, "code": code}
    if row["execution_state"] == "unfilled_cash_zero":
        return {"state": "unfilled", "date": day, "code": code, "net_excess_pct": 0., "fixed3_pct": 0., "filled": False}
    raw_map, adj_map = {b["day"]: b for b in raw}, {b["day"]: b for b in adjusted}
    indices = {b["day"]: i for i, b in enumerate(adjusted)}
    index = indices[day]
    entry_day = calendar[t+1]
    if entry_day not in adj_map or entry_day not in benchmark:
        return {"state": "missing_entry", "date": day, "code": code}
    entry = adj_map[entry_day]["open"]
    atr = atr20(adjusted, index)
    vcp = row.get("vcp_shadow", {})
    low = vcp.get("invalidation_below") if vcp.get("matched") else min(b["low"] for b in adjusted[max(0,index-4):index+1])
    pivot = vcp.get("pivot") if vcp.get("matched") and entry >= vcp["pivot"] else None
    try:
        plan = create_plan(entry, low, atr, pivot=pivot, entry_date=entry_day, policy=policy_override)
    except ValueError:
        return {"state": "invalid_before_entry", "date": day, "code": code,
                "net_excess_pct": 0., "fixed3_pct": 0., "filled": False}
    state, pending, fills, adverse = initial_state(plan), None, [], 0.
    for held in range(horizon+1):
        current_day = calendar[t+1+held]
        b, r, ix = adj_map.get(current_day), raw_map.get(current_day), benchmark.get(current_day)
        if b is None or r is None or ix is None:
            return {"state": "censored_missing_path", "date": day, "code": code, "at": current_day}
        can_sell = (r["tradestatus"] == "1" and r["volume"] > 0 and r["high"] != r["low"]
                    and r["open"] / r["preclose"] > .905 and r["close"] / r["preclose"] > .905)
        # A stop observed on a completed daily bar is executed no earlier than the next open.
        if held > 0 and pending and can_sell:
            fraction = min(pending["fraction_of_original"], state["remaining_fraction"])
            fills.append({"date": current_day, "price": b["open"], "fraction": fraction,
                          "benchmark_price": ix["open"], "reason": pending["reason"], "clock": "open"})
            state = record_fill(state, fraction)
            pending = None
            if state["remaining_fraction"] <= 1e-9:
                break
        adverse = min(adverse, (b["low"] / entry - 1) * 100)
        prior_stop = state["stop"]
        decision = assess(plan, state, b, holding_sessions=held, atr=atr20(adjusted, indices[current_day]))
        state = decision["state"]
        if b["low"] <= prior_stop:
            decision = {**decision, "action": "exit_all", "reason": "preexisting_stop_touched_daily_next_open_proxy",
                        "fraction_of_original": state["remaining_fraction"]}
        if decision["action"] in {"exit_all", "reduce"}:
            # Full risk exits outrank a pending partial-profit request.
            if pending is None or decision["action"] == "exit_all":
                pending = decision
        if held == horizon and state["remaining_fraction"] > 0:
            if not can_sell:
                return {"state": "censored_unresolved_exit", "date": day, "code": code}
            fills.append({"date": current_day, "price": b["close"], "fraction": state["remaining_fraction"],
                          "benchmark_price": ix["close"], "reason": "study_horizon_liquidation_not_live_rule", "clock": "close"})
            state = record_fill(state, state["remaining_fraction"])
    cost = row["round_trip_cost_bps_assumption"] / 100
    gross = sum(f["fraction"] * (f["price"] / entry - 1) * 100 for f in fills)
    market = sum(f["fraction"] * (f["benchmark_price"] / benchmark[entry_day]["open"] - 1) * 100 for f in fills)
    return {"state": "completed_daily_proxy", "date": day, "code": code, "plan": plan,
            "net_excess_pct": gross - market - cost, "gross_stock_return_pct": gross,
            "fixed3_pct": row["target_t3_net_excess_pct"], "fills": fills, "filled": True,
            "mae_pct": adverse, "entry_risk_filter_applied": False,
            "note": "same_eligible_entry_for_both_exit_methods; risk-width filter is a live-plan warning only"}


def summarize(records):
    usable = [r for r in records if r["state"] in {"completed_daily_proxy", "unfilled", "invalid_before_entry"}]
    days = defaultdict(list)
    for row in usable:
        days[row["date"]].append(row)
    paired = [{"date": d, "new": statistics.mean(r["net_excess_pct"] for r in rows),
               "fixed3": statistics.mean(r["fixed3_pct"] for r in rows),
               "delta": statistics.mean(r["net_excess_pct"]-r["fixed3_pct"] for r in rows)} for d, rows in sorted(days.items())]
    costs = {}
    for bps in (20,40):
        means = [statistics.mean(r["net_excess_pct"] - ((bps-20)/100 if r["filled"] else 0) for r in group)
                 for _, group in sorted(days.items())]
        costs[str(bps)] = statistics.mean(means) if means else None
    return {"state_counts": dict(Counter(r["state"] for r in records)), "paired_signal_dates": len(paired),
            "mean_net_excess_pct": statistics.mean(r["new"] for r in paired) if paired else None,
            "fixed3_mean_net_excess_pct": statistics.mean(r["fixed3"] for r in paired) if paired else None,
            "mean_paired_improvement_pct": statistics.mean(r["delta"] for r in paired) if paired else None,
            "paired_5_signal_date_block_95_interval": block_interval([r["delta"] for r in paired]),
            "round_trip_cost_bps_sensitivity": costs,
            "fill_reason_counts": dict(Counter(f["reason"] for r in usable for f in r.get("fills", []))),
            "measurement": "retrospective_variable_horizon_trade_labels_not_executable_portfolio_pnl",
            "independent_final_test": False, "production_activation": False}


def run(root):
    root = Path(root).resolve()
    receipt = {"generated_at": datetime.now(TZ).isoformat(), "policy_version": VERSION,
               "production_activation": False, "legacy_midline_rule_enabled": False}
    try:
        status = json.loads((root/"output/research/latest/history_pilot_status.json").read_bytes())
        verify_completed(root,status)
        vcp = json.loads((root/"output/research/latest/vcp_pilot_status.json").read_bytes())
        if vcp["source_experiment_sha256"] != status["result_sha256"]:
            raise ValueError("exit_replay_requires_matching_current_model_generation")
        def bound(ref, key):
            path = (root/ref[key+"_file"]).resolve()
            if not path.is_relative_to(root/"output/history_pilot") or digest(path.read_bytes()) != ref[key+"_sha256"]:
                raise ValueError("exit_replay_model_or_dataset_evidence_mismatch")
            raw=path.read_bytes()
            return json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)
        data, model = bound(vcp,"dataset"), bound(vcp,"result")
        manifest = bound(status,"source_manifest")
        chosen = {(d["date"],c) for d in model["out_of_fold_daily_results"][model["selected_model"]] for c in d["selected_codes"]}
        groups=defaultdict(list)
        for row in data["rows"]:
            if (row["date"],row["code"]) in chosen:
                groups[row["code"]].append(row)
        calendar=[r["calendar_date"] for r in read_capture(root,manifest["calendar"])["rows"] if r["is_trading_day"]=="1"]
        benchmark={r["day"]:r for r in normalize(read_capture(root,manifest["benchmark"])["rows"],index=True)}
        cutoff=manifest["config"]["evaluation_policy"]["previously_reviewed_start_date"]
        records=[]
        for source_code,reference in manifest["stocks"].items():
            code=source_code.split(".")[1]
            if code not in groups: continue
            raw=normalize(read_capture(root,reference)["rows"],allow_unknown_status=True)
            adjusted=causal_adjust(raw)
            for variant,override in VARIANTS.items():
                records.extend({**replay(r,raw,adjusted,calendar,benchmark,cutoff,policy_override=override),"variant":variant} for r in groups[code])
        identity=digest(canonical({"policy":POLICY,"variants":VARIANTS,"version":VERSION,"model_sha256":vcp["result_sha256"],
                                  "code_sha256":digest(Path(__file__).read_bytes())}))
        directory=(root/status["result_file"]).parent/"exit_review"/identity[:16]
        directory.mkdir(parents=True,exist_ok=True)
        path=directory/"trades.json.gz"
        path.write_bytes(gzip.compress(canonical(records),mtime=0))
        variants={k:summarize([r for r in records if r["variant"]==k]) for k in VARIANTS}
        result=variants["defense_and_profit"]
        receipt.update(status="exit_policy_replay_completed_research_only",sample_size=status["sample_size"],
            result=result,variant_results=variants,variant_selection="fixed_research_variants_not_selected_by_highest_test_return",trades_file=path.relative_to(root).as_posix(),trades_sha256=digest(path.read_bytes()),
            source_model_file=vcp["result_file"],source_model_sha256=vcp["result_sha256"],
            limitations=["ST_halts_limits_and_actual_fill_evidence_incomplete","no_portfolio_overlap_or_cash_replay",
                         "daily_stop_touch_executes_at_next_open_in_replay","variable_horizon_differs_from_fixed3_control"])
        write(directory/"status.json",receipt)
    except (ValueError,KeyError,TypeError,OSError,ImportError) as exc:
        receipt.update(status="blocked_exit_policy_replay",reason=str(exc)[:400])
    write(root/"output/research/latest/exit_policy_status.json",receipt)
    return receipt


if __name__=="__main__":
    print(json.dumps(run(Path(__file__).resolve().parents[1]),ensure_ascii=False),flush=True)
