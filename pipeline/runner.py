from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline import SCHEMA_VERSION
from pipeline.adapters import AdapterResult
from pipeline.adapters.market_overview import collect_market_overview
from pipeline.adapters.point_in_time import recover_fixed_point_in_time
from pipeline.adapters.stock_quotes import collect_stock_quotes
from pipeline.calendar import CalendarInfo, resolve_calendar
from pipeline.contracts import ContractError, load_json, load_report_pools
from pipeline.publisher import PublishResult, publish_snapshot, verify_pointer, write_health
from pipeline.quality import apply_quality_result, evaluate_quality


TIMEZONE = ZoneInfo("Asia/Shanghai")
SNAPSHOT_TYPES = {"early", "noon", "close", "evening", "intraday"}
SNAPSHOT_MODES = {"light", "full"}
PROFILE_BY_TYPE = {
    "early": "trading_preopen",
    "noon": "trading_noon",
    "close": "trading_close",
    "evening": "trading_evening",
    "intraday": "trading_intraday",
}
SESSION_BY_TYPE = {
    "early": "preopen",
    "noon": "noon_close",
    "close": "market_close",
    "evening": "evening_verified",
    "intraday": "morning",
}
SUITABLE_REPORTS = {
    "early": ["early"],
    "noon": ["noon"],
    "close": ["evening"],
    "evening": ["evening"],
    "intraday": ["noon", "evening"],
}


@dataclass(frozen=True)
class RunOptions:
    snapshot_type: str
    mode: str
    planned_at: str
    attempt_role: str
    report_date: str | None = None
    moment: datetime | None = None

    def validate(self) -> None:
        if self.snapshot_type not in SNAPSHOT_TYPES:
            raise ValueError(f"Unsupported snapshot_type: {self.snapshot_type}")
        if self.mode not in SNAPSHOT_MODES:
            raise ValueError(f"Unsupported mode: {self.mode}")
        datetime.strptime(self.planned_at, "%H:%M")
        if self.report_date is not None:
            datetime.strptime(self.report_date, "%Y-%m-%d")


@dataclass(frozen=True)
class RunResult:
    grade: str
    published: bool
    reason: str
    snapshot_id: str | None
    health_path: Path
    publish_result: PublishResult | None = None


