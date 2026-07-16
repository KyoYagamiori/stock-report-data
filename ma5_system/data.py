from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
import re
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

import pandas as pd

try:
    import akshare as ak
except Exception:  # pragma: no cover - optional runtime dependency
    ak = None


TIMEZONE = ZoneInfo("Asia/Shanghai")
HISTORY_COLUMNS = [
    "date",
    "code",
    "name",
    "industry",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "turnover",
]

ALIASES = {
    "code": ("code", "symbol", "\u4ee3\u7801"),
    "name": ("name", "\u540d\u79f0"),
    "latest": ("latest", "trade", "current", "\u6700\u65b0\u4ef7"),
    "pct_change": ("pct_change", "changepercent", "change_pct", "\u6da8\u8dcc\u5e45"),
    "open": ("open", "\u4eca\u5f00"),
    "high": ("high", "\u6700\u9ad8"),
    "low": ("low", "\u6700\u4f4e"),
    "prev_close": ("prev_close", "settlement", "\u6628\u6536"),
    "volume": ("volume", "\u6210\u4ea4\u91cf"),
    "amount": ("amount", "\u6210\u4ea4\u989d"),
    "turnover": ("turnover", "turnover_rate", "\u6362\u624b\u7387"),
    "quote_time": ("quote_time", "ticktime", "\u65f6\u95f4", "\u66f4\u65b0\u65f6\u95f4"),
    "industry": ("industry", "\u6240\u5c5e\u884c\u4e1a", "\u884c\u4e1a"),
    "listing_date": ("listing_date", "\u4e0a\u5e02\u65f6\u95f4"),
}


def safe_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number) or number in (float("inf"), float("-inf")):
        return None
    return number


def normalize_code(value: Any) -> str:
    digits = "".join(char for char in str(value) if char.isdigit())
    return digits[-6:].zfill(6) if digits else ""


def board_for(code: str) -> str | None:
    if code.startswith(("000", "001", "002", "003")):
        return "sz_main"
    if code.startswith(("300", "301")):
        return "chinext"
    if code.startswith(("600", "601", "603", "605")):
        return "sh_main"
    if code.startswith("688"):
        return "star"
    return None


def limit_pct_for(code: str, name: str = "") -> float:
    if is_st_name(name):
        return 5.0
    if code.startswith(("300", "301", "688")):
        return 20.0
    return 10.0


def is_st_name(name: str) -> bool:
    return bool(re.match(r"^(?:\*ST|ST|SST)(?![A-Z])", str(name).strip().upper()))


def normalize_spot_frame(
    frame: pd.DataFrame,
    quote_at: datetime,
    config: dict[str, Any],
) -> pd.DataFrame:
    columns = {field: _find_column(frame, aliases) for field, aliases in ALIASES.items()}
    if columns["code"] is None or columns["latest"] is None:
        return pd.DataFrame(columns=[*ALIASES, "board", "valid_quote", "one_price_limit"])
    allowed = tuple(config["universe"]["allowed_prefixes"])
    records: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        code = normalize_code(row.get(columns["code"]))
        if not code.startswith(allowed) or board_for(code) is None:
            continue
        name = _clean_text(row.get(columns["name"])) if columns["name"] else ""
        latest = safe_number(row.get(columns["latest"]))
        volume = safe_number(row.get(columns["volume"])) if columns["volume"] else None
        suspended = latest in (None, 0.0) or volume == 0.0
        high = safe_number(row.get(columns["high"])) if columns["high"] else latest
        low = safe_number(row.get(columns["low"])) if columns["low"] else latest
        pct = safe_number(row.get(columns["pct_change"])) if columns["pct_change"] else None
        quote_time = _normalize_quote_time(
            row.get(columns["quote_time"]) if columns["quote_time"] else None,
            quote_at,
        )
        listing_date = _normalize_date(row.get(columns["listing_date"])) if columns["listing_date"] else None
        one_price = bool(
            latest is not None
            and high is not None
            and low is not None
            and abs(high - low) < 1e-8
            and pct is not None
            and abs(pct) >= limit_pct_for(code, name) - 0.05
        )
        records.append(
            {
                "code": code,
                "name": name,
                "board": board_for(code),
                "latest": latest,
                "pct_change": pct,
                "open": _value(row, columns["open"]),
                "high": high,
                "low": low,
                "prev_close": _value(row, columns["prev_close"]),
                "volume": volume,
                "amount": _value(row, columns["amount"]),
                "turnover": _value(row, columns["turnover"]),
                "quote_time": quote_time,
                "industry": _clean_text(row.get(columns["industry"])) if columns["industry"] else "",
                "listing_date": listing_date,
                "is_st": is_st_name(name),
                "suspended": suspended,
                "one_price_limit": one_price,
                "valid_quote": not suspended and latest is not None and quote_time is not None,
            }
        )
    return pd.DataFrame.from_records(records)


