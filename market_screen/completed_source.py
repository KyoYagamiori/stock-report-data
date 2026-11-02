"""Read a verified completed-session store; repair only missing records."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from time import monotonic

from .daily import accepted_screen
from .history import fetch_history
from .quotes import parse_sina_quotes, validate_quote
from .runner import assemble_record, previous_stock_session, verified_suspension
from .technicals import PARAMETERS, rank_candidate


def read_hashed(root, reference, directory, path_key="file"):
    root = Path(root).resolve()
    path = (root / reference[path_key]).resolve()
    if not path.is_relative_to(Path(directory).resolve()):
        raise ValueError("source_path_outside_immutable_version")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference.get("sha256"):
        raise ValueError("source_sha256_mismatch:" + path.name)
    return json.loads(raw), path


def verify_no_trade(root, directory, row, target, moment):
    quote = row.get("quote") or {}
    if quote.get("code") != row.get("code") or validate_quote(quote, target, "close", now=moment) != ["no_trades"]:
        raise ValueError("completed_no_trade_quote_invalid")
    marker = "output/boll/archive/"
    raw_path = str(quote.get("raw_file", ""))
    if marker not in raw_path:
        raise ValueError("completed_no_trade_raw_source_missing")
    path = (root / raw_path[raw_path.index(marker):]).resolve()
    if not path.is_relative_to(directory / "quote_sources"):
        raise ValueError("completed_no_trade_raw_source_outside_version")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != quote.get("raw_sha256"):
        raise ValueError("completed_no_trade_raw_sha256_mismatch")
    parsed = parse_sina_quotes(raw).get(row["code"], {})
    for key in ("code", "date", "time", "status", "open", "prev_close", "close", "high", "low", "volume", "amount"):
        if parsed.get(key) != quote.get(key):
            raise ValueError("completed_no_trade_raw_fields_mismatch")


def load_completed_records(root, target, moment):
    """Hash every shard once. Partial exact-date stores remain explicitly partial."""
    root = Path(root).resolve()
    gate = accepted_screen(root, target, moment)
    try:
        manifest = json.loads((root / "output/boll/latest/manifest.json").read_text())
        pointers = [manifest.get(key, {}) for key in ("latest_complete_screen", "latest_screen")]
        pointer = next((p for p in pointers if p.get("selected_file") == gate.get("screen_file")), None)
        if pointer is None:
            pointer = next(p for p in reversed(pointers) if p.get("market_date") == target)
        screen, path = read_hashed(root, {"file": pointer["selected_file"], "sha256": pointer["sha256"]}, root / "output/boll/archive")
        stamp = datetime.fromisoformat(screen["published_at"])
        if (screen.get("market_date") != target or stamp.tzinfo is None or stamp > moment
                or screen.get("parameters") != PARAMETERS):
            raise ValueError("completed_store_date_parameters_or_publication_invalid")
        universe, _ = read_hashed(root, {"file": screen["universe_file"], "sha256": screen["universe_sha256"]}, path.parent)
        expected = {r["code"] for r in universe["records"]}
        if len(expected) != screen["universe_count"] or len(expected) != len(universe["records"]):
            raise ValueError("completed_store_universe_count_invalid")
        records = {}
        for ref in screen["record_shards"]:
            shard, _ = read_hashed(root, ref, path.parent / "records")
            if len(shard["records"]) != ref["count"]:
                raise ValueError("completed_store_shard_count_invalid")
            for row in shard["records"]:
                if row.get("code") not in expected or row["code"] in records or row.get("market_date") != target:
                    raise ValueError("completed_store_duplicate_identity_or_date")
                records[row["code"]] = row
        if (set(records) != expected or dict(Counter(r["status"] for r in records.values())) != screen["status_counts"]):
            raise ValueError("completed_store_accounting_invalid")
        return records, {"accepted": gate["accepted"], "screen_file": pointer["selected_file"],
            "sha256": pointer["sha256"], "run_id": screen["run_id"], "market_date": target,
            "published_at": screen["published_at"], "record_shards_verified": len(screen["record_shards"]),
            "reasons": gate.get("reasons", [])}, path.parent
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        return {}, {"accepted": False, "market_date": target, "reasons": [str(exc)]}, None


def reuse_daily_records(root, universe, dates, config, moment, *, max_seconds=120, fetcher=None):
    """No history request for a valid completed record; at most 24 gap repairs."""
    root = Path(root).resolve()
    old, source, directory = load_completed_records(root, dates["market_date"], moment)
    states_path = root / "config/boll_trading_states.json"
    states = {r["code"]: r for r in json.loads(states_path.read_text()).get("records", [])} if states_path.exists() else {}
    output, missing = {}, []
    for stock in universe:
        code = stock["code"]
        row = copy.deepcopy(old.get(code))
        name = str(stock.get("name", "")).upper()
        reasons = []
        if "ST" in name or "退" in name:
            row = {**stock, "market_date": dates["market_date"], "status": "excluded", "reasons": ["risk_warning_name"], "ranking": {"eligible": False},
                   "update_method": "current_risk_warning_exclusion"}
        elif str(stock.get("listing_date") or "")[:10] > dates["market_date"]:
            row = {**stock, "market_date": dates["market_date"], "status": "excluded", "reasons": ["not_listed_at_target_date"], "ranking": {"eligible": False},
                   "update_method": "not_listed_at_completed_session"}
        elif row and row.get("status") == "screened":
            ind = row.get("indicators", {})
            if (ind.get("bar_date") != dates["market_date"] or not ind.get("history_current")
                    or ind.get("bar_count") != 160 or ind.get("parameters") != PARAMETERS):
                reasons.append("completed_record_indicators_invalid")
            else:
                try:
                    row["ranking"] = rank_candidate(stock, ind, config)
                except (ValueError, KeyError, TypeError) as exc:
                    reasons.append("completed_record_ranking_input_invalid:" + str(exc))
        elif row and row.get("status") == "excluded":
            why = row.get("reasons", [])
            if why == ["no_trades_on_target_session"]:
                try:
                    verify_no_trade(root, directory, row, dates["market_date"], moment)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    reasons.append(str(exc))
            elif why == ["issuer_announced_suspension"]:
                if not verified_suspension(row.get("trading_state"), code, dates["market_date"]):
                    reasons.append("completed_suspension_proof_invalid")
            elif why == ["new_listing_insufficient_completed_history"]:
                listed = stock.get("listing_date")
                if not listed or sum(listed <= day <= dates["market_date"] for day in dates["expected_sessions"]) >= 160:
                    reasons.append("completed_new_listing_exclusion_invalid")
            else:
                reasons.append("completed_exclusion_requires_current_review")
        else:
            reasons.append("completed_record_missing_or_unresolved")
        if reasons or row is None:
            missing.append(stock)
            row = {**stock, "market_date": dates["market_date"], "status": "unresolved", "ranking": {"eligible": False},
                   "reasons": reasons or ["completed_record_missing"], "update_method": "completed_store_gap"}
        else:
            row.update({key: stock.get(key) for key in ("code", "name", "exchange", "board", "industry", "listing_date")})
            if row.get("update_method") not in {"current_risk_warning_exclusion", "not_listed_at_completed_session"}:
                row["update_method"] = "verified_completed_store_reuse"
                row["completed_store_source"] = {"screen_file": source.get("screen_file"), "sha256": source.get("sha256")}
        output[code] = row
    started = monotonic()
    deadline = started + max(0, max_seconds)
    # A missing/corrupt whole store is an upstream failure, not permission to
    # start 5,000 history downloads in the noon deadline.
    repairable = missing if old and len(missing) <= 24 and max_seconds >= 20 else []
    cache = root / "output/boll/state/history"
    cache.mkdir(parents=True, exist_ok=True)
    def repair(stock):
        if monotonic() >= deadline:
            return None
        previous, evidence = previous_stock_session(stock, dates, states.get(stock["code"]))
        history = (fetcher or fetch_history)(stock, dates["market_date"], cache,
            previous_session=previous, quote=None, timeout=min(12, max(1, deadline - monotonic())),
            retry_count=0, suspension_evidence=evidence)
        return assemble_record(stock, history, dates["market_date"], config, dates["expected_sessions"], trading_state=states.get(stock["code"]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(repair, stock): stock for stock in repairable}
        for future in as_completed(futures):
            stock = futures[future]
            try:
                row = future.result()
                if row:
                    output[stock["code"]] = row
            except Exception as exc:
                output[stock["code"]]["repair_error"] = str(exc)[:300]
    return [output[s["code"]] for s in sorted(universe, key=lambda s: s["code"])], {
        "source": source, "reused_count": sum(r.get("update_method") == "verified_completed_store_reuse" for r in output.values()),
        "gap_codes": [s["code"] for s in missing], "repair_requested_count": len(repairable),
        "unresolved_codes": [r["code"] for r in output.values() if r["status"] == "unresolved"],
        "history_policy": "Reuse immutable completed indicators; fetch at most 24 actual gaps, never an unfinished daily bar."}