def run_pipeline(
    options: RunOptions,
    root: Path,
    calendar_resolver: Callable[[datetime, Path], CalendarInfo] = resolve_calendar,
    stock_collector: Callable[[Path, datetime, str, str], tuple[AdapterResult, pd.DataFrame]] = collect_stock_quotes,
    market_collector: Callable[[pd.DataFrame, str, datetime], AdapterResult] = collect_market_overview,
    point_in_time_recoverer: Callable[
        [AdapterResult, AdapterResult, str, str, str, datetime],
        tuple[AdapterResult, AdapterResult],
    ] = recover_fixed_point_in_time,
) -> RunResult:
    options.validate()
    started = (options.moment or datetime.now(TIMEZONE)).astimezone(TIMEZONE)
    report_date = options.report_date or started.date().isoformat()
    planned_at = f"{report_date}T{options.planned_at}:00+08:00"
    if _expired_scheduled_run(options, started, planned_at):
        return _skipped_run(options, root, started, planned_at)
    calendar = calendar_resolver(started, root)
    profile = "non_trading" if not calendar.is_trading_day else PROFILE_BY_TYPE[options.snapshot_type]
    if options.attempt_role.startswith("retry-") and _already_ready(root, report_date, options.snapshot_type):
        return _skipped_run(
            options, root, started, planned_at,
            status="skipped_ready", reason="a verified A-grade snapshot for this cycle already exists",
        )

    if options.snapshot_type == "evening" and profile != "non_trading":
        recovery_reason = None
        if not _same_day_close_available(root, report_date):
            recovery = run_pipeline(
                RunOptions(
                    snapshot_type="close",
                    mode="full",
                    planned_at="15:20",
                    attempt_role=f"{options.attempt_role}-close-recovery",
                    report_date=report_date,
                    moment=started,
                ),
                root,
                calendar_resolver=calendar_resolver,
                stock_collector=stock_collector,
                market_collector=market_collector,
                point_in_time_recoverer=point_in_time_recoverer,
            )
            if recovery.grade == "F":
                recovery_reason = f"automatic close recovery failed: {recovery.reason}"
        return _run_evening(
            options,
            root,
            started,
            report_date,
            planned_at,
            calendar,
            recovery_reason=recovery_reason,
        )

    market_date = (
        calendar.latest_completed_trading_day
        if profile in {"trading_preopen", "non_trading"}
        else report_date
    )
    previous_close = (
        _verified_previous_close_snapshot(root, market_date)
        if profile in {"trading_preopen", "non_trading"} else None
    )
    if previous_close and _previous_close_covers_pool(previous_close):
        stock_result = _stocks_from_previous_close(previous_close, started)
        market_result = _market_from_previous_close(previous_close, started)
    else:
        stock_result, spot_quotes = stock_collector(root, started, market_date, options.mode)
        market_result = market_collector(spot_quotes, stock_result.source, started)
        if previous_close:
            market_result = _market_from_previous_close(previous_close, started)
    if profile == "trading_noon":
        _annotate_noon_volume(root, stock_result.data["stocks"], report_date)
    published_at = datetime.now(TIMEZONE).isoformat(timespec="seconds")
    snapshot = _build_snapshot(
        options=options,
        report_date=report_date,
        planned_at=planned_at,
        started=started,
        published_at=published_at,
        calendar=calendar,
        profile=profile,
        market_date=market_date,
        stock_result=stock_result,
        market_result=market_result,
        collection_mode="live_or_latest_completed",
    )
    quality = evaluate_quality(snapshot, profile)
    if quality.grade == "F" and _recovery_target_reached(profile, report_date, started):
        try:
            stock_result, market_result = point_in_time_recoverer(
                stock_result,
                market_result,
                profile,
                report_date,
                market_date,
                started,
            )
            if profile == "trading_noon":
                _annotate_noon_volume(root, stock_result.data["stocks"], report_date)
            published_at = datetime.now(TIMEZONE).isoformat(timespec="seconds")
            snapshot = _build_snapshot(
                options=options,
                report_date=report_date,
                planned_at=planned_at,
                started=started,
                published_at=published_at,
                calendar=calendar,
                profile=profile,
                market_date=market_date,
                stock_result=stock_result,
                market_result=market_result,
                collection_mode="historical_point_in_time_recovery",
            )
            quality = evaluate_quality(snapshot, profile)
        except Exception as exc:
            snapshot["warnings"].append(f"历史时点恢复失败：{str(exc)[:400]}")
    apply_quality_result(snapshot, quality)
    if quality.grade == "F":
        health = _health_payload(options, started, snapshot, False, "quality gate failed")
        health_path = write_health(root, health)
        return RunResult("F", False, "quality gate failed", snapshot["snapshot_id"], health_path)

    publish_result = publish_snapshot(snapshot, root, calendar.as_manifest())
    health = _health_payload(options, started, snapshot, publish_result.published, publish_result.reason)
    health_path = write_health(root, health)
    return RunResult(
        quality.grade,
        publish_result.published,
        publish_result.reason,
        snapshot["snapshot_id"],
        health_path,
        publish_result,
    )