def fetch_all_a_spot(ak_module: Any = ak) -> tuple[pd.DataFrame, str, list[str]]:
    if ak_module is None:
        return pd.DataFrame(), "unavailable", ["AKShare is unavailable"]
    attempts = [
        ("AKShare stock_zh_a_spot", getattr(ak_module, "stock_zh_a_spot", None)),
        ("AKShare stock_zh_a_spot_em", getattr(ak_module, "stock_zh_a_spot_em", None)),
    ]
    errors: list[str] = []
    for source, fetcher in attempts:
        if fetcher is None:
            continue
        try:
            frame = fetcher()
            if frame is not None and not frame.empty:
                return frame, source, errors
            errors.append(f"{source} returned no rows")
        except Exception as exc:
            errors.append(f"{source} failed: {str(exc)[:240]}")
    return pd.DataFrame(), "unavailable", errors


class HistoryStore:
    def __init__(self, path: Path, rolling_days: int = 70):
        self.path = path
        self.rolling_days = rolling_days

    def load(self) -> pd.DataFrame:
        if not self.path.exists():
            return pd.DataFrame(columns=HISTORY_COLUMNS)
        frame = pd.read_csv(self.path, dtype={"code": str})
        for column in HISTORY_COLUMNS:
            if column not in frame.columns:
                frame[column] = None
        frame["code"] = frame["code"].map(normalize_code)
        frame["date"] = frame["date"].astype(str)
        return frame[HISTORY_COLUMNS]

    def save(self, frame: pd.DataFrame) -> None:
        target = frame.copy()
        if target.empty:
            return
        target["code"] = target["code"].map(normalize_code)
        target["date"] = target["date"].astype(str)
        target = target.sort_values(["code", "date"]).drop_duplicates(["code", "date"], keep="last")
        target = target.groupby("code", group_keys=False).tail(self.rolling_days)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        compression = "gzip" if self.path.suffix == ".gz" else None
        target[HISTORY_COLUMNS].to_csv(temp, index=False, compression=compression)
        temp.replace(self.path)

    def merge(self, existing: pd.DataFrame, additions: pd.DataFrame) -> pd.DataFrame:
        if existing.empty:
            return additions.copy()
        if additions.empty:
            return existing.copy()
        return pd.concat([existing, additions], ignore_index=True)


def current_bars(spot: pd.DataFrame, market_date: str) -> pd.DataFrame:
    if spot.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    bars = pd.DataFrame(
        {
            "date": market_date,
            "code": spot["code"],
            "name": spot["name"],
            "industry": spot["industry"],
            "open": spot["open"],
            "high": spot["high"],
            "low": spot["low"],
            "close": spot["latest"],
            "volume": spot["volume"],
            "amount": spot["amount"],
            "turnover": spot["turnover"],
        }
    )
    return bars[HISTORY_COLUMNS]


