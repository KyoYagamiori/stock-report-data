"""Ensure a current, fully accepted daily screen before the evening report."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

from .history import write_json
from .runner import TZ, resolve_dates, run


def accepted_screen(root: Path, expected_date: str, moment: datetime) -> dict:
    """Validate immutable bytes, date and coverage; never accept an older pass."""
    root = Path(root).resolve()
    reasons = []
    try:
        manifest = json.loads((root / "output/boll/latest/manifest.json").read_text())
    except (OSError, ValueError) as exc:
        return {"accepted": False, "reasons": ["manifest_unavailable:" + str(exc)]}
    pointers = [manifest.get(key, {}) for key in ("latest_screen", "latest_complete_screen")]
    for pointer in pointers:
        if pointer.get("market_date") != expected_date:
            continue
        try:
            path = (root / pointer["selected_file"]).resolve()
            if not path.is_relative_to(root / "output/boll/archive"):
                raise ValueError("screen_path_outside_immutable_archive")
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != pointer.get("sha256"):
                raise ValueError("screen_sha256_mismatch")
            screen = json.loads(raw)
            if screen.get("market_date") != expected_date:
                raise ValueError("screen_market_date_mismatch")
            stamp = datetime.fromisoformat(screen["published_at"])
            if stamp.tzinfo is None or stamp > moment:
                raise ValueError("invalid_or_future_publication")
            if not screen.get("technical_screen_complete") or not screen.get("universe_current"):
                raise ValueError("screen_or_official_membership_incomplete")
            counts = screen.get("status_counts", {})
            total = screen.get("universe_count", 0)
            if (not isinstance(total, int) or total <= 0
                    or not screen.get("all_codes_accounted_for")
                    or screen.get("unresolved_count") != 0
                    or counts.get("unresolved", 0) != 0
                    or counts.get("screened", 0) + counts.get("excluded", 0) != total):
                raise ValueError("coverage_accounting_incomplete")
            candidate_path = (root / screen["candidate_file"]).resolve()
            if not candidate_path.is_relative_to(path.parent):
                raise ValueError("candidate_file_outside_screen_archive")
            candidates = json.loads(candidate_path.read_text())
            if candidates.get("market_date") != expected_date or not candidates.get("screen_complete"):
                raise ValueError("candidate_date_or_coverage_mismatch")
            return {"accepted": True, "reasons": [], "market_date": expected_date,
                    "screen_file": pointer["selected_file"], "candidate_file": screen["candidate_file"],
                    "run_id": screen["run_id"], "published_at": screen["published_at"],
                    "universe_count": total, "status_counts": counts,
                    "universe_current": True, "technical_screen_complete": True,
                    "sha256_verified": True}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            reasons.append(str(exc))
    return {"accepted": False, "expected_market_date": expected_date,
            "reasons": reasons or ["no_complete_screen_for_latest_completed_session"]}


def ensure_daily(root: Path, *, max_seconds=2400, moment=None, collector=None) -> dict:
    """Try twice within one shared budget, and retain a visible daily audit."""
    from time import monotonic

    root = Path(root)
    now = moment or datetime.now(TZ)
    dates = resolve_dates(root, now, "auto")
    if dates["is_trading_day"] and (now.hour, now.minute) < (15, 10):
        raise ValueError("daily_close_update_requires_completed_session")
    target = dates["market_date"]
    gate = accepted_screen(root, target, now)
    started = monotonic()
    attempts = []
    collect = collector or run
    if not gate["accepted"]:
        for number in (1, 2):
            remaining = int(max_seconds - (monotonic() - started))
            if remaining <= 0:
                break
            budget = max(1, remaining // (3 - number))
            try:
                summary = collect(root, phase="close", max_seconds=budget)
                attempts.append({"attempt": number, "run_id": summary.get("run_id"),
                                 "technical_screen_complete": summary.get("technical_screen_complete"),
                                 "unresolved_count": summary.get("unresolved_count")})
            except Exception as exc:
                attempts.append({"attempt": number, "error": type(exc).__name__ + ":" + str(exc)[:500]})
            gate = accepted_screen(root, target, moment or datetime.now(TZ))
            if gate["accepted"]:
                break
    result = {"schema_version": "1.0", "report_date": dates["report_date"],
              "expected_market_date": target, "is_trading_day": dates["is_trading_day"],
              "checked_at": (moment or datetime.now(TZ)).isoformat(),
              "status": ("updated" if attempts else "already_current") if gate["accepted"] else "incomplete",
              "attempts": attempts, **gate,
              "policy": "Daily acceptance is required. Non-trading days retain the last completed session; never relabel old prices as new."}
    write_json(root / "output/boll/latest/daily_update.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--max-seconds", type=int, default=2400)
    args = parser.parse_args()
    if args.max_seconds <= 0:
        parser.error("--max-seconds must be positive")
    return 0 if ensure_daily(args.root, max_seconds=args.max_seconds)["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
