"""Append dated launch observations and complete their frozen return windows."""

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, time
from hashlib import sha256
import gzip
import json
from pathlib import Path
from statistics import median

from pipeline.calendar import resolve_calendar

from report_support.market_funds import CHINA
from report_support.relaunch import KLINE, fetch_history, measure_base, parse_bars, recent_rising_turnover

FOLDER = Path("output/research/relaunch")
BASE_DATE = "2026-11-27"
BASELINE = f"events_{BASE_DATE}.json.gz"
STUDY = f"study_{BASE_DATE}.json"
HORIZON = 10
EPSILON = 1e-10
PENDING, GAP, MATURE = "待到期", "日线缺口", "已成熟"


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(payload)
    temp.replace(path)


@dataclass(frozen=True)
class Sessions:
    days: list[str]
    position: dict[str, int]

    @classmethod
    def from_repo(cls, path):
        data = json.loads(path.read_bytes())
        source = data["source"]
        days = sorted({date.fromisoformat(day).isoformat() for day in data["trade_dates"]})
        if not days or not isinstance(source, str) or not source.strip() or "fallback" in source.lower():
            raise ValueError("Trading calendar cache fails the source or date checks")
        return cls(days, {day: index for index, day in enumerate(days)})


def result_key(event):
    return event["code"] + "/" + event["launch"]


def outcome(bars_by_day, clock, clamped_date, event, mainboard):
    start = clock.position[event["launch"]]
    last = start + HORIZON - 1
    if last > clock.position[clamped_date]:
        return {"label_status": PENDING}
    days = clock.days[start:last + 1]
    if event["asof"] not in bars_by_day or any(day not in bars_by_day for day in days):
        return {"label_status": GAP}
    bars = [bars_by_day[day] for day in days]
    # Use one adjustment basis for the entire price path. The frozen trigger prices are never edited.
    prev = bars_by_day[event["asof"]].close
    launch = bars[0].close
    wave = max(row.close for row in bars) / prev - 1
    follow = max(row.close for row in bars[1:]) / launch - 1
    current = largest = 0
    threshold = 9.8 if mainboard else 19.8
    for row in bars:
        current = current + 1 if row.change_pct >= threshold else 0
        largest = max(largest, current)
    return {
        "label_status": MATURE, "label_end": days[-1], "wave_max": wave, "post_max": follow,
        "post_end": bars[-1].close / launch - 1, "large_rise_streak": largest,
        "wave30": wave >= .30 - EPSILON, "post15": follow >= .15 - EPSILON,
    }


def advance_known_highs(bars):
    peak, gain = bars[0], 0.0
    for i, bar in enumerate(bars):
        if bar.high > peak.high:
            peak = bar
        if i >= 20:
            gain = max(gain, bar.close / bars[i - 20].close - 1)
        yield peak, gain


