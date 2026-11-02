"""Independent noon collection: completed store + current official universe + quotes."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
from datetime import datetime, time
import hashlib
import json
from pathlib import Path
from time import monotonic

from .completed_source import read_hashed, reuse_daily_records
from .history import write_json
from .membership import read_frozen_universe
from .noon_repair import evidence_path, recover_quote, verify_quote_evidence
from .quotes import fetch_quotes, validate_quote
from .runner import TZ, overlay_record, publish, resolve_dates
from .universe import load_universe, membership_current, validate_universe


def retain_quote_bytes(root, directory, quote, cache):
    """Make each new publication self-contained, retaining original clocks."""
    if not quote or not quote.get("raw_file"):
        return quote
    quote = copy.deepcopy(quote)
    source = evidence_path(root, quote["raw_file"])
    key = (str(source), quote.get("raw_sha256"))
    if key not in cache:
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != quote.get("raw_sha256"):
            raise ValueError("reused_quote_source_sha256_mismatch")
        target = directory / "quote_sources" / ("retained_" + quote["raw_sha256"] + ".raw")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        cache[key] = target.relative_to(root).as_posix()
    quote["original_raw_file"] = quote["raw_file"]
    quote["raw_file"] = cache[key]
    if quote.get("recovery", {}).get("original_quote"):
        quote["recovery"]["original_quote"] = retain_quote_bytes(root, directory, quote["recovery"]["original_quote"], cache)
    return quote


def reusable_noon_quotes(root, report_date, moment):
    """A failed membership/history gate does not discard valid current quotes."""
    root = Path(root).resolve()
    result, errors, raw_cache = {}, [], {}
    try:
        manifest = json.loads((root / "output/boll/latest/manifest.json").read_text())
        pointer = manifest.get("latest_noon_overlay", {})
        if pointer.get("market_date") != report_date or pointer.get("phase") != "noon":
            return result, errors
        overlay, path = read_hashed(root, {"file": pointer["selected_file"], "sha256": pointer["sha256"]}, root / "output/boll/archive")
        stamp = datetime.fromisoformat(pointer["published_at"])
        if (overlay.get("market_date") != report_date or overlay.get("phase") != "noon"
                or stamp.tzinfo is None or stamp > moment):
            raise ValueError("prior_noon_overlay_date_or_publication_invalid")
        seen = set()
        for ref in overlay["quote_shards"]:
            data, _ = read_hashed(root, ref, path.parent / "quotes")
            if len(data["records"]) != ref["count"]:
                raise ValueError("prior_noon_quote_shard_count_invalid")
            for row in data["records"]:
                code = row["code"]
                if code in seen:
                    raise ValueError("prior_noon_quote_duplicate_code")
                seen.add(code)
                quote = row.get("quote") or {}
                reasons = validate_quote(quote, report_date, "noon", now=moment)
                if quote.get("code") != code or reasons not in ([], ["no_trades"]):
                    continue
                try:
                    verify_quote_evidence(root, quote, report_date, moment, cache=raw_cache)
                    result[code] = quote
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    errors.append({"code": code, "error": str(exc)[:200]})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {}, [{"error": str(exc)[:300]}]
    return result, errors


def compare_noon(root, directory, records, quotes, dates, moment, config):
    """Evaluate every official code; current prices never become daily bars.

    Preserve the existing completed-day BOLL score. Noon adds explicit risk
    gates, not an invented win probability or an unfinished indicator score.
    """
    comparisons, candidates = [], []
    for row in records:
        overlay = overlay_record(row, quotes.get(row["code"]), dates["report_date"], "noon", moment, dates["market_date"])
        reasons = list(row.get("ranking", {}).get("reasons", []))
        if row.get("status") != "screened":
            reasons += row.get("reasons", []) or ["daily_record_not_screened"]
        if not row.get("ranking", {}).get("eligible"):
            reasons.append("completed_daily_setup_not_eligible")
        if overlay["status"] != "valid":
            reasons += overlay.get("errors", []) or ["no_valid_daily_price_overlay"]
        elif overlay.get("corporate_action_basis_changed"):
            reasons.append("corporate_action_price_basis_review_required")
        else:
            boll = row["indicators"]["boll"]
            price = overlay["quote"]["close"]
            if price < boll["mid"]:
                reasons.append("noon_price_below_completed_middle_band")
            if (price / boll["upper"] - 1) * 100 > config["maximum_extension_above_upper_pct"]:
                reasons.append("noon_price_extended_above_completed_upper_band")
        item = {"code": row["code"], "eligible": not reasons, "reasons": list(dict.fromkeys(reasons)),
                "completed_daily_score": row.get("ranking", {}).get("score"), "daily_date": dates["market_date"],
                "quote_date": (overlay.get("quote") or {}).get("date"), "quote_time": (overlay.get("quote") or {}).get("time"),
                "quote_status": overlay["quote_status"], "analysis_reviewed": False}
        comparisons.append(item)
        if item["eligible"]:
            candidates.append({**row, "noon_overlay": overlay, "noon_comparison": item})
    candidates.sort(key=lambda r: (-r["ranking"]["score"], r["code"]))
    refs = []
    for offset in range(0, len(comparisons), 100):
        rows = comparisons[offset:offset + 100]
        path = directory / "noon_comparisons" / (rows[0]["code"] + "-" + rows[-1]["code"] + ".json")
        write_json(path, {"records": rows})
        refs.append({"file": path.relative_to(root).as_posix(), "count": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    path = directory / "noon_candidates.json"
    write_json(path, {"report_date": dates["report_date"], "daily_baseline_date": dates["market_date"],
        "market_cutoff": dates["report_date"] + "T11:30:00+08:00", "evaluated_count": len(comparisons),
        "eligible_count": len(candidates), "ranking_method": "completed_boll_score_with_noon_price_risk_gates_v1",
        "company_diligence_complete": False, "candidates": candidates[:config["candidate_count"]],
        "scope_note": "Every official code accounted for; quantitative triage only. No statistical win rate or full-company diligence."})
    return {"candidate_file": path.relative_to(root).as_posix(), "candidate_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "evaluated_count": len(comparisons), "eligible_count": len(candidates), "record_shards": refs,
            "ranking_method": "completed_boll_score_with_noon_price_risk_gates_v1"}


def collect_noon(root, *, phase="noon", max_seconds=480, moment=None, quote_collector=None, repairer=None, history_fetcher=None):
    """Never launch a full historical rebuild at noon. Repeated runs merge gaps."""
    root = Path(root).resolve()
    now = moment or datetime.now(TZ)
    if phase != "noon" or not time(11, 30) <= now.time().replace(tzinfo=None) < time(12, 20):
        raise ValueError("noon_quote_collection_requires_1130_to_1220_China_time")
    dates = resolve_dates(root, now, "noon")
    if not dates["is_trading_day"]:
        raise ValueError("noon_quote_collection_requires_trading_day")
    started = monotonic()
    deadline = started + min(max_seconds, (now.replace(hour=12, minute=20, second=0, microsecond=0) - now).total_seconds())
    directory = root / "output/boll/archive" / dates["market_date"] / (now.strftime("%Y%m%dT%H%M%S%f") + "-noon")
    directory.mkdir(parents=True, exist_ok=False)
    config = json.loads((root / "config/boll_screen.json").read_text())
    member_errors = []
    try:
        universe, meta = read_frozen_universe(root, dates["report_date"], now)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        member_errors.append(str(exc))
        universe, meta = load_universe(root, dates["report_date"], refresh=True, timeout=min(8, config["request_timeout_seconds"]))
    validate_universe(universe)
    if not membership_current({**meta, "fresh": False}, dates["report_date"]):
        meta = {**meta, "fresh": False, "freshness_reasons": meta.get("freshness_reasons", []) + ["same_day_official_source_contract_not_met"]}
    # Quotes first: protect the time-sensitive observation from history gaps.
    previous, proof_errors = reusable_noon_quotes(root, dates["report_date"], now)
    quotes = {s["code"]: previous[s["code"]] for s in universe if s["code"] in previous}
    missing = [s for s in universe if s["code"] not in quotes]
    metadata = {"source": "independent_noon_gap_merge", "reused_verified_quotes": len(quotes),
                "primary_requested_codes": [s["code"] for s in missing], "prior_proof_errors": proof_errors,
                "membership_reuse_errors": member_errors, "minute_repairs": []}
    if missing and monotonic() < deadline:
        options = {"timeout": min(8, max(1, deadline - monotonic()))}
        if quote_collector is None:
            options["max_seconds"] = max(1, deadline - monotonic() - 15)
        fresh, fetch_meta = (quote_collector or fetch_quotes)(missing, directory, **options)
        quotes.update(fresh)
        metadata["primary_collection"] = fetch_meta
    gaps = [s for s in universe if (quotes.get(s["code"], {}).get("code") != s["code"] or
            validate_quote(quotes.get(s["code"], {}), dates["report_date"], "noon", now=moment or datetime.now(TZ)) not in ([], ["no_trades"]))]
    # Bound a whole-provider outage. Never make 10,000 minute requests or
    # pretend a small candidate quote set is the full market.
    requested = gaps if len(gaps) <= 64 else gaps[:64]
    def repair(stock):
        remaining = deadline - monotonic()
        if remaining < 2:
            return None, [{"code": stock["code"], "accepted": False, "error": "shared_noon_deadline_exhausted"}]
        return (repairer or recover_quote)(stock, quotes.get(stock["code"]), root, directory, dates["report_date"],
                         timeout=min(8, max(1, remaining / 2)), moment=moment)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(repair, stock): stock for stock in requested}
        for future in as_completed(futures):
            stock = futures[future]
            try:
                quote, attempts = future.result()
                metadata["minute_repairs"].extend(attempts)
                if quote and quote.get("code") == stock["code"]:
                    quotes[stock["code"]] = quote
            except Exception as exc:
                metadata["minute_repairs"].append({"code": stock["code"], "accepted": False, "error": str(exc)[:300]})
    metadata["unattempted_gap_codes"] = [s["code"] for s in gaps[len(requested):]]
    records, daily = reuse_daily_records(root, universe, dates, config, moment or datetime.now(TZ),
            max_seconds=min(90, max(0, deadline - monotonic())), fetcher=history_fetcher)
    retained = {}
    quotes = {code: retain_quote_bytes(root, directory, quote, retained) for code, quote in quotes.items()}
    for row in records:
        if row.get("reasons") == ["no_trades_on_target_session"]:
            row["quote"] = retain_quote_bytes(root, directory, row.get("quote"), retained)
    current = moment or datetime.now(TZ)
    comparison = compare_noon(root, directory, records, quotes, dates, current, config)
    details = {"strategy": "completed_store_plus_independent_noon_quotes_v1", "completed_daily": daily,
               "noon_comparison": comparison, "no_history_full_rescan": True,
               "freeze_deadline": dates["report_date"] + "T12:20:00+08:00"}
    return publish(root, directory, records, universe, meta, dates, quotes, metadata,
                   now.isoformat(), monotonic() - started, config, moment=current, collection_details=details)
