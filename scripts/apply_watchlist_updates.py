from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


TIMEZONE = ZoneInfo("Asia/Shanghai")
ROOT = Path(os.environ.get("STOCK_DATA_ROOT", Path(__file__).resolve().parents[1]))

FIXED_COLUMNS = ["code", "name", "theme", "priority", "locked", "status", "note"]
WATCHLIST_COLUMNS = [
    "code",
    "name",
    "theme",
    "priority",
    "locked",
    "status",
    "source_report",
    "reason",
    "last_action",
    "note",
]
UPDATE_COLUMNS = ["code", "name", "theme", "reason", "action", "priority", "source_report", "note"]
HISTORY_COLUMNS = ["snapshot_at", *WATCHLIST_COLUMNS]
APPLIED_COLUMNS = [
    "applied_at",
    "code",
    "name",
    "theme",
    "action",
    "priority",
    "source_report",
    "note",
    "result",
    "message",
]

PRIORITY_ORDER = ["low", "medium", "high"]
VALID_PRIORITIES = set(PRIORITY_ORDER)
VALID_STATUSES = {"active", "inactive"}
VALID_ACTIONS = {"add", "keep", "upgrade", "downgrade", "remove", "inactive", "replace"}


@dataclass
class Paths:
    root: Path
    fixed_watchlist: Path
    watchlist: Path
    updates: Path
    archive_history: Path
    archive_applied: Path
    output_status_md: Path
    output_status_json: Path


def get_paths(root: Path = ROOT) -> Paths:
    return Paths(
        root=root,
        fixed_watchlist=root / "config" / "fixed_watchlist.csv",
        watchlist=root / "config" / "watchlist.csv",
        updates=root / "input" / "watchlist_updates.csv",
        archive_history=root / "archive" / "watchlist_history.csv",
        archive_applied=root / "archive" / "applied_watchlist_updates.csv",
        output_status_md=root / "output" / "latest" / "watchlist_status.md",
        output_status_json=root / "output" / "latest" / "watchlist_status.json",
    )


def now_iso() -> str:
    return datetime.now(TIMEZONE).isoformat(timespec="seconds")


def ensure_dirs(paths: Paths) -> None:
    for directory in [
        paths.root / "config",
        paths.root / "input",
        paths.root / "archive",
        paths.root / "output" / "latest",
        paths.root / "output" / "history",
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def normalize_code(value: Any) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else ""


def clean_text(value: Any) -> str:
    return "" if pd.isna(value) else str(value).strip()


def normalize_bool(value: Any) -> str:
    text = clean_text(value).lower()
    return "true" if text in {"true", "1", "yes", "y"} else "false"


def normalize_priority(value: Any, default: str = "medium") -> str:
    text = clean_text(value).lower()
    return text if text in VALID_PRIORITIES else default


def normalize_status(value: Any, default: str = "active") -> str:
    text = clean_text(value).lower()
    return text if text in VALID_STATUSES else default


def read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)
    for column in columns:
        if column not in df.columns:
            df[column] = ""
    return df[columns].fillna("")


def write_csv(df: pd.DataFrame, path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = df.copy()
    for column in columns:
        if column not in output.columns:
            output[column] = ""
    output[columns].to_csv(path, index=False, encoding="utf-8-sig")


def normalize_watchlist(df: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, str]] = []
    for _, row in df.iterrows():
        code = normalize_code(row.get("code", ""))
        if not code:
            continue
        records.append(
            {
                "code": code,
                "name": clean_text(row.get("name", "")),
                "theme": clean_text(row.get("theme", "")),
                "priority": normalize_priority(row.get("priority", "")),
                "locked": normalize_bool(row.get("locked", "")),
                "status": normalize_status(row.get("status", "")),
                "source_report": clean_text(row.get("source_report", "")) or "manual",
                "reason": clean_text(row.get("reason", "")),
                "last_action": clean_text(row.get("last_action", "")) or "keep",
                "note": clean_text(row.get("note", "")),
            }
        )
    if not records:
        return pd.DataFrame(columns=WATCHLIST_COLUMNS)
    normalized = pd.DataFrame(records, columns=WATCHLIST_COLUMNS)
    return normalized.drop_duplicates(subset=["code"], keep="last").reset_index(drop=True)


