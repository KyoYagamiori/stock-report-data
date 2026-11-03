"""Collect and independently accept noon quotes AND the report snapshot."""
from __future__ import annotations

import argparse
from datetime import datetime, time
import hashlib
import json
from pathlib import Path
from time import monotonic

from .daily import accepted_screen
from .history import write_json
from .quotes import validate_quote
from .runner import TZ, resolve_dates
from .noon_collection import collect_noon
from .noon_repair import verify_quote_evidence
from .universe import membership_current, validate_universe


def _read_hashed(root, reference, *, directory, path_key="file"):
    path = (root / reference[path_key]).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("evidence_outside_immutable_directory")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference.get("sha256"):
        raise ValueError("evidence_sha256_mismatch:" + path.name)
    return json.loads(raw), path


def accepted_noon(root: Path, moment: datetime) -> dict:
    """Do not treat a successful daily scan as successful midday collection."""
    root = Path(root).resolve()
    dates = resolve_dates(root, moment, "noon")
    today, target = dates["report_date"], dates["market_date"]
    result = {"accepted": False, "report_date": today, "expected_market_date": target,
              "valid_quotes": None, "no_trade_quotes": None, "missing_quotes": None}
    baseline = accepted_screen(root, target, moment)
    result["daily_baseline"] = baseline
    try:
        manifest = json.loads((root / "output/boll/latest/manifest.json").read_text())
        # Keep the noon pointer independent of later intraday/close publications.
        pointer = manifest.get("latest_noon_overlay", manifest.get("latest_overlay", {}))
        overlay, path = _read_hashed(root, pointer, directory=root / "output/boll/archive",
                                    path_key="selected_file")
        screen, screen_path = _read_hashed(root, {"file": pointer["screen_file"],
                                                 "sha256": pointer["screen_sha256"]}, directory=path.parent)
        # A later partial overlay must not invalidate an accepted noon archive.
        if path.parent != screen_path.parent:
            raise ValueError("overlay_not_from_accepted_current_screen")
        if (screen.get("report_date") != today or screen.get("market_date") != target
                or screen.get("phase") != "noon"):
            raise ValueError("noon_screen_date_or_phase_mismatch")
        # Diagnose quotes even when current membership/history fails. A prior
        # early return hid 5,210 valid observations and nine bad timestamps.
        screen_reasons = []
        if not screen.get("universe_current") or not membership_current(screen.get("universe_provenance", {}), today):
            screen_reasons.append("noon_membership_not_current")
        if (not screen.get("technical_screen_complete") or not screen.get("all_codes_accounted_for")
                or screen.get("unresolved_count") != 0):
            screen_reasons.append("noon_technicals_incomplete")
        result["current_screen"] = {"accepted": not screen_reasons, "reasons": screen_reasons,
                                    "run_id": screen.get("run_id"), "screen_file": pointer["screen_file"],
                                    "status_counts": screen.get("status_counts"),
                                    "unresolved_codes": screen.get("unresolved_codes", [])}
        independent = screen.get("collection_details", {}).get("strategy") == "completed_store_plus_independent_noon_quotes_v1"
        published = datetime.fromisoformat(screen["published_at"])
        started = datetime.fromisoformat(screen["started_at"])
        if started.tzinfo is None or not started <= published <= moment:
            raise ValueError("invalid_noon_publication_time_chain")
        if (pointer.get("market_date") != today or pointer.get("phase") != "noon"
                or overlay.get("market_date") != today or overlay.get("phase") != "noon"
                or overlay.get("daily_baseline_date") != target):
            raise ValueError("noon_overlay_date_or_phase_mismatch")
        universe, _ = _read_hashed(root, {"file": screen["universe_file"],
                                         "sha256": screen["universe_sha256"]}, directory=path.parent)
        listings = universe["records"]
        validate_universe(listings)
        expected = {row["code"] for row in listings}
        if independent:
            try:
                from .membership import SOURCE_KEYS
                provenance = screen.get("universe_provenance", {})
                if universe.get("provenance") != provenance or not membership_current({**provenance, "fresh": False}, today):
                    raise ValueError("same_day_official_membership_contract_failed")
                if not SOURCE_KEYS.issubset(provenance.get("sources", {})):
                    raise ValueError("official_source_proof_incomplete")
                for key in SOURCE_KEYS:
                    ref = provenance["sources"][key]
                    source_path = (root / ref["raw_file"]).resolve()
                    stamp = datetime.fromisoformat(ref["retrieved_at"])
                    if (not source_path.is_relative_to(path.parent / "universe_sources") or stamp.tzinfo is None
                            or stamp > moment or hashlib.sha256(source_path.read_bytes()).hexdigest() != ref["sha256"]):
                        raise ValueError("official_source_bytes_or_retrieval_invalid")
                result["official_membership_bytes_verified"] = True
            except (OSError, ValueError, KeyError, TypeError) as exc:
                screen_reasons.append(str(exc))
                result["current_screen"]["accepted"] = False
        counts = screen.get("status_counts", {})
        if (len(expected) != screen.get("universe_count") or overlay.get("universe_count") != len(expected)
                or sum(counts.values()) != len(expected)):
            raise ValueError("noon_universe_count_mismatch")
        rows = []
        for shard in overlay.get("quote_shards", []):
            part, _ = _read_hashed(root, shard, directory=path.parent / "quotes")
            if len(part["records"]) != shard["count"]:
                raise ValueError("noon_quote_shard_count_mismatch")
            rows.extend(part["records"])
        codes = [row["code"] for row in rows]
        if len(codes) != len(expected) or set(codes) != expected:
            raise ValueError("noon_quotes_missing_duplicate_or_substituted_codes")
        valid, no_trades, gaps, times, raw_cache = 0, 0, [], [], {}
        for row in rows:
            quote = row.get("quote") or {}
            errors = validate_quote(quote, today, "noon", now=moment)
            if quote.get("code") != row["code"]:
                errors.append("quote_security_mismatch")
            if independent and errors in ([], ["no_trades"]):
                try:
                    verify_quote_evidence(root, quote, today, moment, cache=raw_cache)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    errors.append("raw_quote_evidence_invalid:" + str(exc))
            if errors == []:
                valid += 1
                times.append(quote["time"])
            elif errors == ["no_trades"]:
                no_trades += 1
                times.append(quote["time"])
            else:
                gaps.append({"code": row["code"], "reasons": errors})
        result.update(universe_count=len(expected), valid_quotes=valid, no_trade_quotes=no_trades,
                      missing_quotes=len(gaps), quote_gaps=gaps, overlay_file=pointer["selected_file"],
                      overlay_sha256=pointer["sha256"], quote_time_min=min(times) if times else None,
                      quote_time_max=max(times) if times else None, sha256_verified=True,
                      scan_run_id=screen["run_id"], scan_published_at=screen["published_at"])
        quote_accepted = not (gaps or not overlay.get("full_market_overlay_complete")
                or overlay.get("valid_quotes") != valid or overlay.get("no_trade_quotes") != no_trades)
        result["quote_coverage_accepted"] = quote_accepted
        comparison_reasons = []
        if independent:
            comparison = screen["collection_details"].get("noon_comparison", {})
            try:
                table, _ = _read_hashed(root, {"file": comparison["candidate_file"], "sha256": comparison["candidate_sha256"]}, directory=path.parent)
                evaluated = []
                for ref in comparison["record_shards"]:
                    shard, _ = _read_hashed(root, ref, directory=path.parent / "noon_comparisons")
                    if len(shard["records"]) != ref["count"]:
                        raise ValueError("comparison_shard_count_mismatch")
                    evaluated += shard["records"]
                if (table.get("report_date") != today or table.get("daily_baseline_date") != target
                        or table.get("evaluated_count") != len(expected) or comparison.get("evaluated_count") != len(expected)
                        or len(evaluated) != len(expected) or {r["code"] for r in evaluated} != expected
                        or any(r.get("daily_date") != target for r in evaluated)):
                    raise ValueError("comparison_date_or_full_universe_accounting_mismatch")
                if table.get("ranking_method") == "completed_boll_score_with_noon_price_risk_gates_v1_fixed":
                    passed = sorted((r for r in evaluated if r.get("eligible")),
                                    key=lambda r: (-r["completed_daily_score"], r["code"]))
                    selected = table.get("candidates", [])
                    if (table.get("eligible_count") != len(passed)
                            or any(r.get("rejection_reasons") or r.get("reasons") for r in passed)
                            or [r["code"] for r in selected] != [r["code"] for r in passed[:len(selected)]]
                            or len(selected) != min(len(passed), table.get("candidate_limit", 20))):
                        raise ValueError("noon_candidate_business_result_mismatch")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                comparison_reasons.append(str(exc))
            result["full_universe_comparison"] = {"accepted": not comparison_reasons, **comparison, "reasons": comparison_reasons}
            result["collection_strategy"] = screen["collection_details"]["strategy"]
            result["completed_daily_source"] = screen["collection_details"]["completed_daily"]
        reasons = ([] if baseline["accepted"] else ["completed_daily_baseline_not_accepted"])
        reasons += screen_reasons
        reasons += comparison_reasons
        if not quote_accepted:
            reasons.append("full_market_noon_quotes_incomplete")
        result.update(accepted=not reasons, reasons=reasons)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        result["reasons"] = [str(exc)]
    return result