def build_history_index(history: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if history.empty:
        return {}
    return {
        str(code): group.sort_values("date").reset_index(drop=True)
        for code, group in history.groupby("code", sort=False)
    }


def fetch_history_for_codes(
    codes: Iterable[str],
    start_date: str,
    end_date: str,
    ak_module: Any = ak,
    workers: int = 8,
    fetcher: Callable[..., pd.DataFrame] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    if ak_module is None and fetcher is None:
        return pd.DataFrame(columns=HISTORY_COLUMNS), ["AKShare is unavailable"]
    history_fetcher = fetcher or ak_module.stock_zh_a_hist
    frames: list[pd.DataFrame] = []
    errors: list[str] = []

    def fetch(code: str) -> pd.DataFrame:
        raw = history_fetcher(symbol=code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        return normalize_history_frame(raw, code)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_by_code = {executor.submit(fetch, normalize_code(code)): normalize_code(code) for code in codes}
        for future in as_completed(future_by_code):
            code = future_by_code[future]
            try:
                frame = future.result()
                if frame.empty:
                    errors.append(f"{code}: no history")
                else:
                    frames.append(frame)
            except Exception as exc:
                errors.append(f"{code}: {str(exc)[:160]}")
    if not frames:
        return pd.DataFrame(columns=HISTORY_COLUMNS), errors
    return pd.concat(frames, ignore_index=True), errors


def fetch_recent_qfq_histories(
    codes: Iterable[str],
    moment: datetime,
    workers: int = 8,
) -> tuple[pd.DataFrame, list[str]]:
    start, end = bootstrap_date_range(moment)
    return fetch_history_for_codes(codes, start, end, workers=workers)


def normalize_history_frame(frame: pd.DataFrame, code: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    aliases = {
        "date": ("date", "\u65e5\u671f"),
        "name": ("name", "\u540d\u79f0"),
        "open": ("open", "\u5f00\u76d8"),
        "high": ("high", "\u6700\u9ad8"),
        "low": ("low", "\u6700\u4f4e"),
        "close": ("close", "\u6536\u76d8"),
        "volume": ("volume", "\u6210\u4ea4\u91cf"),
        "amount": ("amount", "\u6210\u4ea4\u989d"),
        "turnover": ("turnover", "\u6362\u624b\u7387"),
        "industry": ("industry", "\u6240\u5c5e\u884c\u4e1a"),
    }
    columns = {key: _find_column(frame, value) for key, value in aliases.items()}
    if columns["date"] is None or columns["close"] is None:
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    result = pd.DataFrame({"date": frame[columns["date"]].astype(str).str[:10], "code": normalize_code(code)})
    for field in ("name", "industry"):
        result[field] = frame[columns[field]].astype(str) if columns[field] else ""
    for field in ("open", "high", "low", "close", "volume", "amount", "turnover"):
        result[field] = pd.to_numeric(frame[columns[field]], errors="coerce") if columns[field] else None
    return result[HISTORY_COLUMNS].dropna(subset=["date", "close"])


def load_industry_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    frame = pd.read_csv(path, dtype={"code": str})
    if not {"code", "industry"}.issubset(frame.columns):
        return {}
    return {normalize_code(row.code): str(row.industry) for row in frame.itertuples() if str(row.industry).strip()}


def apply_industry_map(spot: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    result = spot.copy()
    if result.empty:
        return result
    result["industry"] = [
        _clean_text(industry) or _clean_text(mapping.get(code)) or "Unknown"
        for code, industry in zip(result["code"], result["industry"])
    ]
    return result


def listing_age_days(listing_date: str | None, market_date: str, history_days: int) -> int:
    if listing_date:
        try:
            return (date.fromisoformat(market_date) - date.fromisoformat(listing_date)).days
        except ValueError:
            pass
    return history_days


def _find_column(frame: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    lower = {str(column).lower(): str(column) for column in frame.columns}
    for alias in aliases:
        if alias in frame.columns:
            return str(alias)
        if alias.lower() in lower:
            return lower[alias.lower()]
    return None


def _value(row: pd.Series, column: str | None) -> float | None:
    return safe_number(row.get(column)) if column else None


def _normalize_quote_time(value: Any, quote_at: datetime) -> str:
    local = quote_at.astimezone(TIMEZONE)
    text = str(value or "").strip()
    if not text:
        return local.isoformat(timespec="seconds")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TIMEZONE)
        return parsed.astimezone(TIMEZONE).isoformat(timespec="seconds")
    except ValueError:
        pass
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed_time = datetime.strptime(text, fmt).time()
            return datetime.combine(local.date(), parsed_time, tzinfo=TIMEZONE).isoformat(timespec="seconds")
        except ValueError:
            continue
    return local.isoformat(timespec="seconds")


def _normalize_date(value: Any) -> str | None:
    text = "".join(char for char in str(value or "") if char.isdigit())
    if len(text) >= 8:
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return None


def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def bootstrap_date_range(moment: datetime, calendar_days: int = 150) -> tuple[str, str]:
    end = moment.astimezone(TIMEZONE).date()
    start = end - timedelta(days=calendar_days)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