def normalize_fixed(df: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, str]] = []
    for _, row in df.iterrows():
        code = normalize_code(row.get("code", ""))
        if not code:
            continue
        note = clean_text(row.get("note", ""))
        records.append(
            {
                "code": code,
                "name": clean_text(row.get("name", "")),
                "theme": clean_text(row.get("theme", "")),
                "priority": normalize_priority(row.get("priority", "")),
                "locked": "true",
                "status": normalize_status(row.get("status", ""), "active"),
                "source_report": "fixed_watchlist",
                "reason": note,
                "last_action": "keep",
                "note": note or "固定观察",
            }
        )
    return pd.DataFrame(records, columns=WATCHLIST_COLUMNS)


def normalize_updates(df: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, str]] = []
    for _, row in df.iterrows():
        code = normalize_code(row.get("code", ""))
        action = clean_text(row.get("action", "")).lower()
        if not code and not action:
            continue
        records.append(
            {
                "code": code,
                "name": clean_text(row.get("name", "")),
                "theme": clean_text(row.get("theme", "")),
                "reason": clean_text(row.get("reason", "")),
                "action": action,
                "priority": clean_text(row.get("priority", "")).lower(),
                "source_report": clean_text(row.get("source_report", "")),
                "note": clean_text(row.get("note", "")),
            }
        )
    return pd.DataFrame(records, columns=UPDATE_COLUMNS)


def upsert_fixed_watchlist(watchlist: pd.DataFrame, fixed: pd.DataFrame) -> pd.DataFrame:
    current = normalize_watchlist(watchlist)
    for _, fixed_row in fixed.iterrows():
        code = fixed_row["code"]
        match = current["code"] == code
        if match.any():
            idx = current.index[match][0]
            for column in ["name", "theme", "priority", "locked", "status"]:
                current.at[idx, column] = fixed_row[column]
            if not current.at[idx, "reason"]:
                current.at[idx, "reason"] = fixed_row["reason"]
            if not current.at[idx, "note"]:
                current.at[idx, "note"] = fixed_row["note"]
        else:
            current = pd.concat([current, pd.DataFrame([fixed_row])], ignore_index=True)
    return current[WATCHLIST_COLUMNS].reset_index(drop=True)


def append_watchlist_history(watchlist: pd.DataFrame, paths: Paths, timestamp: str) -> None:
    history_rows = watchlist.copy()
    history_rows.insert(0, "snapshot_at", timestamp)
    existing = read_csv(paths.archive_history, HISTORY_COLUMNS)
    combined = pd.concat([existing, history_rows[HISTORY_COLUMNS]], ignore_index=True)
    write_csv(combined, paths.archive_history, HISTORY_COLUMNS)


def priority_index(priority: str) -> int:
    return PRIORITY_ORDER.index(normalize_priority(priority))


def bump_priority(priority: str) -> str:
    index = min(priority_index(priority) + 1, len(PRIORITY_ORDER) - 1)
    return PRIORITY_ORDER[index]


def lower_priority(priority: str) -> str:
    index = max(priority_index(priority) - 1, 0)
    return PRIORITY_ORDER[index]


def row_to_watchlist_record(row: pd.Series, default_action: str) -> dict[str, str]:
    return {
        "code": normalize_code(row.get("code", "")),
        "name": clean_text(row.get("name", "")),
        "theme": clean_text(row.get("theme", "")),
        "priority": normalize_priority(row.get("priority", ""), "medium"),
        "locked": "false",
        "status": "active",
        "source_report": clean_text(row.get("source_report", "")) or "manual_update",
        "reason": clean_text(row.get("reason", "")),
        "last_action": default_action,
        "note": clean_text(row.get("note", "")),
    }


def set_if_present(watchlist: pd.DataFrame, idx: int, update: pd.Series, columns: list[str]) -> None:
    for column in columns:
        value = clean_text(update.get(column, ""))
        if value:
            watchlist.at[idx, column] = value