def _run_evening(
    options: RunOptions,
    root: Path,
    started: datetime,
    report_date: str,
    planned_at: str,
    calendar: CalendarInfo,
    recovery_reason: str | None = None,
) -> RunResult:
    manifest_path = root / "output" / "latest" / "manifest.json"
    if not manifest_path.exists():
        reason = recovery_reason or "close snapshot manifest is missing"
        return _evening_failure(options, root, started, reason)
    try:
        manifest = load_json(manifest_path)
        close_pointer = manifest.get("snapshots", {}).get("close")
        if close_pointer is None:
            raise ContractError("close pointer is missing")
        close_snapshot = verify_pointer(root, close_pointer)
    except ContractError as exc:
        return _evening_failure(options, root, started, str(exc))
    if close_snapshot.get("market_date") != report_date:
        return _evening_failure(options, root, started, "close snapshot market_date is not today")

    published_at = datetime.now(TIMEZONE).isoformat(timespec="seconds")
    snapshot = deepcopy(close_snapshot)
    snapshot.update(
        {
            "snapshot_id": _snapshot_id(report_date, options, started),
            "workflow_run_id": _workflow_run_id(started),
            "workflow_attempt": _workflow_attempt(),
            "snapshot_type": "evening",
            "snapshot_mode": "full",
            "quality_profile": "trading_evening",
            "quality_grade": "F",
            "quality_reasons": [],
            "blocking_reasons": [],
            "degradation_actions": [],
            "report_cycle": f"{report_date}-evening",
            "market_session": "evening_verified",
            "planned_at": planned_at,
            "started_at": started.isoformat(timespec="seconds"),
            "published_at": published_at,
            "realtime_expected": False,
            "based_on_snapshot_id": close_snapshot["snapshot_id"],
            "suitable_reports": ["evening"],
        }
    )
    snapshot["market"] = deepcopy(close_snapshot.get("market", {}))
    snapshot["market"]["base_close_grade"] = close_snapshot["quality_grade"]
    snapshot["validation"] = deepcopy(close_snapshot.get("validation", {}))
    snapshot["validation"].update(
        {
            "schema_valid": True,
            "calendar_valid": calendar.valid,
            "time_valid": True,
            "cross_field_valid": True,
            "base_snapshot_valid": True,
        }
    )
    quality = evaluate_quality(snapshot, "trading_evening")
    apply_quality_result(snapshot, quality)
    if quality.grade == "F":
        return _evening_failure(options, root, started, "; ".join(quality.blocking_reasons))
    publish_result = publish_snapshot(snapshot, root, calendar.as_manifest())
    health = _health_payload(options, started, snapshot, publish_result.published, publish_result.reason)
    health_path = write_health(root, health)
    return RunResult(
        quality.grade,
        publish_result.published,
        publish_result.reason,
        snapshot["snapshot_id"],
        health_path,
        publish_result,
    )


def _same_day_close_available(root: Path, report_date: str) -> bool:
    manifest_path = root / "output" / "latest" / "manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = load_json(manifest_path)
        pointer = manifest.get("snapshots", {}).get("close")
        if pointer is None:
            return False
        snapshot = verify_pointer(root, pointer)
    except ContractError:
        return False
    return snapshot.get("market_date") == report_date and snapshot.get("quality_grade") in {"A", "B"}


def _evening_failure(
    options: RunOptions, root: Path, started: datetime, reason: str
) -> RunResult:
    health = {
        "schema_version": SCHEMA_VERSION,
        "status": "not_ready",
        "snapshot_type": "evening",
        "snapshot_mode": options.mode,
        "attempt_role": options.attempt_role,
        "planned_at": options.planned_at,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        "quality_grade": "F",
        "published": False,
        "reason": reason,
    }
    path = write_health(root, health)
    return RunResult("F", False, reason, None, path)


