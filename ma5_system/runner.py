from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd

from ma5_system import SCHEMA_VERSION, STRATEGY_ID
from pipeline.calendar import CalendarInfo, resolve_calendar
from ma5_system.config import load_strategy_config
from ma5_system.data import (
    HistoryStore,
    apply_industry_map,
    build_history_index,
    current_bars,
    fetch_all_a_spot,
    fetch_recent_qfq_histories,
    load_industry_map,
    normalize_spot_frame,
)
from ma5_system.events import fetch_event_risks
from ma5_system.market import enrich_index_trends
from ma5_system.intraday import apply_intraday_metrics, fetch_intraday_metrics
from ma5_system.publisher import PublishResult, publish_screen
from ma5_system.quality import assess_quality
from ma5_system.render import render_screen_markdown
from ma5_system.scoring import apply_direction_context, build_technical_record, market_score, rank_directions, score_stock
from pipeline.adapters.market_overview import collect_market_overview


TIMEZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class RunOptions:
    phase: str
    planned_at: str
    report_date: str | None = None
    moment: datetime | None = None
    archive_report: bool = False

    def validate(self) -> None:
        if self.phase not in {"preclose", "close"}:
            raise ValueError("phase must be preclose or close")
        datetime.strptime(self.planned_at, "%H:%M")
        if self.report_date:
            datetime.strptime(self.report_date, "%Y-%m-%d")


@dataclass(frozen=True)
class RunResult:
    screen: dict[str, Any]
    publication: PublishResult
    report_path: Path | None