def apply_one_update(watchlist: pd.DataFrame, update: pd.Series) -> tuple[pd.DataFrame, str, str]:
    code = update["code"]
    action = update["action"]
    if not code:
        return watchlist, "skipped", "缺少 6 位股票代码。"
    if action not in VALID_ACTIONS:
        return watchlist, "skipped", f"不支持的 action: {action or '(空)'}。"

    match = watchlist["code"] == code
    exists = bool(match.any())
    idx = int(watchlist.index[match][0]) if exists else -1

    if action in {"add", "replace"}:
        if exists:
            watchlist.at[idx, "status"] = "active"
            watchlist.at[idx, "last_action"] = action
            set_if_present(watchlist, idx, update, ["name", "theme", "reason", "source_report", "note"])
            priority = normalize_priority(update.get("priority", ""), "")
            if priority:
                watchlist.at[idx, "priority"] = priority
            message = "已重新激活或更新已有股票。"
        else:
            record = row_to_watchlist_record(update, action)
            watchlist = pd.concat([watchlist, pd.DataFrame([record])], ignore_index=True)
            message = "已新增股票。"

        if action == "replace":
            theme = clean_text(update.get("theme", ""))
            replaced: list[str] = []
            if theme:
                for old_idx, old_row in watchlist.iterrows():
                    old_code = old_row["code"]
                    if old_code == code:
                        continue
                    if (
                        old_row["theme"] == theme
                        and old_row["locked"] == "false"
                        and old_row["priority"] == "low"
                        and old_row["status"] == "active"
                    ):
                        watchlist.at[old_idx, "status"] = "inactive"
                        watchlist.at[old_idx, "last_action"] = "replace_inactive"
                        watchlist.at[old_idx, "reason"] = f"被同主题 replace 更新替换：{code}"
                        replaced.append(old_code)
            if replaced:
                message += f" 同主题低优先级动态股票已设为 inactive: {', '.join(replaced)}。"
        return watchlist, "applied", message

    if not exists:
        if action in {"keep", "upgrade", "downgrade"}:
            record = row_to_watchlist_record(update, action)
            watchlist = pd.concat([watchlist, pd.DataFrame([record])], ignore_index=True)
            return watchlist, "applied", "原观察池不存在，已按更新建议新增为 active。"
        return watchlist, "skipped", "观察池中不存在该股票，无法执行移除或 inactive。"

    locked = watchlist.at[idx, "locked"] == "true"
    if action == "keep":
        watchlist.at[idx, "status"] = "active"
        watchlist.at[idx, "last_action"] = "keep"
        set_if_present(watchlist, idx, update, ["reason", "source_report", "note"])
        return watchlist, "applied", "已保留并更新理由。"

    if action == "upgrade":
        current = watchlist.at[idx, "priority"]
        requested = normalize_priority(update.get("priority", ""), "")
        if requested and priority_index(requested) > priority_index(current):
            watchlist.at[idx, "priority"] = requested
        else:
            watchlist.at[idx, "priority"] = bump_priority(current)
        watchlist.at[idx, "status"] = "active"
        watchlist.at[idx, "last_action"] = "upgrade"
        set_if_present(watchlist, idx, update, ["reason", "source_report", "note"])
        return watchlist, "applied", "已提高优先级。"

    if action == "downgrade":
        current = watchlist.at[idx, "priority"]
        requested = normalize_priority(update.get("priority", ""), "")
        if requested and priority_index(requested) < priority_index(current):
            watchlist.at[idx, "priority"] = requested
        else:
            watchlist.at[idx, "priority"] = lower_priority(current)
        watchlist.at[idx, "last_action"] = "downgrade"
        set_if_present(watchlist, idx, update, ["reason", "source_report", "note"])
        return watchlist, "applied", "已降低优先级。"

    if action in {"remove", "inactive"}:
        if locked:
            watchlist.at[idx, "last_action"] = f"skip_{action}"
            set_if_present(watchlist, idx, update, ["reason", "source_report", "note"])
            return watchlist, "skipped_locked", "locked=true，已跳过移除或 inactive 请求。"
        watchlist.at[idx, "status"] = "inactive"
        watchlist.at[idx, "last_action"] = action
        set_if_present(watchlist, idx, update, ["reason", "source_report", "note"])
        return watchlist, "applied", "已设为 inactive，未物理删除。"

    return watchlist, "skipped", "未处理的更新。"


def append_applied_updates(records: list[dict[str, str]], paths: Paths) -> None:
    if not records:
        return
    existing = read_csv(paths.archive_applied, APPLIED_COLUMNS)
    combined = pd.concat([existing, pd.DataFrame(records, columns=APPLIED_COLUMNS)], ignore_index=True)
    write_csv(combined, paths.archive_applied, APPLIED_COLUMNS)


def clear_updates_file(paths: Paths) -> None:
    write_csv(pd.DataFrame(columns=UPDATE_COLUMNS), paths.updates, UPDATE_COLUMNS)