def _build_snapshot(
    *,
    options: RunOptions,
    report_date: str,
    planned_at: str,
    started: datetime,
    published_at: str,
    calendar: CalendarInfo,
    profile: str,
    market_date: str,
    stock_result: AdapterResult,
    market_result: AdapterResult,
    collection_mode: str,
) -> dict[str, Any]:
    stocks = list(stock_result.data["stocks"])
    market = dict(market_result.data)
    market["latest_completed_trading_day"] = calendar.latest_completed_trading_day
    market["calendar_source"] = calendar.source
    quote_times = sorted(
        str(record["quote_time"])
        for record in stocks
        if record.get("valid_quote") and record.get("quote_time")
    )
    coverage = _coverage(stocks, market)
    pools = load_report_pools()
    present_codes = {record.get("code") for record in stocks}
    missing_core = [f"{record['code']}:quote" for record in stocks if record.get("pool") == "core" and not record.get("valid_quote")]
    missing_core.extend(f"{record['code']}:missing_record" for record in pools["core"]
                        if record["code"] not in present_codes)
    missing_optional = [
        f"{record['code']}:quote"
        for record in stocks
        if record.get("pool") in {"watch", "supplemental"} and not record.get("valid_quote")
    ]
    missing_optional.extend(f"{record['code']}:missing_record" for record in pools["watch"]
                            if record["code"] not in present_codes)
    if not market.get("turnover_valid"):
        missing_optional.append("total_turnover")
    if not market.get("breadth_valid"):
        missing_optional.append("market_breadth")
    for record in stocks:
        if record.get("locked") and not record.get("valid_quote"):
            missing_core.append(f"{record['code']}:locked_quote")
        if record.get("locked") and record.get("indicator_status") != "ready":
            missing_optional.append(f"{record['code']}:technical_indicators")
    if coverage["sectors_top"]["valid"] < 5:
        missing_optional.append("sectors_top")
    if coverage["sectors_bottom"]["valid"] < 5:
        missing_optional.append("sectors_bottom")

    realtime_expected = profile not in {"trading_preopen", "trading_evening", "non_trading"}
    time_valid = _initial_time_valid(profile, quote_times, planned_at, started, published_at)
    session = "non_trading" if profile == "non_trading" else _session_for(options.snapshot_type, started)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": _snapshot_id(report_date, options, started),
        "workflow_run_id": _workflow_run_id(started),
        "workflow_attempt": _workflow_attempt(),
        "snapshot_type": options.snapshot_type,
        "snapshot_mode": options.mode,
        "quality_profile": profile,
        "quality_grade": "F",
        "quality_reasons": [],
        "blocking_reasons": [],
        "degradation_actions": [],
        "report_date": report_date,
        "report_cycle": f"{report_date}-{options.snapshot_type}",
        "market_date": market_date,
        "market_session": session,
        "planned_at": planned_at,
        "started_at": started.isoformat(timespec="seconds"),
        "published_at": published_at,
        "collection_mode": collection_mode,
        "point_in_time_recovered": collection_mode == "historical_point_in_time_recovery",
        "schedule_delay_minutes": _schedule_delay_minutes(planned_at, started),
        "quote_time_min": quote_times[0] if quote_times else None,
        "quote_time_max": quote_times[-1] if quote_times else None,
        "realtime_expected": realtime_expected,
        "realtime_available": any(record.get("valid_quote") for record in stocks) if realtime_expected else False,
        "based_on_snapshot_id": None,
        "suitable_reports": SUITABLE_REPORTS[options.snapshot_type],
        "coverage": coverage,
        "missing_core_fields": missing_core,
        "missing_optional_fields": missing_optional,
        "warnings": [
            *stock_result.errors,
            *market_result.errors,
            *([calendar.warning] if calendar.warning else []),
        ],
        "validation": {
            "schema_valid": True,
            "time_valid": time_valid,
            "calendar_valid": calendar.valid,
            "cross_field_valid": market_date <= report_date,
        },
        "source_status": {
            "stock_quotes": stock_result.as_status(),
            "market_overview": market_result.as_status(),
        },
        "market": market,
        "stocks": stocks,
        "attempt_role": options.attempt_role,
        "risk_notice": "本快照只提供公开行情数据核验，不构成投资建议。",
    }
    return snapshot