def launch_row(stock, bars, i, clock, previous_t, highs, published_at):
    t, prev = bars[i], bars[i - 1]
    pos = clock.position[t.day]
    mainboard = stock["board"].endswith("主板")
    if (t.change_pct < (5 if mainboard else 8) or pos - previous_t <= HORIZON
            or pos < 120 or [row.day for row in bars[i - 10:i]] != clock.days[pos - 10:pos]):
        return None
    ten = measure_base(bars[i - 10:i])
    if t.close <= ten["high"]:
        return None
    twenty, sixty, long = (measure_base(bars[i - n:i]) for n in (20, 60, 120))
    full_history = [row.day for row in bars[i - 120:i]] == clock.days[pos - 120:pos]
    pre = bars[i - 25:i]
    amount5 = median(row.amount for row in pre[-5:])
    amount20 = median(row.amount for row in pre[:20])
    amount_multiple = t.amount / median(row.amount for row in pre[-20:])
    lift = recent_rising_turnover(pre)
    near20 = prev.close >= .95 * twenty["high"]
    near60 = prev.close >= .93 * sixty["high"]
    box60 = sixty["range_pct"] <= 30 and abs(sixty["close_change_pct"]) <= 12
    box120 = box60 and long["range_pct"] <= 40 and abs(long["close_change_pct"]) <= 15
    tight10 = ten["range_pct"] <= 12
    peak, gain = highs[i - 120]
    old_leader = gain >= .60 and pos - clock.position[peak.day] >= 120 and prev.close <= .8 * peak.high
    full20 = t.close > twenty["high"]
    burst = amount_multiple >= 1.5
    return {
        "sample": stock["sample"], "board": stock["board"], "code": stock["code"], "name": stock["name"],
        "launch": t.day, "asof": prev.day, "first_recorded_at": published_at,
        "base120_complete": full_history, "historical_leader": old_leader,
        "prior_peak_day": peak.day if old_leader else None, "prior_peak": peak.high if old_leader else None,
        "prior_close": prev.close, "trigger_open": t.open, "trigger_close": t.close,
        "trigger_pct": t.change_pct / 100, "one_price": t.high == t.low, "gap_pct": t.open / prev.close - 1,
        "prior10_low": ten["low"], "prior10_high": ten["high"], "prior20_high": twenty["high"],
        "prior60_high": sixty["high"], "range10": ten["range_pct"] / 100, "range20": twenty["range_pct"] / 100,
        "range60": sixty["range_pct"] / 100, "range120": long["range_pct"] / 100,
        "drift60": sixty["close_change_pct"] / 100, "drift120": long["close_change_pct"] / 100,
        "amount5_rel": amount5 / amount20, "trigger_amount_rel": amount_multiple,
        "base60": box60, "base120": box120, "tight10": tight10, "quiet5": amount5 <= .75 * amount20,
        "lift5": lift, "near20": near20, "near60": near60, "tight_and_lift": tight10 and lift,
        "near_and_lift": near20 and lift, "full20": full20, "burst": burst, "full_and_burst": full20 and burst,
    }


def watch_row(stock, bars):
    name = stock["name"]
    if len(bars) < 121 or name.upper().startswith(("ST", "*ST", "退市")) or name.endswith("退"):
        return None
    older = bars[:-120]
    if len(older) < 21:
        return None
    peak, gain = list(advance_known_highs(older))[-1]
    last = bars[-1]
    top = max(row.high for row in bars[-20:])
    if gain < .60 or last.close > .8 * peak.high or last.close < .95 * top or not recent_rising_turnover(bars):
        return None
    window = measure_base(bars[-20:])
    return {
        "code": stock["code"], "name": stock["name"], "market_date": last.day, "price": last.close,
        "prior_peak": peak.high, "prior_peak_date": peak.day, "watch_level": top,
        "window_low": window["low"], "near_and_lift": True,
        "one_price": last.high == last.low,
    }


def fetch_bars(code, asof, offline_root=None):
    try:
        if offline_root:
            payload = json.loads((offline_root / (code + ".json")).read_bytes())["data"]
            payload = {**payload, "klines": [row for row in payload["klines"] if row.split(",", 1)[0] <= asof]}
        else:
            payload = fetch_history(code, asof)
        if payload["code"] != code:
            raise ValueError("history symbol mismatch")
        bars = parse_bars(payload, asof)
        return bars, payload["name"], None if bars and bars[-1].day == asof else "no_current_close"
    except (OSError, KeyError, TypeError, ValueError):
        return [], None, "history_unavailable"


def count_rows(rows):
    return {field: sum(row.get(field) is True for row in rows) for field in ("wave30", "post15", "historical_leader")}