def accepted_snapshot(root: Path, moment: datetime) -> dict:
    from pipeline.publisher import verify_pointer
    from pipeline.quality import evaluate_quality

    today = moment.date().isoformat()
    try:
        manifest = json.loads((root / "output/latest/manifest.json").read_text())
        pointer = manifest["snapshots"]["noon"]
        snapshot = verify_pointer(root, pointer)
        grade = evaluate_quality(snapshot, "trading_noon").grade
        readiness = manifest["report_readiness"]["noon"]
        if (snapshot["snapshot_type"] != "noon" or snapshot["report_date"] != today
                or snapshot["market_date"] != today or snapshot["report_cycle"] != today + "-noon"
                or grade not in {"A", "B"} or readiness.get("status") not in {"ready_a", "ready_b"}
                or readiness.get("selected_file") != pointer["selected_file"]):
            raise ValueError("current_noon_report_snapshot_not_ready")
        stamps = [datetime.fromisoformat(snapshot[key]) for key in ("planned_at", "started_at", "published_at")]
        if any(stamp.tzinfo is None for stamp in stamps) or not stamps[0] <= stamps[1] <= stamps[2] <= moment:
            raise ValueError("invalid_report_snapshot_time_chain")
        return {"accepted": True, "status": readiness["status"], "quality_grade": grade,
                "selected_file": pointer["selected_file"], "snapshot_id": snapshot["snapshot_id"],
                "sha256_verified": True, "reasons": []}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"accepted": False, "reasons": [str(exc)]}


