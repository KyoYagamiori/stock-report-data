"""Replay a real failed noon archive without changing historical acceptance."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
import json
from pathlib import Path

from .completed_source import read_hashed
from .history import write_json
from .noon_collection import reusable_noon_quotes
from .noon_repair import recover_quote, verify_quote_evidence
from .quotes import validate_quote
from .runner import TZ


def replay_latest_noon(root, *, repairer=None, moment=None):
    """Late recovered evidence is supplemental; canonical noon files stay intact."""
    root = Path(root).resolve()
    now = moment or datetime.now(TZ)
    today = now.date().isoformat()
    manifest = json.loads((root / "output/boll/latest/manifest.json").read_text())
    pointer = manifest.get("latest_noon_overlay", {})
    if pointer.get("market_date") != today:
        return {"status": "not_applicable", "reason": "no_current_date_noon_archive_to_replay"}
    overlay, overlay_path = read_hashed(root, {"file": pointer["selected_file"], "sha256": pointer["sha256"]}, root / "output/boll/archive")
    screen, _ = read_hashed(root, {"file": pointer["screen_file"], "sha256": pointer["screen_sha256"]}, overlay_path.parent)
    universe, _ = read_hashed(root, {"file": screen["universe_file"], "sha256": screen["universe_sha256"]}, overlay_path.parent)
    stocks = {row["code"]: row for row in universe["records"]}
    original = {}
    for ref in overlay["quote_shards"]:
        shard, _ = read_hashed(root, ref, overlay_path.parent / "quotes")
        if len(shard["records"]) != ref["count"]:
            raise ValueError("replay_quote_shard_count_mismatch")
        for row in shard["records"]:
            if row["code"] in original:
                raise ValueError("replay_duplicate_quote_code")
            original[row["code"]] = row.get("quote") or {}
    if set(original) != set(stocks):
        raise ValueError("replay_universe_quote_set_mismatch")
    verified, proof_errors = reusable_noon_quotes(root, today, now)
    gaps = sorted(set(stocks) - set(verified))
    before_valid = sum(validate_quote(q, today, "noon", now=now) == [] for q in verified.values())
    before_zero = sum(validate_quote(q, today, "noon", now=now) == ["no_trades"] for q in verified.values())
    directory = root / "output/boll/archive" / overlay["daily_baseline_date"] / (now.strftime("%Y%m%dT%H%M%S%f") + "-noon-validation")
    directory.mkdir(parents=True, exist_ok=False)
    attempts, recovered, failures = [], {}, []
    def repair(code):
        return (repairer or recover_quote)(stocks[code], original[code], root, directory, today, timeout=8, moment=moment)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(repair, code): code for code in gaps[:64]}
        for future in as_completed(futures):
            code = futures[future]
            try:
                quote, trace = future.result()
                attempts += trace
                if quote:
                    verify_quote_evidence(root, quote, today, moment or datetime.now(TZ))
                    recovered[code] = quote
                else:
                    failures.append(code)
            except Exception as exc:
                attempts.append({"code": code, "accepted": False, "error": str(exc)[:300]})
                failures.append(code)
    failures += gaps[64:]
    after = {**verified, **recovered}
    result = {"schema_version": "1.0", "report_date": today, "checked_at": (moment or datetime.now(TZ)).isoformat(),
        "status": "quote_replay_complete" if not failures else "quote_replay_incomplete", "universe_count": len(stocks),
        "source_overlay": pointer, "before": {"valid_quotes": before_valid, "no_trade_quotes": before_zero, "missing_quotes": len(gaps)},
        "after": {"valid_quotes": sum(validate_quote(q, today, "noon", now=moment or datetime.now(TZ)) == [] for q in after.values()),
                  "no_trade_quotes": sum(validate_quote(q, today, "noon", now=moment or datetime.now(TZ)) == ["no_trades"] for q in after.values()),
                  "missing_quotes": len(failures)},
        "requested_gap_codes": gaps[:64], "recovered_codes": sorted(recovered), "unresolved_codes": sorted(failures),
        "prior_raw_proof_errors": proof_errors, "attempts": attempts, "recovered_quotes": recovered,
        "original_noon_membership_current": screen.get("universe_current"),
        "original_noon_technical_screen_complete": screen.get("technical_screen_complete"),
        "historical_noon_acceptance_changed": False,
        "policy": "Post-cutoff quote replay only. Does not assert availability at 12:40 or replace original noon_update, membership, ranking or report."}
    path = root / "output/boll/noon_checks" / today / (now.strftime("%H%M%S%f") + "-quote-replay.json")
    write_json(path, result)
    return {**result, "audit_file": path.relative_to(root).as_posix(), "audit_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    result = replay_latest_noon(Path(__file__).resolve().parents[1])
    print(json.dumps({key: value for key, value in result.items() if key not in {"recovered_quotes", "attempts"}}, ensure_ascii=False), flush=True)
    return 0 if result["status"] in {"not_applicable", "quote_replay_complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