def compute(root, target, clock, offline_root=None):
    folder = root / FOLDER
    baseline_bytes = (folder / BASELINE).read_bytes()
    baseline = json.loads(gzip.decompress(baseline_bytes))
    if baseline["asof"] != BASE_DATE:
        raise ValueError("Unexpected baseline date")
    study_hash = sha256((folder / STUDY).read_bytes()).hexdigest()
    state_file, manifest_file = folder / "rolling.json.gz", folder / "manifest.json"
    base_hash = sha256(baseline_bytes).hexdigest()
    state = json.loads(gzip.decompress(state_file.read_bytes())) if state_file.exists() else {
        "baseline_sha256": base_hash, "through": {}, "events": [], "outcomes": {}, "watch": {},
    }
    if state["baseline_sha256"] != base_hash:
        raise ValueError("Ledger was made from a different historical baseline")
    manifest = json.loads(manifest_file.read_bytes()) if manifest_file.exists() else {
        "schema_version": 1, "daily": {}, "baseline": {"file": str(FOLDER / BASELINE), "sha256": base_hash},
        "study": {"file": str(FOLDER / STUDY), "sha256": study_hash, "asof": BASE_DATE},
    }
    latest = manifest.get("latest")
    if latest and latest["market_date"] > target:
        raise ValueError("Refusing to move the live ledger to an earlier date")
    same_day = latest and latest["market_date"] == target
    if same_day:
        payload = (root / latest["file"]).read_bytes()
        if sha256(payload).hexdigest() != latest["sha256"]:
            raise ValueError("Existing daily reader hash mismatch")
        today = json.loads(payload)
        if today["status"] == "complete":
            print(f"{target}: already current")
            return False
    else:
        today = {"new_events": [], "updated_outcomes": {}, "watch_added": {}, "watch_removed": {}}
        if not latest:
            today["baseline_date_events"] = [event for event in baseline["events"] if event["launch"] == target]

    by_code = {stock["code"]: stock for stock in baseline["stocks"]}
    active = [code for code, stock in by_code.items() if stock["last"] == BASE_DATE]
    all_events = baseline["events"] + state["events"]
    events_by_code = {code: [] for code in active}
    for event in all_events:
        if event["code"] in events_by_code:
            events_by_code[event["code"]].append(event)
    work = [code for code in active if state["through"].get(code) != target]
    if same_day and not work:
        return False
    now = datetime.now(CHINA).isoformat(timespec="microseconds")
    failures = dict(today.get("quote_gaps", {}))
    prior_days = clock.days[clock.position[target] - 10:clock.position[target]]
    trigger_gaps = dict(today.get("trigger_gaps", {}))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = pool.map(lambda code: fetch_bars(code, target, offline_root), work)
        for code, (bars, name, error) in zip(work, results):
            if error:
                failures[code] = error
            else:
                failures.pop(code, None)
                if len(bars) < 121 or [row.day for row in bars[-11:-1]] != prior_days:
                    trigger_gaps[code] = "missing_pretrigger_bars"
                else:
                    trigger_gaps.pop(code, None)
            stock = {**by_code[code], "name": name or by_code[code]["name"]}
            known = events_by_code[code]
            registered = {event["launch"] for event in known}
            previous_t = max((clock.position[d] for d in registered), default=-HORIZON-1)
            frontier = state["through"].get(code, BASE_DATE)
            if not error and target > frontier:
                highs = list(advance_known_highs(bars))
                for i in range(120, len(bars)):
                    day = bars[i].day
                    if day <= frontier or day in registered or day not in clock.position:
                        continue
                    event = launch_row(stock, bars, i, clock, previous_t, highs, now)
                    if event:
                        event["label_status"] = PENDING
                        known.append(event)
                        state["events"].append(event)
                        today["new_events"].append(event)
                        previous_t = clock.position[day]
            lookup = {row.day: row for row in bars}
            for event in known:
                key = result_key(event)
                previous = state["outcomes"].get(key, event)
                initial_gap = event.get("label_status") == GAP and event["launch"] <= BASE_DATE
                if previous["label_status"] == MATURE or initial_gap:
                    continue
                resolved = outcome(lookup, clock, target, event, stock["board"].endswith("主板"))
                if resolved["label_status"] != previous["label_status"]:
                    receipt = {**resolved, "code": code, "name": stock["name"], "launch": event["launch"],
                               "outcome_published_at": now, "outcome_checked_on": target}
                    state["outcomes"][key] = receipt
                    today["updated_outcomes"][key] = receipt
            if error:
                continue
            state["through"][code] = target
            watch = watch_row(stock, bars)
            previous = state["watch"].get(code)
            if watch:
                state["watch"][code] = watch
                if previous is None:
                    today["watch_added"][code] = watch
            elif previous is not None:
                state["watch"].pop(code)
                today["watch_removed"][code] = {**previous, "condition_lost_on": target}

    all_events = baseline["events"] + state["events"]
    merged = [{**event, **state["outcomes"].get(result_key(event), {})} for event in all_events]
    label_counts = {label: sum(row["label_status"] == label for row in merged) for label in (PENDING, GAP, MATURE)}
    eligible = [row for row in merged if row["launch"] > BASE_DATE and row["label_status"] == MATURE
                and row["base120_complete"] and row["first_recorded_at"][:10] == row["launch"]]
    comparisons = {}
    for factor in ("lift5", "near_and_lift", "base60", "base120"):
        comparisons[factor] = {
            group: {"n": len(part), **count_rows(part)}
            for group, part in (("matched", [row for row in eligible if row[factor]]),
                                ("other", [row for row in eligible if not row[factor]]))
        }
    active_watch = [watch for watch in state["watch"].values() if watch["market_date"] == target]
    now = datetime.now(CHINA)
    today.update(
        schema_version=1, market_date=target, published_at=now.isoformat(timespec="microseconds"),
        status="partial" if failures else "complete", data_basis="completed_daily_forward_adjusted_price_proxy",
        data_source=KLINE, tracked_codes=len(active), historical_only=len(by_code) - len(active),
        current_codes=len(active) - len(failures), quote_gaps=failures, trigger_gaps=trigger_gaps,
        totals={"signals": len(merged), "outcomes": label_counts, **count_rows(merged),
                "relaunch_waves": sum(row["historical_leader"] and row.get("wave30") is True for row in merged)},
        next_session_watch=sorted(active_watch, key=lambda row: row["code"]),
        forward_comparisons=comparisons, study=manifest["study"],
    )
    immutable = FOLDER / "daily" / target / (now.strftime("%H%M%S_%f") + ".json")
    raw = json_bytes(today)
    pointer = {"market_date": target, "published_at": today["published_at"], "status": today["status"],
               "file": str(immutable), "sha256": sha256(raw).hexdigest()}
    manifest["daily"].setdefault(target, []).append(pointer)
    manifest["latest"] = pointer
    atomic_write(root / immutable, raw)
    atomic_write(state_file, gzip.compress(json_bytes(state), mtime=0))
    atomic_write(manifest_file, json_bytes(manifest))
    print(json.dumps({"market_date": target, "status": today["status"], "codes": today["current_codes"],
                      "new": len(today["new_events"]), "outcomes": len(today["updated_outcomes"]),
                      "signals": len(merged)}, ensure_ascii=False))
    return True


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--asof", type=date.fromisoformat, help="Optional date for local regression checks")
    parser.add_argument("--offline-root", type=Path, help="Use captured quotes for local tests")
    args = parser.parse_args()
    root = args.root.resolve()
    now = datetime.now(CHINA)
    calendar_path = root / "output/cache/trade_calendar.json"
    clock = Sessions.from_repo(calendar_path)
    calendar = resolve_calendar(now, root, ak_module=None)
    if not calendar.valid:
        raise ValueError("Current market date could not be verified")
    if args.asof and not args.offline_root:
        parser.error("--asof requires captured input for a local check")
    if not args.asof and (not calendar.is_trading_day or now.time() < time(15, 10)):
        print("No completed trading day to record")
        return
    target = args.asof.isoformat() if args.asof else calendar.latest_completed_trading_day
    if target < BASE_DATE or target > calendar.latest_completed_trading_day or target not in clock.position:
        raise ValueError("Ledger needs a completed trading date at or after its baseline")
    compute(root, target, clock, args.offline_root)


if __name__ == "__main__":
    main()