def _collect_snapshot(root, now):
    from pipeline.runner import RunOptions, run_pipeline

    return run_pipeline(RunOptions(snapshot_type="noon", mode="full",
                        planned_at=now.strftime("%H:%M"), attempt_role="independent-noon-ingest",
                        report_date=now.date().isoformat(), moment=now), root)


def ensure_noon(root: Path, *, max_seconds=600, moment=None, collector=None, snapshot_collector=None) -> dict:
    """Use one retry per component; keep old dates and explicit failed audits."""
    root = Path(root).resolve()
    now = moment or datetime.now(TZ)
    dates = resolve_dates(root, now, "noon")
    result = {"schema_version": "1.0", "report_date": dates["report_date"],
              "expected_market_date": dates["market_date"], "is_trading_day": dates["is_trading_day"],
              "market_cutoff": dates["report_date"] + "T11:30:00+08:00", "attempts": []}
    if not dates["is_trading_day"]:
        result.update(status="not_applicable", accepted=False, reasons=["non_trading_day"])
    elif not time(11, 30) <= now.time().replace(tzinfo=None) < time(12, 20):
        result.update(status="outside_collection_window", accepted=False,
                      reasons=["noon_ingest_requires_1130_to_1220_China_time"])
    else:
        start = monotonic()
        scan_gate = accepted_noon(root, now)
        snapshot_gate = accepted_snapshot(root, now)
        for number in (1, 2):
            current = moment or datetime.now(TZ)
            # Finish with room for publication before the 12:40 report.
            wall_remaining = (current.replace(hour=12, minute=20, second=0, microsecond=0) - current).total_seconds()
            remaining = min(max_seconds - (monotonic() - start), wall_remaining)
            if remaining <= 0:
                break
            if not scan_gate["accepted"]:
                try:
                    summary = (collector or collect_noon)(root, phase="noon",
                                                max_seconds=max(1, int(remaining / (3 - number))))
                    result["attempts"].append({"component": "full_market", "attempt": number,
                                               "run_id": summary.get("run_id")})
                except Exception as exc:
                    result["attempts"].append({"component": "full_market", "attempt": number,
                                               "error": type(exc).__name__ + ":" + str(exc)[:500]})
                scan_gate = accepted_noon(root, moment or datetime.now(TZ))
            current = moment or datetime.now(TZ)
            if (not snapshot_gate["accepted"] and monotonic() - start < max_seconds
                    and current.time().replace(tzinfo=None) < time(12, 20)):
                try:
                    snapshot = (snapshot_collector or _collect_snapshot)(root, current)
                    result["attempts"].append({"component": "report_snapshot", "attempt": number,
                                               "grade": snapshot.grade, "published": snapshot.published,
                                               "snapshot_id": snapshot.snapshot_id})
                except Exception as exc:
                    result["attempts"].append({"component": "report_snapshot", "attempt": number,
                                               "error": type(exc).__name__ + ":" + str(exc)[:500]})
                snapshot_gate = accepted_snapshot(root, moment or datetime.now(TZ))
            if scan_gate["accepted"] and snapshot_gate["accepted"]:
                break
        result.update(accepted=scan_gate["accepted"] and snapshot_gate["accepted"],
                      full_market=scan_gate, report_snapshot=snapshot_gate)
        result["status"] = ("updated" if result["attempts"] else "already_current") if result["accepted"] else "incomplete"
        result["reasons"] = scan_gate.get("reasons", []) + snapshot_gate.get("reasons", [])
    checked = moment or datetime.now(TZ)
    result["checked_at"] = checked.isoformat()
    result["policy"] = "Completed daily indicators and current 11:30 quotes are separate; no afternoon quotes or old dates relabeled as noon."
    archive = root / "output/boll/noon_checks" / dates["report_date"] / (checked.strftime("%H%M%S%f") + ".json")
    write_json(archive, result)
    result["audit_file"] = archive.relative_to(root).as_posix()
    result["audit_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    latest = root / "output/boll/latest/noon_update.json"
    # A late cron is a diagnostic, not permission to erase an earlier audit.
    if result["status"] not in {"outside_collection_window", "not_applicable"} or not latest.exists():
        write_json(latest, result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--max-seconds", type=int, default=600)
    args = parser.parse_args()
    if args.max_seconds <= 0:
        parser.error("--max-seconds must be positive")
    result = ensure_noon(args.root, max_seconds=args.max_seconds)
    return 0 if result["accepted"] or result["status"] == "not_applicable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
