"""Reuse a proven no-trade exclusion for the identical completed session only."""
from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from .quotes import parse_sina_quotes, validate_quote
from .technicals import PARAMETERS


def reuse_completed_exclusions(root: Path, records: list[dict], target: str, moment: datetime):
    """A resumed stock today does not erase its earlier no-trade session.

This never fabricates bars or updates quote timestamps, never fills a different
market date, and never replaces a currently screened record. All screen, shard
and original quote bytes must hash-match before the archived status is reused.
"""
    wanted = {r["code"] for r in records if r.get("status") == "unresolved"
              and r.get("reasons") == ["missing_target_session_bar"] and r.get("market_date") == target}
    if not wanted:
        return records
    root = Path(root).resolve()
    replacements = {}
    try:
        manifest = json.loads((root / "output/boll/latest/manifest.json").read_text())
        pointer = manifest["latest_complete_screen"]
        if pointer.get("market_date") != target:
            return records
        path = (root / pointer["selected_file"]).resolve()
        if not path.is_relative_to(root / "output/boll/archive"):
            raise ValueError("completed_screen_path_outside_archive")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != pointer.get("sha256"):
            raise ValueError("completed_screen_sha256_mismatch")
        screen = json.loads(raw)
        stamp = datetime.fromisoformat(screen["published_at"])
        counts = screen.get("status_counts", {})
        if (screen.get("market_date") != target or not screen.get("technical_screen_complete")
                or not screen.get("universe_current") or not screen.get("all_codes_accounted_for")
                or screen.get("unresolved_count") != 0 or screen.get("parameters") != PARAMETERS
                or counts.get("screened", 0) + counts.get("excluded", 0) != screen.get("universe_count")
                or stamp.tzinfo is None or stamp > moment):
            raise ValueError("completed_screen_not_accepted")
        seen = set()
        for ref in screen["record_shards"]:
            shard = (root / ref["file"]).resolve()
            # The publisher's shard ranges are just an optimization. Unknown
            # filenames are still read and verified rather than assumed empty.
            bounds = shard.stem.split("-")
            if len(bounds) == 2 and all(len(x) == 6 and x.isdigit() for x in bounds):
                if not any(bounds[0] <= code <= bounds[1] for code in wanted):
                    continue
            if not shard.is_relative_to(path.parent / "records"):
                raise ValueError("completed_record_path_outside_version")
            raw_shard = shard.read_bytes()
            if hashlib.sha256(raw_shard).hexdigest() != ref.get("sha256"):
                raise ValueError("completed_record_sha256_mismatch")
            rows = json.loads(raw_shard)["records"]
            if len(rows) != ref["count"]:
                raise ValueError("completed_record_count_mismatch")
            for row in rows:
                code = row.get("code")
                if code not in wanted:
                    continue
                if code in seen:
                    raise ValueError("duplicate_completed_exclusion")
                seen.add(code)
                if (row.get("market_date") != target or row.get("status") != "excluded"
                        or row.get("reasons") != ["no_trades_on_target_session"]):
                    continue
                quote = row.get("quote") or {}
                if quote.get("code") != code or validate_quote(quote, target, "close", now=moment) != ["no_trades"]:
                    continue
                relative = str(quote.get("raw_file", ""))
                marker = "output/boll/archive/"
                if marker not in relative:
                    continue
                relative = relative[relative.index(marker):]
                quote_path = (root / relative).resolve()
                if not quote_path.is_relative_to(path.parent / "quote_sources"):
                    raise ValueError("completed_quote_path_outside_version")
                raw_quote = quote_path.read_bytes()
                digest = hashlib.sha256(raw_quote).hexdigest()
                if digest != quote.get("raw_sha256"):
                    raise ValueError("completed_quote_sha256_mismatch")
                parsed = parse_sina_quotes(raw_quote).get(code, {})
                fields = ("code", "date", "time", "status", "open", "prev_close", "close", "high", "low", "volume", "amount")
                if any(parsed.get(key) != quote.get(key) for key in fields):
                    raise ValueError("completed_quote_raw_fields_mismatch")
                restored = copy.deepcopy(row)
                restored["update_method"] = "verified_same_session_no_trade_reuse"
                restored["completed_session_exclusion_evidence"] = {
                    "market_date": target, "screen_file": pointer["selected_file"], "screen_sha256": pointer["sha256"],
                    "record_file": ref["file"], "record_sha256": ref["sha256"],
                    "quote_source_file": relative, "quote_source_sha256": digest,
                    "scope_note": "No trades in this completed session only; not a claim about today's suspension or quote availability."}
                replacements[code] = restored
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [{**r, "completed_exclusion_reuse_error": str(exc)[:300]} if r.get("code") in wanted else r for r in records]
    return [replacements.get(r.get("code"), r) for r in records]