def summarize_watchlist(watchlist: pd.DataFrame, actions: list[dict[str, str]], timestamp: str) -> dict[str, Any]:
    active = watchlist[watchlist["status"] == "active"]
    locked = watchlist[watchlist["locked"] == "true"]
    high = active[active["priority"] == "high"]

    def names_for(action_names: set[str], result: str | None = None) -> list[str]:
        output: list[str] = []
        for record in actions:
            if record["action"] in action_names and (result is None or record["result"] == result):
                label = f'{record["name"] or record["code"]} {record["code"]}'.strip()
                output.append(label)
        return output

    skipped_locked = [
        f'{record["name"] or record["code"]} {record["code"]}: {record["message"]}'.strip()
        for record in actions
        if record["result"] == "skipped_locked"
    ]

    return {
        "generated_at": timestamp,
        "active_count": int(len(active)),
        "locked_count": int(len(locked)),
        "high_priority": [f'{row["name"]} {row["code"]}'.strip() for _, row in high.iterrows()],
        "added": names_for({"add", "replace"}, "applied"),
        "upgraded": names_for({"upgrade"}, "applied"),
        "downgraded": names_for({"downgrade"}, "applied"),
        "inactive": names_for({"remove", "inactive"}, "applied"),
        "skipped_locked_removals": skipped_locked,
        "actions": actions,
        "watchlist": watchlist.to_dict(orient="records"),
    }


def render_status_markdown(summary: dict[str, Any]) -> str:
    def bullet(items: list[str]) -> str:
        if not items:
            return "- 无"
        return "\n".join(f"- {item}" for item in items)

    return f"""# 观察池状态

生成时间：{summary["generated_at"]}

## 当前状态

- 当前 active 股票数量：{summary["active_count"]}
- 当前 locked 股票数量：{summary["locked_count"]}
- 当前 high priority 股票：
{bullet(summary["high_priority"])}

## 本次观察池更新

### 新增或替换
{bullet(summary["added"])}

### 提高优先级
{bullet(summary["upgraded"])}

### 降级
{bullet(summary["downgraded"])}

### 设为 inactive
{bullet(summary["inactive"])}

### 跳过的 locked 删除或 inactive 请求
{bullet(summary["skipped_locked_removals"])}

## 说明

- locked=true 的固定观察股票不会被自动删除。
- remove 默认只把股票设为 inactive，不做物理删除。
- 成功应用更新后，input/watchlist_updates.csv 会清空并保留表头，避免重复应用。
"""


def write_status_outputs(summary: dict[str, Any], paths: Paths) -> None:
    paths.output_status_json.parent.mkdir(parents=True, exist_ok=True)
    paths.output_status_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    paths.output_status_md.write_text(render_status_markdown(summary), encoding="utf-8")


def apply_updates(root: Path = ROOT, clear_input: bool = True) -> dict[str, Any]:
    paths = get_paths(root)
    ensure_dirs(paths)

    timestamp = now_iso()
    fixed = normalize_fixed(read_csv(paths.fixed_watchlist, FIXED_COLUMNS))
    watchlist = upsert_fixed_watchlist(read_csv(paths.watchlist, WATCHLIST_COLUMNS), fixed)
    updates = normalize_updates(read_csv(paths.updates, UPDATE_COLUMNS))

    append_watchlist_history(watchlist, paths, timestamp)

    applied_records: list[dict[str, str]] = []
    action_summaries: list[dict[str, str]] = []
    for _, update in updates.iterrows():
        before_name = clean_text(update.get("name", ""))
        watchlist, result, message = apply_one_update(watchlist, update)
        watchlist = upsert_fixed_watchlist(watchlist, fixed)
        record = {
            "applied_at": timestamp,
            "code": update["code"],
            "name": before_name,
            "theme": update["theme"],
            "action": update["action"],
            "priority": update["priority"],
            "source_report": update["source_report"],
            "note": update["note"],
            "result": result,
            "message": message,
        }
        applied_records.append(record)
        action_summaries.append(record)

    watchlist = normalize_watchlist(upsert_fixed_watchlist(watchlist, fixed))
    watchlist = watchlist.sort_values(
        by=["status", "priority", "locked", "code"],
        key=lambda col: col.map({"active": "0", "inactive": "1", "high": "0", "medium": "1", "low": "2", "true": "0", "false": "1"}).fillna(col),
    ).reset_index(drop=True)

    write_csv(watchlist, paths.watchlist, WATCHLIST_COLUMNS)
    append_applied_updates(applied_records, paths)

    if clear_input and len(updates) > 0:
        clear_updates_file(paths)

    summary = summarize_watchlist(watchlist, action_summaries, timestamp)
    write_status_outputs(summary, paths)
    return summary


def main() -> None:
    summary = apply_updates()
    print(
        f"Watchlist updated: active={summary['active_count']}, "
        f"locked={summary['locked_count']}, actions={len(summary['actions'])}"
    )


if __name__ == "__main__":
    main()
