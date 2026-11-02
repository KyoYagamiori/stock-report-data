"""Classify an automation result by exact cycle, never by archive existence.

This is a decision helper for the existing verification task. There is no
GitHub-to-ChatGPT send API here, and no inferred delivery acknowledgement.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .index import CYCLES, validate_body

TZ = ZoneInfo("Asia/Shanghai")
TIMES = {"early": "09:00:00", "noon": "12:40:00", "evening": "21:00:00"}


def assess_delivery(task, report_date, cycle, *, moment):
    due = datetime.fromisoformat(report_date + "T" + TIMES[cycle] + "+08:00")
    if moment.astimezone(TZ) < due:
        return {"action": "not_due", "reason": "future_cycle"}
    if moment.astimezone(TZ).date().isoformat() != report_date:
        return {"action": "do_not_backfill", "reason": "past_report_date"}
    details = task.get("run_details") or {}
    last = details.get("last_run") or {}
    result = details.get("latest_result") or {}

    def same_cycle(record):
        try:
            stamp = datetime.fromisoformat(record["scheduled_for"].replace("Z", "+00:00"))
            return stamp.tzinfo is not None and stamp == due
        except (KeyError, AttributeError, TypeError, ValueError):
            return False

    if same_cycle(last) and last.get("recorded_status") == "in_progress":
        return {"action": "wait_for_active_run", "reason": "prevent_concurrent_duplicate",
                "run_id": last.get("id")}
    if same_cycle(result) and not result.get("is_failure_message") and result.get("chat_ref"):
        text = result.get("content_text", "")
        if result.get("content_truncated") and text.startswith(f"# {report_date} {CYCLES[cycle]}"):
            return {"action": "recorded_result_present", "reason": "tool_excerpt_truncated",
                    "run_id": result.get("run_id"), "device_delivery": "unknown"}
        try:
            validate_body(text, report_date, cycle)
            return {"action": "recorded_result_present", "reason": "complete_matching_chat_result",
                    "run_id": result.get("run_id"), "device_delivery": "unknown"}
        except (ValueError, TypeError):
            pass
    return {"action": "recover_same_cycle", "reason": last.get("recorded_status", "missing_matching_result")
            if same_cycle(last) else "missing_matching_run", "run_id": last.get("id")}