def _coverage(stocks: list[dict[str, Any]], market: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pools = load_report_pools()
    expected_core = {item["code"] for item in pools["core"]}
    expected_watch = {item["code"] for item in pools["watch"]}
    core = {record.get("code") for record in stocks if record.get("pool") == "core"
            and record.get("code") in expected_core and record.get("valid_quote")}
    watch = {record.get("code") for record in stocks if record.get("pool") == "watch"
             and record.get("code") in expected_watch and record.get("valid_quote")}
    breadth = market.get("breadth", {})
    return {
        "indices": _coverage_item(len(market.get("indices", [])), 3),
        "core": _coverage_item(len(core), len(expected_core)),
        "watch": _coverage_item(len(watch), len(expected_watch)),
        "market_breadth": _coverage_item(sum(key in breadth for key in ("up", "down", "flat", "limit_up", "limit_down")), 5),
        "sectors_top": _coverage_item(len(market.get("sectors_top", [])), 5),
        "sectors_bottom": _coverage_item(len(market.get("sectors_bottom", [])), 5),
    }


def _coverage_item(valid: int, expected: int) -> dict[str, Any]:
    return {"valid": valid, "expected": expected, "ratio": 1.0 if expected == 0 else valid / expected}


def _initial_time_valid(
    profile: str, quote_times: list[str], planned_at: str, started: datetime, published_at: str
) -> bool:
    planned = datetime.fromisoformat(planned_at)
    published = datetime.fromisoformat(published_at)
    if not planned <= started <= published:
        return False
    if not quote_times:
        return profile == "non_trading"
    quotes = [datetime.fromisoformat(value) for value in quote_times]
    if any(quote > published for quote in quotes):
        return False
    if profile == "trading_intraday" and max(quotes) > planned + timedelta(minutes=20):
        return False
    if profile == "trading_noon" and max(quotes).time() > time(11, 35, 59):
        return False
    return True


def _expired_scheduled_run(options: RunOptions, started: datetime, planned_at: str) -> bool:
    # A queue entry from yesterday must never be relabelled with today's date.
    if options.attempt_role not in {"primary", "retry-1", "retry-2", "rolling"}:
        return False
    planned = datetime.fromisoformat(planned_at)
    if started < planned:
        return True
    if options.snapshot_type == "intraday":
        return started > planned + timedelta(minutes=20)
    deadlines = {"early": time(9, 5), "noon": time(12, 45), "close": time(20, 10), "evening": time(21, 5)}
    return started.time().replace(tzinfo=None) > deadlines[options.snapshot_type]


def _skipped_run(
    options: RunOptions, root: Path, started: datetime, planned_at: str,
    *, status: str = "skipped_expired",
    reason: str = "scheduled run missed its report window; no later quote was relabelled",
) -> RunResult:
    health_path = write_health(root, {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "snapshot_type": options.snapshot_type,
        "snapshot_mode": options.mode,
        "attempt_role": options.attempt_role,
        "planned_at": planned_at,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        "schedule_delay_minutes": _schedule_delay_minutes(planned_at, started),
        "quality_grade": "A" if status == "skipped_ready" else "F",
        "published": False,
        "reason": reason,
    })
    return RunResult("A" if status == "skipped_ready" else "F", False, reason, None, health_path)


def _already_ready(root: Path, report_date: str, snapshot_type: str) -> bool:
    if snapshot_type == "intraday":
        return False
    path = root / "output/latest/manifest.json"
    if not path.exists():
        return False
    try:
        manifest = load_json(path)
        pointer = manifest.get("snapshots", {}).get(snapshot_type)
        if not pointer or pointer.get("report_cycle") != f"{report_date}-{snapshot_type}":
            return False
        return verify_pointer(root, pointer).get("quality_grade") == "A"
    except (ContractError, OSError):
        return False


def _verified_previous_close_snapshot(root: Path, market_date: str) -> dict[str, Any] | None:
    path = root / "output/latest/manifest.json"
    if not path.exists():
        return None
    try:
        pointer = load_json(path).get("snapshots", {}).get("close")
        if not pointer:
            return None
        close = verify_pointer(root, pointer)
    except (ContractError, OSError):
        return None
    if close.get("market_date") != market_date or close.get("quality_grade") not in {"A", "B"}:
        return None
    return close


def _previous_close_covers_pool(close: dict[str, Any]) -> bool:
    pools = load_report_pools()
    expected = {item["code"] for group in ("core", "watch", "supplemental") for item in pools[group]}
    return expected.issubset({item["code"] for item in close.get("stocks", [])})


def _stocks_from_previous_close(close: dict[str, Any], started: datetime) -> AdapterResult:
    pools = load_report_pools()
    configured = {item["code"]: (group, item) for group in ("core", "watch", "supplemental") for item in pools[group]}
    stocks = []
    for base in close["stocks"]:
        if base["code"] not in configured:
            continue
        group, entry = configured[base["code"]]
        stock = deepcopy(base)
        stock["pool"] = group
        stock["locked"] = bool(entry.get("locked"))
        # Previous versions labelled raw daily history as qfq. Do not carry that claim forward.
        if stock.get("indicator_adjustment") == "qfq":
            stock["indicator_status"] = "missing"
            stock["indicator_adjustment"] = "unverified_legacy"
            stock["warnings"] = [*stock.get("warnings", []), "旧指标复权口径未验证，盘前不沿用。"]
        stocks.append(stock)
    valid = sum(bool(stock.get("valid_quote")) for stock in stocks)
    return AdapterResult(
        status="success" if valid == len(stocks) else "partial",
        source=f"verified previous close snapshot {close['snapshot_id']}",
        data={"stocks": stocks}, started_at=started,
        finished_at=datetime.now(TIMEZONE), records_expected=len(stocks), records_valid=valid,
    )


def _market_from_previous_close(close: dict[str, Any], started: datetime) -> AdapterResult:
    market_date = close["market_date"]
    market = deepcopy(close["market"])
    market["quote_source"] = f"verified previous close snapshot {close['snapshot_id']}"
    market["market_asof"] = market_date
    return AdapterResult(
        status="success", source=market["quote_source"], data=market,
        started_at=started, finished_at=datetime.now(TIMEZONE),
        records_expected=5, records_valid=5,
    )


def _annotate_noon_volume(root: Path, stocks: list[dict[str, Any]], report_date: str) -> None:
    """Compare noon turnover with the prior verified noon, never with a full day."""
    for stock in stocks:
        stock["same_phase_amount_ratio"] = None
        stock["same_phase_reference_date"] = None
    path = root / "output/latest/manifest.json"
    if not path.exists():
        return
    try:
        pointer = load_json(path).get("snapshots", {}).get("noon")
        if not pointer or pointer.get("report_cycle") == f"{report_date}-noon":
            return
        prior = verify_pointer(root, pointer)
    except (ContractError, OSError):
        return
    prior_date = prior.get("market_date")
    prior_quote = prior.get("quote_time_max")
    if not prior_date or prior_date >= report_date or not prior_quote:
        return
    if not time(11, 25) <= datetime.fromisoformat(prior_quote).time() <= time(11, 35, 59):
        return
    by_code = {item["code"]: item for item in prior.get("stocks", []) if item.get("valid_quote")}
    for stock in stocks:
        current_quote = stock.get("quote_time")
        if not stock.get("valid_quote") or stock.get("latest_trade_date") != report_date or not current_quote:
            continue
        quote_time = datetime.fromisoformat(current_quote).time()
        if not time(11, 25) <= quote_time <= time(11, 35, 59):
            continue
        earlier = by_code.get(stock["code"])
        daily_date_matches = prior_date in {
            stock.get("previous_trade_date"), stock.get("daily_latest_trade_date")
        }
        if not earlier or not daily_date_matches:
            continue
        earlier_quote = earlier.get("quote_time")
        if not earlier_quote or not time(11, 25) <= datetime.fromisoformat(earlier_quote).time() <= time(11, 35, 59):
            continue
        reference = earlier.get("today_amount")
        current = stock.get("today_amount")
        if isinstance(reference, (int, float)) and reference > 0 and isinstance(current, (int, float)) and current >= 0:
            stock["same_phase_amount_ratio"] = round(current / reference - 1, 4)
            stock["same_phase_reference_date"] = prior_date


def _recovery_target_reached(profile: str, report_date: str, started: datetime) -> bool:
    if profile == "trading_preopen":
        return started.date().isoformat() >= report_date
    if profile != "trading_noon":
        return False
    if started.date().isoformat() > report_date:
        return True
    return started.date().isoformat() == report_date and started.time().replace(tzinfo=None) >= datetime.strptime("11:30", "%H:%M").time()


def _schedule_delay_minutes(planned_at: str, started: datetime) -> float:
    try:
        planned = datetime.fromisoformat(planned_at).astimezone(TIMEZONE)
    except ValueError:
        return 0.0
    return round(max(0.0, (started - planned).total_seconds() / 60), 2)


def _session_for(snapshot_type: str, started: datetime) -> str:
    if snapshot_type != "intraday":
        return SESSION_BY_TYPE[snapshot_type]
    return "morning" if started.hour < 12 else "afternoon"


def _snapshot_id(report_date: str, options: RunOptions, started: datetime) -> str:
    run_id = _workflow_run_id(started)
    safe_run_id = re.sub(r"[^A-Za-z0-9_-]", "", run_id)[-24:]
    return f"{report_date.replace('-', '')}-{options.planned_at.replace(':', '')}-{options.snapshot_type}-{options.mode}-{safe_run_id}"


def _workflow_run_id(started: datetime) -> str:
    return os.environ.get("GITHUB_RUN_ID") or f"local{started.strftime('%Y%m%d%H%M%S')}"


def _workflow_attempt() -> int:
    try:
        return max(1, int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")))
    except ValueError:
        return 1


def _health_payload(
    options: RunOptions,
    started: datetime,
    snapshot: dict[str, Any],
    published: bool,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "published" if published else "not_published",
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_type": options.snapshot_type,
        "snapshot_mode": options.mode,
        "attempt_role": options.attempt_role,
        "planned_at": snapshot["planned_at"],
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        "quality_grade": snapshot["quality_grade"],
        "collection_mode": snapshot.get("collection_mode", "unknown"),
        "point_in_time_recovered": bool(snapshot.get("point_in_time_recovered")),
        "schedule_delay_minutes": snapshot.get("schedule_delay_minutes", 0),
        "quality_reasons": snapshot.get("quality_reasons", []),
        "blocking_reasons": snapshot.get("blocking_reasons", []),
        "coverage": snapshot.get("coverage", {}),
        "source_status": snapshot.get("source_status", {}),
        "published": published,
        "reason": reason,
    }
