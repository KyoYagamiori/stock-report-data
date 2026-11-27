"""Refit an isolated research candidate only with audited prospective labels."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics

from market_screen.history import TZ, canonical_bytes, write_json
from .daily_model_data import checked, immutable, write_changed_latest
from .daily_model_report_feedback import read_published
from .early_model import block_interval, daily_results, fit, predictions
from .ledger import stamp
from .model import eligible_train

DATA = Path("output/research/daily_model")
AUDITS = DATA / "feedback/audited"
CANDIDATES = DATA / "retraining"
CANDIDATE_POINTER = CANDIDATES / "latest.json"
STATUS = Path("output/research/latest/daily_model_retraining.json")
EVIDENCE = ("official_benchmark", "corporate_actions", "execution_and_costs")
ERRORS = (OSError, ValueError, TypeError, KeyError, ImportError, ArithmeticError)


def load_candidate(root, now):
    path = root / CANDIDATE_POINTER
    if not path.exists():
        return None, None
    ref = json.loads(path.read_bytes())
    candidate = json.loads(checked(root, ref, CANDIDATES))
    if stamp(candidate["frozen_at"]) > now:
        raise ValueError("candidate_frozen_in_future")
    return ref, candidate


def attach_shadow_scores(root, rows, active_ref, now):
    candidate_ref, candidate = load_candidate(root, now)
    if not rows or not candidate or candidate["baseline_model"] != active_ref:
        return
    # The file must have reached the published branch before new forecasts exist.
    raw = read_published(root, Path(candidate_ref["file"]))
    if hashlib.sha256(raw).hexdigest() != candidate_ref["sha256"]:
        raise ValueError("published_candidate_hash_mismatch")
    scores = predictions(candidate["models"][candidate["primary_model"]], rows)
    if not all(math.isfinite(score) for score in scores):
        raise ValueError("nonfinite_shadow_score")
    for row, score in zip(rows, scores):
        row["research_candidate"] = {"sha256": candidate_ref["sha256"], "score": float(score)}


def published_predictions(episodes, active_ref, now):
    return [episode for episode in episodes.values()
            if episode["model_sha256"] == active_ref["sha256"]
            and episode.get("public_available_by")
            and stamp(episode["prediction_registered_at"]) <= stamp(episode["public_available_by"]) <= now
            and stamp(episode["public_available_by"]) < stamp(episode["entry_date"] + "T09:30:00+08:00")]


def audited_labels(root, episodes, calendar, now, config):
    rows, rejected = [], Counter()
    proved, seen = set(), set()
    for episode in sorted(episodes, key=lambda ep: (ep["prediction_registered_at"], ep["signal_id"])):
        path = root / AUDITS / (episode["signal_id"] + ".json")
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
            audit = json.loads(raw)
            entry_day = episode["entry_date"]
            exit_day = calendar[calendar.index(entry_day) + 3]
            if (audit.get("schema_version") != 1 or audit.get("signal_id") != episode["signal_id"]
                    or audit["prediction_sha256"] != episode["prediction_file"]["sha256"]
                    or audit.get("entry_date") != entry_day or audit.get("exit_date") != exit_day
                    or not stamp(exit_day + "T15:00:00+08:00") <= stamp(audit["label_known_at"]) <= now):
                raise ValueError("audit_does_not_match_frozen_t3_prediction")
            if (audit.get("scope") != "audited_public_market_execution"
                    or audit.get("round_trip_cost_bps") != config["round_trip_cost_bps"]
                    or not audit.get("benchmark_code")):
                raise ValueError("audit_benchmark_execution_or_cost_scope_invalid")
            returns = [audit["gross_adjusted_stock_return_pct"], audit["gross_benchmark_return_pct"]]
            if any(isinstance(value, bool) or not isinstance(value, (int, float))
                   or not math.isfinite(value) or value < -100 for value in returns):
                raise ValueError("invalid_audited_return")
            for kind in EVIDENCE:
                ref = audit["evidence"][kind]
                key = ref["file"], ref["sha256"]
                if key not in proved:
                    if not checked(root, ref, AUDITS / "sources"):
                        raise ValueError("empty_audit_source")
                    proved.add(key)
            day = stamp(episode["prediction_registered_at"]).astimezone(TZ).date().isoformat()
            stock_day = episode["code"], day
            # A stock published in several shape pools is one training sample per date.
            # Only an already audited row can supply its label.
            first_on_day = stock_day not in seen
            seen.add(stock_day)
            rows.append({"signal_id": episode["signal_id"], "date": day, "code": episode["code"],
                         "setup": episode["setup"], "features": episode["features"],
                         "incumbent_score": episode["scores"][config["primary_model"]],
                         "label_end_date": exit_day, "first_on_day": first_on_day,
                         "target_t3_net_excess_pct": returns[0] - returns[1] - config["round_trip_cost_bps"] / 100,
                         "benchmark_code": audit["benchmark_code"],
                         "audit": {"file": path.relative_to(root).as_posix(),
                                   "sha256": hashlib.sha256(raw).hexdigest()}})
        except (*ERRORS, IndexError) as exc:
            rejected[str(exc).split(":")[0][:120]] += 1
    if len({row["benchmark_code"] for row in rows}) > 1:
        raise ValueError("mixed_official_benchmark_codes")
    return rows, dict(rejected)


def split_at(rows, dates, boundary):
    validation_start = boundary - max(8, boundary // 5)
    train = eligible_train(rows, set(dates[:validation_start]), dates[validation_start])
    valid = eligible_train(rows, set(dates[validation_start:boundary]), dates[boundary])
    return train, valid


def fit_candidate(rows, active, policy, now):
    dates = sorted({row["date"] for row in rows})
    feature_names = tuple(active["feature_names"])
    primary = policy["primary_model"]
    boundaries = [len(dates) * 3 // 5, len(dates) * 4 // 5, len(dates)]
    folds = []
    for start, end in zip(boundaries, boundaries[1:]):
        train, valid = split_at(rows, dates, start)
        test_days = set(dates[start:end])
        test = [row for row in rows if row["date"] in test_days]
        if not (train and valid and test):
            continue
        model = fit(primary, train, valid, feature_names=feature_names)
        candidate = daily_results(test, predictions(model, test))
        incumbent = daily_results(test, [row["incumbent_score"] for row in test])
        folds.append({"test_start": dates[start], "dates": len(candidate),
                      "candidate_minus_incumbent_pct": statistics.mean(
                          new["net_excess_pct"] - old["net_excess_pct"] for new, old in zip(candidate, incumbent)),
                      "candidate_minus_rule_pct": statistics.mean(day["paired_improvement_pct"] for day in candidate)})
    train, valid = split_at(rows, dates, boundaries[1])
    if not folds or not train or not valid:
        raise ValueError("insufficient_purged_chronological_folds")
    return {"frozen_at": now.isoformat(), "feature_names": list(feature_names), "primary_model": primary,
            "models": {kind: fit(kind, train, valid, feature_names=feature_names) for kind in ("ridge", "lightgbm")},
            "audit_through_signal_date": dates[-1], "training_rows": len(train), "validation_rows": len(valid),
            "label_sources": [row["audit"] for row in rows], "rolling_development_folds": folds,
            "evaluation_scope": "rolling_development_diagnostics_then_later_frozen_forward_comparison",
            "production_activation": False}


def forward_comparison(episodes, labels, candidate_ref, primary):
    net_returns = {row["signal_id"]: row["target_t3_net_excess_pct"] for row in labels}
    cohorts, by_day = defaultdict(list), defaultdict(list)
    for episode in episodes:
        if episode.get("research_candidate", {}).get("sha256") == candidate_ref["sha256"]:
            cohorts[episode["cohort_id"], episode["setup"]].append(episode)
    paired = 0
    for group in cohorts.values():
        shadow = min(group, key=lambda ep: (-ep["research_candidate"]["score"], ep["code"]))
        incumbent = min(group, key=lambda ep: (-ep["scores"][primary], ep["code"]))
        rule = min(group, key=lambda ep: (ep["features"]["signal_age_sessions"],
                                        abs(ep["features"]["distance_to_mid_atr"]), ep["code"]))
        if any(winner["signal_id"] not in net_returns for winner in (shadow, incumbent, rule)):
            continue
        new, old, baseline = [net_returns[winner["signal_id"]] for winner in (shadow, incumbent, rule)]
        by_day[shadow["prediction_registered_at"][:10]].append((new - old, new - baseline))
        paired += 1
    relative = [[statistics.mean(pair[i] for pair in pairs) for _, pairs in sorted(by_day.items())] for i in (0, 1)]
    return {"paired_cohorts": paired, "awaiting_audited_labels": len(cohorts) - paired, "signal_dates": len(by_day),
            "candidate_minus_incumbent_pct": statistics.mean(relative[0]) if by_day else None,
            "candidate_minus_rule_pct": statistics.mean(relative[1]) if by_day else None,
            "candidate_minus_incumbent_95_interval": block_interval(relative[0]),
            "candidate_minus_rule_95_interval": block_interval(relative[1])}


def run(root, config, episodes, calendar, now, *, proxy_rows, shadow_error=None):
    enabled = config.get("automatic_retraining") is True
    status = {"enabled": enabled, "checked_at": now.isoformat(), "status": "disabled",
              "matured_price_proxy_rows": proxy_rows, "qualified_rows": 0, "qualified_signal_dates": 0,
              "forward_sessions": 0, "production_activation": False}
    if not enabled:
        return status
    try:
        status.update(status="waiting_for_qualified_feedback", required_evidence=list(EVIDENCE))
        policy = json.loads((root / "config/model_release_policy.json").read_bytes())
        thresholds = {"forward_sessions": policy["minimum_forward_sessions"],
                      "qualified_rows": policy["minimum_matured_signals"],
                      "qualified_signal_dates": policy["minimum_matured_signal_dates"]}
        status["minimums"] = thresholds
        ref, candidate = load_candidate(root, now)
        if ref:
            status["candidate"] = ref
        if shadow_error:
            raise ValueError(shadow_error)
        active_path = root / DATA / "active_model.json"
        if active_path.exists():
            active_ref = json.loads(active_path.read_bytes())
            prospective = published_predictions(episodes, active_ref, now)
            if prospective:
                first_entry = min(episode["entry_date"] for episode in prospective)
                status["forward_sessions"] = sum(first_entry <= day
                    and stamp(day + "T15:00:00+08:00") <= now for day in calendar)
            labels, rejected = audited_labels(root, prospective, calendar, now, config)
            unique = [row for row in labels if row["first_on_day"]]
            in_trial = candidate and candidate["baseline_model"] == active_ref
            new = [row for row in unique if not in_trial or row["date"] > candidate["audit_through_signal_date"]]
            status.update(qualified_rows=len(unique), qualified_signal_dates=len({row["date"] for row in unique}),
                          new_qualified_rows=len(new), new_qualified_signal_dates=len({row["date"] for row in new}),
                          rejected_labels=rejected)
            if in_trial:
                status.update(status="candidate_in_forward_trial",
                              forward_comparison=forward_comparison(prospective, labels, ref, config["primary_model"]))
            if (status["forward_sessions"] >= thresholds["forward_sessions"]
                    and len(new) >= thresholds["qualified_rows"]
                    and status["new_qualified_signal_dates"] >= thresholds["qualified_signal_dates"]):
                active = json.loads(checked(root, active_ref, DATA / "models"))
                proposed = fit_candidate(unique, active, config, now)
                proposed["baseline_model"] = active_ref
                digest = hashlib.sha256(canonical_bytes(proposed)).hexdigest()
                ref = immutable(root, root / CANDIDATES / (digest + ".json"), proposed)
                write_json(root / CANDIDATE_POINTER, ref)
                status.update(status="research_candidate_trained", candidate=ref,
                              training_rows=proposed["training_rows"], validation_rows=proposed["validation_rows"],
                              forward_comparison=forward_comparison([], [], ref, config["primary_model"]))
    except ERRORS as exc:
        status.update(status="blocked_retraining_check", reason=str(exc)[:400])
    return write_changed_latest(root / STATUS, status, "checked_at")