def run_scan(
    options: RunOptions,
    root: Path,
    spot_fetcher: Callable[[], tuple[pd.DataFrame, str, list[str]]] = fetch_all_a_spot,
    market_collector: Callable[..., Any] = collect_market_overview,
    index_enricher: Callable[[list[dict[str, Any]], datetime], tuple[list[dict[str, Any]], list[str]]] = enrich_index_trends,
    event_provider: Callable[[list[str], str], tuple[dict[str, list[dict[str, str]]], list[str]]] = fetch_event_risks,
    minute_provider: Callable[[list[str], datetime], tuple[dict[str, dict[str, Any]], list[str]]] = fetch_intraday_metrics,
    history_provider: Callable[[list[str], datetime], tuple[pd.DataFrame, list[str]]] = fetch_recent_qfq_histories,
    calendar_resolver: Callable[[datetime, Path], CalendarInfo] = resolve_calendar,
    config: dict[str, Any] | None = None,
) -> RunResult:
    options.validate()
    config = config or load_strategy_config()
    started = (options.moment or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    report_date = options.report_date or started.date().isoformat()
    calendar = calendar_resolver(started, root)
    calendar_valid_for_report = bool(calendar.valid and calendar.date == report_date)
    market_date = report_date if calendar.is_trading_day else calendar.latest_completed_trading_day
    long_holiday_risk = _is_long_holiday_gap(report_date, calendar.next_trading_day)
    raw_spot, source, source_errors = spot_fetcher()
    spot = normalize_spot_frame(raw_spot, started, config)
    industry_map = load_industry_map(root / "output" / "ma5" / "state" / "industry_map.csv")
    spot = apply_industry_map(spot, industry_map)
    history_store = HistoryStore(
        root / "output" / "ma5" / "state" / "daily_history.csv.gz",
        rolling_days=int(config["history"]["rolling_days"]),
    )
    history = history_store.load()
    history_index = build_history_index(history)
    previous_directions = _previous_directions(root)
    directions = rank_directions(spot, previous_directions)
    direction_by_name = {item["name"]: item for item in directions}
    history_ready = 0
    signals: list[dict[str, Any]] = []
    for row in spot.to_dict(orient="records"):
        code_history = history_index.get(row["code"], pd.DataFrame())
        if len(code_history) >= config["universe"]["minimum_history_days"]:
            history_ready += 1
        record = build_technical_record(row, code_history, market_date, options.phase, config)
        record = apply_direction_context(record, direction_by_name.get(record.get("industry")))
        record["daily_history_refreshed"] = False
        record["major_data_gap"] = not bool(record.get("technical_complete"))
        record["data_grade"] = "A" if row.get("valid_quote") and record.get("technical_complete") else "F"
        result = score_stock(record, record.get("direction_rank"), config)
        signals.append(result.card)
    preliminary = sorted(
        (signal for signal in signals if signal.get("eligible")),
        key=lambda item: (item.get("score", 0), item.get("amount", 0) or 0),
        reverse=True,
    )[:30]
    deep_codes = [item["code"] for item in preliminary]
    deep_history, deep_history_errors = history_provider(deep_codes, started) if deep_codes else (pd.DataFrame(), [])
    deep_history_index = build_history_index(deep_history)
    if deep_codes:
        deep_refreshed: list[dict[str, Any]] = []
        for signal in signals:
            if signal.get("code") not in deep_codes:
                deep_refreshed.append(signal)
                continue
            fresh_history = deep_history_index.get(signal["code"], pd.DataFrame())
            refreshed_record = build_technical_record(signal, fresh_history, market_date, options.phase, config)
            refreshed_record = apply_direction_context(
                refreshed_record,
                direction_by_name.get(refreshed_record.get("industry")),
            )
            refreshed_record["daily_history_refreshed"] = len(fresh_history) >= config["universe"]["minimum_history_days"]
            refreshed_record["major_data_gap"] = not bool(
                refreshed_record.get("technical_complete") and refreshed_record["daily_history_refreshed"]
            )
            refreshed_record["data_grade"] = (
                "A"
                if refreshed_record.get("valid_quote") and refreshed_record.get("technical_complete")
                else "F"
            )
            deep_refreshed.append(
                score_stock(refreshed_record, refreshed_record.get("direction_rank"), config).card
            )
        signals = deep_refreshed
    event_map, event_errors = event_provider(deep_codes, report_date) if deep_codes else ({}, [])
    minute_map, minute_errors = minute_provider(deep_codes, started) if deep_codes else ({}, [])
    deep_complete_codes = {
        code
        for code in deep_codes
        if len(deep_history_index.get(code, pd.DataFrame())) >= config["universe"]["minimum_history_days"]
        and code in event_map
        and (options.phase != "preclose" or code in minute_map)
    }
    deep_scan_complete = len(deep_complete_codes) >= min(10, len(deep_codes))
    if deep_codes:
        refreshed: list[dict[str, Any]] = []
        for signal in signals:
            signal["event_items"] = event_map.get(signal["code"], [])
            signal["long_holiday_risk"] = long_holiday_risk
            signal["event_risk"] = bool(signal["event_items"]) or long_holiday_risk
            signal["event_risk_reasons"] = [
                *(["long_holiday_ahead"] if long_holiday_risk else []),
                *(item.get("title", "event_window") for item in signal["event_items"]),
            ]
            signal["event_data_complete"] = signal["code"] in event_map
            signal = apply_intraday_metrics(signal, minute_map.get(signal["code"]) if signal["code"] in deep_codes else None)
            if signal["code"] in deep_codes:
                signal["major_data_gap"] = bool(
                    signal.get("major_data_gap")
                    or not signal.get("event_data_complete")
                    or not signal.get("intraday_data_complete")
                )
            refreshed.append(score_stock(signal, signal.get("direction_rank"), config).card)
        signals = refreshed
    deep_code_set = set(deep_codes)
    eligible = sorted(
        (
            signal
            for signal in signals
            if signal.get("eligible") and (not deep_code_set or signal.get("code") in deep_code_set)
        ),
        key=lambda item: (item.get("score", 0), item.get("amount", 0) or 0),
        reverse=True,
    )
    cards = eligible[: int(config["candidate"]["maximum_cards"])]
    overview = market_collector(raw_spot, source, started)
    market_data = overview.data if hasattr(overview, "data") else dict(overview or {})
    enriched_indices, index_errors = index_enricher(market_data.get("indices", []), started)
    market_data["indices"] = enriched_indices
    turnover_ratio = _turnover_ratio(spot, history, market_date)
    environment = market_score(spot, enriched_indices, directions, turnover_ratio, config)
    completed = (options.moment or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    valid_quotes = int(spot["valid_quote"].sum()) if not spot.empty else 0
    industry_ready = int((spot["valid_quote"] & (spot["industry"] != "Unknown")).sum()) if not spot.empty else 0
    quote_time_max = max((str(item) for item in spot.get("quote_time", []) if item), default=None)
    known_industries = int(spot.loc[spot["industry"] != "Unknown", "industry"].nunique()) if not spot.empty else 0
    required_directions = min(5, known_industries)
    market_complete = bool(
        len(enriched_indices) >= 3
        and all(item.get("trend_points") is not None for item in enriched_indices[:3])
        and required_directions > 0
        and len(directions) >= required_directions
        and turnover_ratio is not None
    )
    quality = assess_quality(
        len(spot),
        valid_quotes,
        history_ready,
        industry_ready,
        quote_time_max,
        cards,
        options.phase,
        completed,
        config,
        market_complete=market_complete,
        deep_scan_complete=deep_scan_complete,
        is_trading_day=calendar.is_trading_day,
        calendar_valid=calendar_valid_for_report,
    )
    if quality["grade"] != "A":
        for signal in signals:
            signal["a_plus"] = False
        for card in cards:
            card["a_plus"] = False
    actionable_candidates = [card for card in cards if card.get("a_plus")]
    best_a_plus = actionable_candidates[0] if actionable_candidates else None
    primary = (
        best_a_plus
        if best_a_plus
        and environment["maximum_position_pct"] >= 40
        and (quality["actionable"] or (options.phase == "close" and quality["grade"] == "A"))
        else None
    )
    scan_id = _scan_id(report_date, options.phase, started)
    screen = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": STRATEGY_ID,
        "scan_id": scan_id,
        "phase": options.phase,
        "report_date": report_date,
        "market_date": market_date,
        "planned_at": f"{report_date}T{options.planned_at}:00+08:00",
        "started_at": started.isoformat(timespec="seconds"),
        "completed_at": completed.isoformat(timespec="seconds"),
        "quote_time_max": quote_time_max,
        "data_source": source,
        "source_errors": [
            *source_errors,
            *getattr(overview, "errors", []),
            *index_errors,
            *event_errors,
            *minute_errors,
            *deep_history_errors,
            *([calendar.warning] if calendar.warning else []),
        ],
        "trading_calendar": {
            "is_trading_day": calendar.is_trading_day,
            "latest_completed_trading_day": calendar.latest_completed_trading_day,
            "source": calendar.source,
            "valid": calendar_valid_for_report,
            "report_date_matches_calendar": calendar.date == report_date,
        },
        "universe": {"normalized": len(spot), "valid_quotes": valid_quotes, "history_ready": history_ready, "industry_ready": industry_ready},
        "quality": quality,
        "market_environment": environment,
        "market_overview": market_data,
        "directions": directions[:5],
        "top10": cards,
        "primary_candidate": primary,
        "blocked_a_plus_candidate": best_a_plus if best_a_plus and primary is None else None,
        "cash_required": options.phase == "preclose" and primary is None,
        "most_likely_error": "板块强度在收盘前后快速反转，或一次MA5回踩被误判为趋势承接。",
        "close_confirmation_checks": _close_checks(primary, cards, options.phase),
        "signal_shards": [],
        "privacy": {"contains_positions": False, "contains_cost_basis": False, "contains_share_count": False},
    }
    publication = publish_screen(screen, signals, root)
    report_path = _archive_private_report(screen, publication, root) if options.archive_report else None
    stock_state_safe = bool(
        calendar_valid_for_report
        and calendar.is_trading_day
        and quality["universe_coverage"] >= config["quality"]["grade_a_universe_coverage"]
        and quality.get("quote_age_minutes") is not None
        and quality["quote_age_minutes"] <= config["quality"]["maximum_quote_age_minutes"]
    )
    if options.phase == "close" and valid_quotes > 0 and stock_state_safe:
        refreshed_history = history_store.merge(history, deep_history) if not deep_history.empty else history
        history_store.save(
            history_store.merge(
                refreshed_history,
                current_bars(spot[spot["valid_quote"]], market_date),
            )
        )
    return RunResult(screen, publication, report_path)


def _previous_directions(root: Path) -> list[str]:
    path = root / "output" / "ma5" / "latest" / "manifest.json"
    if not path.exists():
        return []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        pointer = manifest.get("scans", {}).get("close") or manifest.get("scans", {}).get("preclose")
        if not pointer:
            return []
        screen = json.loads((root / pointer["selected_file"]).read_text(encoding="utf-8"))
        return [item["name"] for item in screen.get("directions", [])[:3]]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _turnover_ratio(spot: pd.DataFrame, history: pd.DataFrame, market_date: str) -> float | None:
    current = pd.to_numeric(spot.get("amount", pd.Series(dtype=float)), errors="coerce").sum()
    if history.empty or current <= 0:
        return None
    prior = history.loc[history["date"].astype(str) < market_date]
    if prior.empty:
        return None
    latest_date = prior["date"].astype(str).max()
    previous = pd.to_numeric(prior.loc[prior["date"].astype(str) == latest_date, "amount"], errors="coerce").sum()
    return float(current / previous) if previous > 0 else None


def _scan_id(report_date: str, phase: str, moment: datetime) -> str:
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    return f"{report_date}-{phase}-{moment.strftime('%H%M%S')}-{run_id}"


def _is_long_holiday_gap(report_date: str, next_trading_day: str | None) -> bool:
    if not next_trading_day:
        return False
    try:
        return (date.fromisoformat(next_trading_day) - date.fromisoformat(report_date)).days > 3
    except ValueError:
        return False


def _close_checks(primary: dict[str, Any] | None, cards: list[dict[str, Any]], phase: str) -> list[str]:
    if phase == "close":
        return []
    if primary:
        return [
            f"{primary['name']}正式收盘是否仍在MA5 {primary['ma5']:.2f}之上。",
            f"是否有效站上确认价 {primary['confirmation_price']:.2f}，且未跌破硬失效位 {primary['hard_invalidation']:.2f}。",
            f"所属方向 {primary.get('industry') or '未知'} 是否仍保持前三。",
            "14:45临时MA5与15:20正式MA5的偏差是否改变候选资格。",
        ]
    return ["确认收盘后仍无A+候选；不得用次优候选替代。", "检查14:45临时MA5与正式收盘MA5差异。"]


def _archive_private_report(screen: dict[str, Any], publication: PublishResult, root: Path) -> Path:
    del publication
    if screen["phase"] == "preclose":
        path = root / "reports" / "MA5扫描" / screen["report_date"][:7] / f"{screen['report_date']} MA5尾盘扫描底稿.md"
    else:
        path = root / "reports" / "MA5扫描" / screen["report_date"][:7] / f"{screen['report_date']} MA5收盘确认.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_screen_markdown(screen), encoding="utf-8")
    return path
