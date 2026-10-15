"""Publish one auditable full-universe screen plus an optional intraday overlay."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import date, datetime, time
import gzip
import hashlib
import json
from pathlib import Path
import time as clock
from zoneinfo import ZoneInfo

from .history import canonical_bytes, fetch_history, import_evidence, import_seed, load_cache, preserve_bootstrap, write_json
from .quotes import fetch_quotes, validate_quote
from .technicals import PARAMETERS, calculate, rank_candidate
from .universe import load_universe, membership_current, validate_universe

TZ = ZoneInfo("Asia/Shanghai")


def calendar_dates(root):
    path = root / "output/cache/trade_calendar.json"
    if not path.exists():
        raise ValueError("verified_trade_calendar_missing")
    data = json.loads(path.read_text())
    dates = sorted(set(data["trade_dates"]))
    if not dates or not data.get("source") or "fallback" in data["source"]:
        raise ValueError("verified_trade_calendar_missing")
    return dates, data["source"]


def resolve_dates(root, moment, phase, explicit_market_date=None):
    if moment.tzinfo is None:
        raise ValueError("run_time_requires_timezone")
    moment = moment.astimezone(TZ)
    dates, source = calendar_dates(root)
    today = moment.date().isoformat()
    if not dates[0] <= today < dates[-1]:
        raise ValueError("trade_calendar_out_of_range")
    if phase == "auto":
        phase = ("close" if moment.time() >= time(15, 10)
                 else "noon" if time(11, 30) <= moment.time() < time(13)
                 else "intraday" if time(9, 30) <= moment.time() < time(15, 10)
                 else "early")
    completed = [d for d in dates if d < today or (d == today and moment.time() >= time(15, 10))]
    target = explicit_market_date or max(completed)
    if target not in completed:
        raise ValueError("market_date_not_a_completed_trading_session")
    previous = max(d for d in dates if d < target)
    return {"market_date": target, "previous_session": previous, "report_date": today,
            "phase": phase, "is_trading_day": today in dates, "calendar_source": source,
            "expected_sessions": dates}


def assemble_record(stock, history, target_date, config, sessions, quote=None):
    code = stock["code"]
    out = {"code": code, "name": stock.get("name"), "exchange": stock["exchange"],
           "board": stock.get("board"), "industry": stock.get("industry"),
           "listing_date": stock.get("listing_date"), "market_date": target_date,
           "source": history.get("source"), "update_method": history.get("update_method"),
           "history_sha256": history.get("history_sha256"), "analysis_reviewed": False}
    name = str(stock.get("name", "")).upper().replace(" ", "")
    if "ST" in name or "退" in name:
        out.update(status="excluded", reasons=["risk_warning_name"], ranking={"eligible": False})
        return out
    listed = str(stock.get("listing_date") or "")[:10]
    if listed and listed > target_date:
        out.update(status="excluded", reasons=["not_listed_at_target_date"], ranking={"eligible": False})
        return out
    if history.get("fetch_status") != "success" or not history.get("bars"):
        out.update(status="unresolved", reasons=["history_request_failed"], errors=history.get("errors", []), ranking={"eligible": False})
        return out
    try:
        indicators = calculate(history["bars"], target_date)
    except (ValueError, KeyError, TypeError) as exc:
        out.update(status="unresolved", reasons=["invalid_history:" + str(exc)], ranking={"eligible": False})
        return out
    out["indicators"] = indicators
    if not indicators["history_current"]:
        # Exact target-day zero-activity quotes justify a no-trade exclusion.
        # A stale last bar or today's zero volume cannot prove an earlier halt.
        if quote and quote.get("date") == target_date and quote.get("status") == "no_trades":
            out.update(status="excluded", reasons=["no_trades_on_target_session"], quote=quote, ranking={"eligible": False})
        else:
            out.update(status="unresolved", reasons=["missing_target_session_bar"], ranking={"eligible": False})
        return out
    if indicators["bar_count"] < config["minimum_history_bars"]:
        possible_sessions = sum(listed <= day <= target_date for day in sessions) if listed else None
        if possible_sessions is not None and possible_sessions < config["minimum_history_bars"]:
            out.update(status="excluded", reasons=["new_listing_insufficient_completed_history"], ranking={"eligible": False})
        else:
            out.update(status="unresolved", reasons=["truncated_history_unexplained"], ranking={"eligible": False})
        return out
    out.update(status="screened", reasons=[], ranking=rank_candidate(stock, indicators, config))
    if (history.get("source") or {}).get("corporate_action_basis_change"):
        out["ranking"].update(eligible=False, reasons=["corporate_action_price_basis_review_required"])
    return out


def overlay_record(record, quote, report_date, phase, moment, expected_baseline_date=None):
    out = {"code": record["code"], "name": record["name"], "completed_daily_asof": record["market_date"],
           "quote": quote, "is_completed_daily_indicator": False}
    errors = validate_quote(quote or {}, report_date, phase, now=moment)
    out["errors"] = errors
    if errors:
        out["status"] = "unavailable"
        return out
    if expected_baseline_date and record.get("indicators", {}).get("bar_date") != expected_baseline_date:
        out.update(status="stale_baseline", errors=["daily_baseline_not_previous_completed_session"])
        return out
    previous = record.get("indicators", {}).get("price")
    out.update(status="valid", return_vs_source_previous_close_pct=(quote["close"] / quote["prev_close"] - 1) * 100,
               daily_boll_position=None, corporate_action_basis_changed=False,
               note="Intraday price overlay on completed daily BOLL; not a completed daily indicator. Volume is absolute, not compared to prior full day.")
    if previous and abs(previous - quote["prev_close"]) > .011:
        out["corporate_action_basis_changed"] = True
        out["note"] = "Previous-close mismatch may be corporate-action mechanics or a source discrepancy; verify the price basis before use."
    else:
        boll = record.get("indicators", {}).get("boll")
        if boll:
            out["daily_boll_position"] = "above_upper" if quote["close"] > boll["upper"] else "above_middle" if quote["close"] >= boll["mid"] else "below_middle"
    return out


def publish(root, run_dir, records, universe, universe_meta, dates, quotes, quotes_meta, started_at, elapsed_s, config):
    counts = Counter(r["status"] for r in records)
    unresolved = [r["code"] for r in records if r["status"] == "unresolved"]
    candidates = sorted((r for r in records if r.get("ranking", {}).get("eligible")),
                        key=lambda r: (-r["ranking"]["score"], r["code"]))[:config["candidate_count"]]
    all_codes_match = {r["code"] for r in records} == {r["code"] for r in universe} and len(records) == len(universe)
    universe_fresh = bool(universe_meta.get("fresh"))
    universe_current = membership_current(universe_meta, dates["report_date"])
    complete = all_codes_match and not unresolved and universe_current
    relative = lambda path: path.relative_to(root).as_posix()
    write_json(run_dir / "universe.json", {"records": universe, "provenance": universe_meta})
    shards = []
    for offset in range(0, len(records), 100):
        rows = records[offset:offset + 100]
        path = run_dir / "records" / f"{rows[0]['code']}-{rows[-1]['code']}.json"
        write_json(path, {"market_date": dates["market_date"], "records": rows})
        shards.append({"file": relative(path), "count": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    summary = {
        "schema_version": "1.0", "run_id": run_dir.name,
        "scope": "SSE/SZSE ordinary A-shares; all sectors; main board, ChiNext, STAR; BSE/B/CDR excluded",
        "market_date": dates["market_date"], "market_cutoff": dates["market_date"] + "T15:00:00+08:00",
        "report_date": dates["report_date"], "phase": dates["phase"], "started_at": started_at,
        "published_at": datetime.now(TZ).isoformat(), "elapsed_seconds": round(elapsed_s, 2),
        "point_in_time_recovered": dates["market_date"] < started_at[:10],
        "universe_count": len(universe), "exchange_counts": dict(Counter(s["exchange"] for s in universe)),
        "universe_fresh": universe_fresh, "universe_provenance": universe_meta,
        "universe_current": universe_current,
        "status_counts": dict(counts), "unresolved_count": len(unresolved), "unresolved_codes": unresolved,
        "all_codes_accounted_for": all_codes_match, "technical_screen_complete": complete,
        "candidate_count": len(candidates), "parameters": PARAMETERS, "record_shards": shards,
        "candidate_file": relative(run_dir / "candidates.json"),
        "company_diligence_complete": False, "focus_stock_code": None,
        "recommendation_status": "candidate_review_required" if complete else "partial_screen_candidate_review_required",
        "quality_note": "Technical screen coverage and company research are separate. No automatic recommendation or statistical win rate.",
        "update_methods": dict(Counter(r.get("update_method") for r in records)),
    }
    write_json(run_dir / "candidates.json", {"screen_complete": complete, "market_date": dates["market_date"],
               "scope_note": summary["quality_note"], "candidates": candidates})
    phase = dates["phase"]
    overlay = None
    if phase in ("noon", "intraday") and dates["is_trading_day"]:
        now = datetime.now(TZ)
        expected_baseline = max(day for day in dates["expected_sessions"] if day < dates["report_date"])
        overlay_rows = [overlay_record(r, quotes.get(r["code"]), dates["report_date"], phase, now, expected_baseline) for r in records]
        valid = sum(r["status"] == "valid" for r in overlay_rows)
        overlay = {"market_date": dates["report_date"], "phase": phase, "daily_baseline_date": dates["market_date"],
                   "valid_quotes": valid, "universe_count": len(universe), "full_market_overlay_complete": valid == len(universe),
                   "source": quotes_meta, "candidate_overlays": [r for r in overlay_rows if r["code"] in {c["code"] for c in candidates}]}
        write_json(run_dir / "overlay.json", overlay)
        for offset in range(0, len(overlay_rows), 100):
            rows = overlay_rows[offset:offset + 100]
            write_json(run_dir / "quotes" / f"{rows[0]['code']}-{rows[-1]['code']}.json", {"records": rows})
        summary["overlay_file"] = relative(run_dir / "overlay.json")
    write_json(run_dir / "screen.json", summary)
    text = [f"# 沪深全市场布林筛选：{dates['market_date']}", "",
            f"名录 {len(universe)} 只；完成指标 {counts.get('screened', 0)}；合理剔除 {counts.get('excluded', 0)}；未解决 {len(unresolved)}。",
            f"全量技术筛选验收：{'通过' if complete else '未通过（见缺口及名录日期）'}。本轮耗时 {elapsed_s:.1f} 秒。", "",
            "以下是待核查公告、业绩、估值和入场条件的研究候选，分数是规则排序，不是统计胜率。", "",
            "| 代码 | 名称 | 研究排序分 | 形态 | 收盘 | 布林中轨 |", "|---|---|---:|---|---:|---:|"]
    for r in candidates:
        text.append(f"| {r['code']} | {r['name']} | {r['ranking']['score']:.2f} | {', '.join(r['indicators']['patterns'])} | {r['indicators']['price']:.2f} | {r['indicators']['boll']['mid']:.4f} |")
    (run_dir / "screen.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    manifest_path = root / "output/boll/latest/manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"schema_version": "1.0"}
    selected = {"market_date": dates["market_date"], "phase": phase, "run_id": run_dir.name,
                "selected_file": relative(run_dir / "screen.json"), "candidate_file": relative(run_dir / "candidates.json"),
                "sha256": hashlib.sha256((run_dir / "screen.json").read_bytes()).hexdigest(),
                "technical_screen_complete": complete, "unresolved_count": len(unresolved),
                "published_at": summary["published_at"]}
    prior = manifest.get("latest_screen", {})
    # New incomplete runs cannot hide an already accepted complete same-date run.
    if dates["market_date"] > prior.get("market_date", "") or (dates["market_date"] == prior.get("market_date", "") and (complete or not prior.get("technical_screen_complete"))):
        manifest["latest_screen"] = selected
    if complete and dates["market_date"] >= manifest.get("latest_complete_screen", {}).get("market_date", ""):
        manifest["latest_complete_screen"] = selected
    if overlay:
        prior_overlay = manifest.get("latest_overlay", {})
        if dates["report_date"] >= prior_overlay.get("market_date", ""):
            manifest["latest_overlay"] = {"market_date": dates["report_date"], "phase": phase,
                "selected_file": relative(run_dir / "overlay.json"), "valid_quotes": overlay["valid_quotes"],
                "full_market_overlay_complete": overlay["full_market_overlay_complete"], "published_at": summary["published_at"]}
    manifest["last_attempt"] = selected
    write_json(manifest_path, manifest)
    return summary


def run(root, *, phase="auto", market_date=None, max_seconds=2400, workers=None, import_history=None,
        refresh_universe=True, skip_quotes=False, moment=None, cached_only=False):
    moment = (moment or datetime.now(TZ)).astimezone(TZ)
    started, started_at = clock.monotonic(), moment.isoformat()
    dates = resolve_dates(root, moment, phase, market_date)
    config = json.loads((root / "config/boll_screen.json").read_text())
    run_id = moment.strftime("%Y%m%dT%H%M%S") + "-" + dates["phase"]
    run_dir = root / "output/boll/archive" / dates["market_date"] / run_id
    if run_dir.exists():
        raise ValueError("immutable_run_id_already_exists")
    run_dir.mkdir(parents=True)
    # This is today's investment universe using the last completed day's bars,
    # not a backtest of historical membership. New listings remain explicit rows.
    universe, universe_meta = load_universe(root, dates["report_date"], refresh=refresh_universe, timeout=config["request_timeout_seconds"])
    validate_universe(universe)
    cache_root = root / "output/boll/state/history"
    cache_root.mkdir(parents=True, exist_ok=True)
    imported = import_evidence(import_history, cache_root, dates["market_date"])
    seed = root / "output/boll/bootstrap/history.jsonl.gz"
    imported += import_seed(seed, cache_root, dates["market_date"])
    print(json.dumps({"stage": "universe", "count": len(universe), "fresh": universe_meta.get("fresh"), "imported": imported}), flush=True)
    quotes, quote_meta = ({}, {"skipped": True}) if skip_quotes else fetch_quotes(universe, run_dir, timeout=config["request_timeout_seconds"])
    output, pending, codes = {}, {}, iter(universe)
    deadline = started + max_seconds
    def get_history(stock):
        if cached_only:
            cached = load_cache(cache_root / (stock["code"] + ".json.gz"), stock["code"], dates["market_date"])
            return {**cached, "fetch_status": "success", "update_method": "cache_hit"} if cached else {
                "code": stock["code"], "fetch_status": "failed", "errors": ["not_cached"], "update_method": "cache_miss"}
        return fetch_history(stock, dates["market_date"], cache_root,
                             previous_session=dates["previous_session"], quote=quotes.get(stock["code"]),
                             timeout=config["request_timeout_seconds"], retry_count=config["retry_count"])
    def submit(pool):
        if clock.monotonic() >= deadline:
            return
        stock = next(codes, None)
        if stock:
            future = pool.submit(get_history, stock)
            pending[future] = stock
    with ThreadPoolExecutor(max_workers=workers or config["history_workers"]) as pool:
        for _ in range(workers or config["history_workers"]):
            submit(pool)
        while pending:
            ready, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in ready:
                stock = pending.pop(future)
                try:
                    evidence = future.result()
                    output[stock["code"]] = assemble_record(stock, evidence, dates["market_date"], config, dates["expected_sessions"], quotes.get(stock["code"]))
                except Exception as exc:
                    output[stock["code"]] = {"code": stock["code"], "name": stock.get("name"), "exchange": stock["exchange"],
                                            "market_date": dates["market_date"], "status": "unresolved", "reasons": [type(exc).__name__ + ":" + str(exc)[:200]],
                                            "ranking": {"eligible": False}}
                submit(pool)
            if len(output) % 100 < len(ready):
                progress = {"run_id": run_id, "processed": len(output), "expected": len(universe),
                            "elapsed_s": round(clock.monotonic() - started, 1), "statuses": dict(Counter(x["status"] for x in output.values()))}
                write_json(root / "output/boll/state/progress.json", progress)
                print(json.dumps(progress), flush=True)
    for stock in universe:
        if stock["code"] not in output:
            output[stock["code"]] = {"code": stock["code"], "name": stock.get("name"), "exchange": stock["exchange"],
                "market_date": dates["market_date"], "status": "unresolved", "reasons": ["time_budget_exhausted"], "ranking": {"eligible": False}}
    records = [output[code] for code in sorted(output)]
    summary = publish(root, run_dir, records, universe, universe_meta, dates, quotes, quote_meta, started_at, clock.monotonic() - started, config)
    preserve_bootstrap(root, universe, dates["market_date"])
    print(json.dumps({key: summary[key] for key in ("run_id", "market_date", "universe_count", "status_counts", "technical_screen_complete", "elapsed_seconds")}), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--phase", choices=("auto", "early", "noon", "close", "intraday"), default="auto")
    parser.add_argument("--market-date")
    parser.add_argument("--max-seconds", type=int, default=2400)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--import-history", type=Path)
    parser.add_argument("--no-refresh-universe", action="store_true")
    parser.add_argument("--skip-quotes", action="store_true")
    parser.add_argument("--cached-only", action="store_true", help="Verify/publish retained evidence without history network requests")
    args = parser.parse_args()
    result = run(args.root, phase=args.phase, market_date=args.market_date, max_seconds=args.max_seconds,
                 workers=args.workers, import_history=args.import_history,
                 refresh_universe=not args.no_refresh_universe, skip_quotes=args.skip_quotes, cached_only=args.cached_only)
    # A partial run is intentionally visible, with data preserved for resuming.
    return 0 if result["technical_screen_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
