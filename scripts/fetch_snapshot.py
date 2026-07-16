from __future__ import annotations

import json
import math
import os
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from apply_watchlist_updates import WATCHLIST_COLUMNS, apply_updates, normalize_code, read_csv


TIMEZONE = ZoneInfo("Asia/Shanghai")
ROOT = Path(os.environ.get("STOCK_DATA_ROOT", Path(__file__).resolve().parents[1]))
FORCE_SINA_DAILY_FALLBACK = os.environ.get("STOCK_FORCE_SINA_DAILY_FALLBACK", "").lower() in {"1", "true", "yes"}
BOX_LOOKBACK_DAYS = 20
MA_WINDOWS = (5, 10, 20, 60)
HIST_LOOKBACK_ROWS = max(BOX_LOOKBACK_DAYS, max(MA_WINDOWS))
HIST_LOOKBACK_CALENDAR_DAYS = 180

try:
    import akshare as ak
except Exception as exc:  # pragma: no cover - exercised only when dependency is missing
    ak = None
    AKSHARE_IMPORT_ERROR = exc
else:
    AKSHARE_IMPORT_ERROR = None


def now() -> datetime:
    return datetime.now(TIMEZONE)


def safe_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def fmt(value: Any, unit: str = "") -> str:
    number = safe_number(value)
    if number is None:
        text = str(value).strip() if value not in (None, "") else "暂无"
        return text
    if abs(number) >= 100_000_000:
        text = f"{number / 100_000_000:.2f}亿"
    elif abs(number) >= 10_000:
        text = f"{number / 10_000:.2f}万"
    else:
        text = f"{number:.2f}"
    return f"{text}{unit}"


def fmt_pct(value: Any) -> str:
    number = safe_number(value)
    return "暂无" if number is None else f"{number:.2f}%"


def limit_pool_text(record: dict[str, Any], value: Any, unit: str = "") -> str:
    if not record.get("is_limit_up_pool"):
        return "未进入涨停池，不适用"
    return fmt(value, unit)


def limit_pool_time_text(record: dict[str, Any], value: Any) -> str:
    if not record.get("is_limit_up_pool"):
        return "未进入涨停池，不适用"
    return value or "暂无"


def snapshot_usage_status(generated_at: datetime) -> dict[str, Any]:
    minute_of_day = generated_at.hour * 60 + generated_at.minute
    if minute_of_day < 9 * 60:
        label = "早报前快照"
        best_for = "09:00 早报盘前基线"
        limitation = "优先读取实时/准实时口径；开盘前若实时接口仍返回上一交易日收盘状态，只能作为盘前基线。"
    elif minute_of_day < 12 * 60 + 30:
        label = "午报前快照"
        best_for = "11:45 午报上午盘核验"
        limitation = "优先读取实时/准实时口径；若实时口径不可用，回落到日线或已存快照并明确标注。"
    elif minute_of_day < 16 * 60:
        label = "收盘后快照"
        best_for = "晚报收盘核验"
        limitation = "优先读取实时/准实时口径，通常可用于收盘量价核验；仍需联网核验新闻、公告和盘后事件。"
    elif minute_of_day < 21 * 60 + 30:
        label = "晚报前快照"
        best_for = "21:30 晚报收盘与盘后核验"
        limitation = "优先读取实时/准实时口径，作为晚报量价核验主口径；若字段缺失，必须明确标注不可核验。"
    else:
        label = "晚间补充快照"
        best_for = "晚报补充和下一交易日早报基线"
        limitation = "若逐股最新交易日为当天且实时/准实时行情时间在15:00后，可用于当日晚报补充核验；下一交易日开盘前只能作为上一交易日基线，不代表下一交易日实时行情。"

    return {
        "label": label,
        "best_for": best_for,
        "generated_date": generated_at.strftime("%Y-%m-%d"),
        "generated_time": generated_at.strftime("%H:%M"),
        "data_priority": "实时/准实时行情优先；日线数据次之；上一份已存快照最后兜底。",
        "limitation": limitation,
        "rules": [
            "先校验快照生成时间、快照类型、适合报告和生成日期，再读取逐股实时/准实时字段。",
            "逐股字段读取顺序：行情主口径、实时/准实时行情可用、实时/准实时数据来源、实时/准实时行情时间、最新交易日/推定日期、最新价、涨跌幅、成交量、成交额、换手率、涨停池、封板资金、炸板次数，最后才看日线备份和已存快照备份。",
            "实时/准实时行情可用=是，只说明本快照生成时使用了实时接口；若快照生成时间或类型不适合当前报告时点，不得把它当作当前实时数据。",
            "早报可把上一交易日实时/收盘口径作为盘前基线；午报必须校验当天11:30后快照或逐股行情时间；晚报必须校验当天15:00后逐股行情时间或收盘后/晚报前快照。",
            "快照不满足当前时点时，报告必须写结构化快照未通过实时性校验，并改用联网实时行情兜底或降低盘面确认分。",
            "公开快照只用于结构化行情核验，不替代联网新闻、公告、政策和产业动态搜索。",
        ],
    }


def format_em_time(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    if ":" in text:
        return text
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) <= 6:
        digits = digits.zfill(6)
        return f"{digits[0:2]}:{digits[2:4]}:{digits[4:6]}"
    return text


def summarize_exception(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    if "ProxyError" in message:
        return "接口连接失败：本机代理断开或外部接口暂不可达（ProxyError）。"
    if "SSLError" in message:
        return "接口连接失败：SSL 连接异常，可能是网络或接口临时问题。"
    if "Read timed out" in message or "ConnectTimeout" in message:
        return "接口连接失败：请求超时，可能是网络或接口临时问题。"
    if "Max retries exceeded with url:" in message:
        return "接口连接失败：外部行情接口暂不可达。"
    return message[:500]


def limit_pct_for(code: str, name: str) -> float:
    upper_name = name.upper()
    if "ST" in upper_name:
        return 5.0
    if code.startswith(("300", "301", "688")):
        return 20.0
    if code.startswith(("4", "8", "9")):
        return 30.0
    return 10.0


def volume_strength(change_ratio: float | None) -> str:
    if change_ratio is None:
        return "暂无可核验数据"
    if change_ratio >= 0:
        return "未缩量"
    shrink = abs(change_ratio)
    if shrink <= 0.10:
        return "轻微缩量"
    if shrink <= 0.30:
        return "正常缩量"
    if shrink <= 0.50:
        return "明显缩量"
    return "极强缩量"


def box_position_label(position_pct: float | None) -> str:
    if position_pct is None:
        return "暂无可核验位置"
    if position_pct >= 100:
        return "箱体上沿上方/突破区"
    if position_pct >= 80:
        return "接近箱体上沿"
    if position_pct <= 0:
        return "箱体下沿下方/破位区"
    if position_pct <= 20:
        return "接近箱体下沿"
    return "箱体中部"


def empty_box_metrics() -> dict[str, Any]:
    return {
        "box_lookback_days": 0,
        "box_data_source": "",
        "box_start_date": "",
        "box_end_date": "",
        "box_upper": None,
        "box_lower": None,
        "box_mid": None,
        "box_position_pct": None,
        "box_position": "暂无可核验位置",
        "box_breakout_watch_price": None,
        "box_pullback_watch_price": None,
    }


def compute_box_metrics(hist: pd.DataFrame, current_price: float | None, source: str) -> dict[str, Any]:
    if hist.empty or "最高" not in hist.columns or "最低" not in hist.columns:
        return empty_box_metrics()
    recent = hist.copy()
    recent["最高"] = pd.to_numeric(recent["最高"], errors="coerce")
    recent["最低"] = pd.to_numeric(recent["最低"], errors="coerce")
    recent = recent.dropna(subset=["最高", "最低" ]).tail(BOX_LOOKBACK_DAYS)
    if recent.empty:
        return empty_box_metrics()
    upper = safe_number(recent["最高"].max())
    lower = safe_number(recent["最低"].min())
    if upper is None or lower is None:
        return empty_box_metrics()
    mid = (upper + lower) / 2
    position_pct = None
    if current_price is not None and upper > lower:
        position_pct = ((current_price - lower) / (upper - lower)) * 100
    return {
        "box_lookback_days": int(len(recent)),
        "box_data_source": source,
        "box_start_date": recent.iloc[0]["日期"].strftime("%Y-%m-%d"),
        "box_end_date": recent.iloc[-1]["日期"].strftime("%Y-%m-%d"),
        "box_upper": upper,
        "box_lower": lower,
        "box_mid": mid,
        "box_position_pct": position_pct,
        "box_position": box_position_label(position_pct),
        "box_breakout_watch_price": upper,
        "box_pullback_watch_price": lower,
    }


def saved_box_metrics(saved_record: dict[str, Any]) -> dict[str, Any]:
    if not saved_record:
        return empty_box_metrics()
    return {
        "box_lookback_days": int(safe_number(saved_record.get("box_lookback_days")) or 0),
        "box_data_source": str(saved_record.get("box_data_source", "")),
        "box_start_date": str(saved_record.get("box_start_date", "")),
        "box_end_date": str(saved_record.get("box_end_date", "")),
        "box_upper": safe_number(saved_record.get("box_upper")),
        "box_lower": safe_number(saved_record.get("box_lower")),
        "box_mid": safe_number(saved_record.get("box_mid")),
        "box_position_pct": safe_number(saved_record.get("box_position_pct")),
        "box_position": str(saved_record.get("box_position", "暂无可核验位置")),
        "box_breakout_watch_price": safe_number(saved_record.get("box_breakout_watch_price")),
        "box_pullback_watch_price": safe_number(saved_record.get("box_pullback_watch_price")),
    }


def ma_position(price: float | None, ma_value: float | None) -> str:
    if price is None or ma_value is None:
        return "unknown"
    if price > ma_value:
        return "above"
    if price < ma_value:
        return "below"
    return "at"


def empty_ma_metrics() -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "ma_data_source": "",
        "ma_alignment": "unknown",
        "ma_trend_signal": "unknown",
    }
    for window in MA_WINDOWS:
        metrics[f"ma{window}"] = None
        metrics[f"price_vs_ma{window}_pct"] = None
        metrics[f"price_vs_ma{window}_position"] = "unknown"
    return metrics


def compute_ma_metrics(hist: pd.DataFrame, current_price: float | None, source: str) -> dict[str, Any]:
    metrics = empty_ma_metrics()
    if hist.empty or "收盘" not in hist.columns:
        return metrics

    closes = pd.to_numeric(hist["收盘"], errors="coerce").dropna()
    if closes.empty:
        return metrics

    metrics["ma_data_source"] = source
    for window in MA_WINDOWS:
        if len(closes) < window:
            continue
        ma_value = safe_number(closes.tail(window).mean())
        metrics[f"ma{window}"] = ma_value
        if current_price is not None and ma_value not in (None, 0):
            metrics[f"price_vs_ma{window}_pct"] = ((current_price - ma_value) / ma_value) * 100
        metrics[f"price_vs_ma{window}_position"] = ma_position(current_price, ma_value)

    ma5 = metrics.get("ma5")
    ma10 = metrics.get("ma10")
    ma20 = metrics.get("ma20")
    ma60 = metrics.get("ma60")
    if all(value is not None for value in [ma5, ma10, ma20, ma60]):
        if ma5 > ma10 > ma20 > ma60:
            metrics["ma_alignment"] = "bullish_alignment"
        elif ma5 < ma10 < ma20 < ma60:
            metrics["ma_alignment"] = "bearish_alignment"
        else:
            metrics["ma_alignment"] = "mixed_or_converging"
    elif all(value is not None for value in [ma5, ma10, ma20]):
        if ma5 > ma10 > ma20:
            metrics["ma_alignment"] = "short_term_bullish_alignment"
        elif ma5 < ma10 < ma20:
            metrics["ma_alignment"] = "short_term_bearish_alignment"
        else:
            metrics["ma_alignment"] = "short_term_mixed"

    if current_price is not None and ma20 is not None:
        if ma5 is not None and ma10 is not None and current_price > ma5 > ma10 > ma20:
            metrics["ma_trend_signal"] = "price_above_ma5_ma10_ma20_short_term_strong"
        elif current_price > ma20:
            metrics["ma_trend_signal"] = "price_above_ma20_trend_repair"
        elif current_price < ma20:
            metrics["ma_trend_signal"] = "price_below_ma20_trend_pressure"
        else:
            metrics["ma_trend_signal"] = "price_at_ma20"

    return metrics


def saved_ma_metrics(saved_record: dict[str, Any]) -> dict[str, Any]:
    if not saved_record:
        return empty_ma_metrics()
    metrics = empty_ma_metrics()
    metrics["ma_data_source"] = str(saved_record.get("ma_data_source", ""))
    metrics["ma_alignment"] = str(saved_record.get("ma_alignment", "unknown"))
    metrics["ma_trend_signal"] = str(saved_record.get("ma_trend_signal", "unknown"))
    for window in MA_WINDOWS:
        metrics[f"ma{window}"] = safe_number(saved_record.get(f"ma{window}"))
        metrics[f"price_vs_ma{window}_pct"] = safe_number(saved_record.get(f"price_vs_ma{window}_pct"))
        metrics[f"price_vs_ma{window}_position"] = str(saved_record.get(f"price_vs_ma{window}_position", "unknown"))
    return metrics


def fetch_limit_up_pool(date_yyyymmdd: str) -> tuple[pd.DataFrame, str | None]:
    if ak is None:
        return pd.DataFrame(), f"AKShare 导入失败：{AKSHARE_IMPORT_ERROR}"
    try:
        df = ak.stock_zt_pool_em(date=date_yyyymmdd)
        if df is None:
            return pd.DataFrame(), "涨停股池接口返回空。"
        df = df.copy()
        if "代码" in df.columns:
            df["代码"] = df["代码"].map(normalize_code)
        return df, None
    except Exception as exc:
        return pd.DataFrame(), f"涨停股池获取失败：{summarize_exception(exc)}"


def fetch_industry(code: str) -> tuple[str, str | None]:
    if ak is None:
        return "", f"AKShare 导入失败：{AKSHARE_IMPORT_ERROR}"
    try:
        df = ak.stock_individual_info_em(symbol=code)
        if df is None or df.empty:
            return "", "个股信息接口返回空。"
        info = dict(zip(df["item"], df["value"]))
        return str(info.get("行业", "")).strip(), None
    except Exception as exc:
        return "", f"行业信息获取失败：{summarize_exception(exc)}"


def sina_symbol(code: str) -> str:
    if code.startswith(("6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def normalize_em_hist(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized["日期"] = pd.to_datetime(normalized["日期"])
    normalized = normalized.sort_values("日期")
    return normalized.tail(HIST_LOOKBACK_ROWS)


def normalize_sina_daily(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    normalized["date"] = pd.to_datetime(normalized["date"])
    normalized = normalized.sort_values("date")
    normalized["previous_close"] = normalized["close"].shift(1)
    normalized["涨跌幅"] = ((normalized["close"] - normalized["previous_close"]) / normalized["previous_close"]) * 100
    output = pd.DataFrame(
        {
            "日期": normalized["date"],
            "收盘": normalized["close"],
            "最高": normalized["high"],
            "最低": normalized["low"],
            "涨跌幅": normalized["涨跌幅"],
            "成交量": normalized["volume"] / 100,
            "成交额": normalized["amount"],
            "换手率": normalized["turnover"] * 100,
        }
    )
    return output.tail(HIST_LOOKBACK_ROWS)


def fetch_em_hist_rows(code: str, start: str, end: str) -> tuple[pd.DataFrame, str | None]:
    if FORCE_SINA_DAILY_FALLBACK:
        return pd.DataFrame(), "已按测试配置跳过东方财富主日线接口。"
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="")
        if df is None or df.empty:
            return pd.DataFrame(), "东方财富主日线接口返回空。"
        return normalize_em_hist(df), None
    except Exception as exc:
        return pd.DataFrame(), f"东方财富主日线接口失败：{summarize_exception(exc)}"


def fetch_sina_daily_rows(code: str, start: str, end: str) -> tuple[pd.DataFrame, str | None]:
    try:
        df = ak.stock_zh_a_daily(symbol=sina_symbol(code), start_date=start, end_date=end, adjust="")
        if df is None or df.empty:
            return pd.DataFrame(), "新浪备用日线接口返回空。"
        return normalize_sina_daily(df), None
    except Exception as exc:
        return pd.DataFrame(), f"新浪备用日线接口失败：{summarize_exception(exc)}"


def fetch_realtime_spot() -> tuple[pd.DataFrame, str, list[str]]:
    if ak is None:
        return pd.DataFrame(), "暂无可用实时接口", [f"AKShare 导入失败：{AKSHARE_IMPORT_ERROR}"]

    warnings: list[str] = []
    attempts = [
        ("新浪实时行情接口", ak.stock_zh_a_spot),
        ("东方财富实时行情接口", ak.stock_zh_a_spot_em),
    ]
    for source, fetcher in attempts:
        try:
            df = fetcher()
            if df is None or df.empty:
                warnings.append(f"{source}返回空。")
                continue
            df = df.copy()
            if "代码" not in df.columns:
                warnings.append(f"{source}缺少代码字段。")
                continue
            df["normalized_code"] = df["代码"].map(normalize_code)
            return df, source, warnings
        except Exception as exc:
            warnings.append(f"{source}获取失败：{summarize_exception(exc)}")

    return pd.DataFrame(), "暂无可用实时接口", warnings


def spot_record_for(spot_quotes: pd.DataFrame, code: str) -> dict[str, Any] | None:
    if spot_quotes.empty or "normalized_code" not in spot_quotes.columns:
        return None
    matches = spot_quotes[spot_quotes["normalized_code"] == code]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()


def record_number(record: dict[str, Any] | None, keys: list[str]) -> float | None:
    if not record:
        return None
    for key in keys:
        if key in record:
            number = safe_number(record.get(key))
            if number is not None:
                return number
    return None


def record_text(record: dict[str, Any] | None, keys: list[str]) -> str:
    if not record:
        return ""
    for key in keys:
        value = record.get(key)
        text = "" if value is None else str(value).strip()
        if text and text.lower() != "nan":
            return text
    return ""


def normalize_realtime_volume(value: Any, source: str) -> float | None:
    number = safe_number(value)
    if number is None:
        return None
    if "新浪" in source:
        return number / 100
    return number


def fetch_hist_rows(code: str, today: datetime) -> tuple[pd.DataFrame, str, list[str], list[str]]:
    if ak is None:
        return pd.DataFrame(), "暂无可用日线接口", [f"AKShare 导入失败：{AKSHARE_IMPORT_ERROR}"], []
    start = (today - timedelta(days=HIST_LOOKBACK_CALENDAR_DAYS)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")

    em_hist, em_error = fetch_em_hist_rows(code, start, end)
    if em_error is None:
        return em_hist, "东方财富主接口", [], []

    sina_hist, sina_error = fetch_sina_daily_rows(code, start, end)
    if sina_error is None:
        return sina_hist, "新浪备用日线接口", [], [f"{em_error} 已使用新浪备用日线接口。"]

    return pd.DataFrame(), "暂无可用日线接口", [f"日线行情获取失败：{em_error}; {sina_error}"], []


def load_saved_snapshot(root: Path) -> tuple[dict[str, dict[str, Any]], str]:
    candidates = [
        root / "output" / "latest" / "close" / "report_data_compact.json",
        root / "output" / "latest" / "evening" / "report_data_compact.json",
        root / "output" / "latest" / "noon" / "report_data_compact.json",
        root / "output" / "latest" / "early" / "report_data_compact.json",
        root / "output" / "latest" / "report_data.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        records = {
            normalize_code(record.get("code", "")): record
            for record in payload.get("stocks", [])
            if normalize_code(record.get("code", ""))
        }
        if records:
            return records, str(payload.get("published_at") or payload.get("generated_at", ""))
    return {}, ""


def zt_record_for(limit_pool: pd.DataFrame, code: str) -> dict[str, Any] | None:
    if limit_pool.empty or "代码" not in limit_pool.columns:
        return None
    matches = limit_pool[limit_pool["代码"] == code]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()


def build_stock_record(
    row: pd.Series,
    limit_pool: pd.DataFrame,
    today: datetime,
    spot_quotes: pd.DataFrame,
    realtime_data_source: str,
    saved_records: dict[str, dict[str, Any]],
    saved_snapshot_time: str,
    include_technicals: bool = True,
) -> dict[str, Any]:
    code = row["code"]
    name = row["name"]
    errors: list[str] = []
    data_warnings: list[str] = []
    if include_technicals:
        hist, daily_data_source, hist_errors, daily_warnings = fetch_hist_rows(code, today)
    else:
        hist = pd.DataFrame()
        daily_data_source = "最近有效完整快照技术基线"
        hist_errors = []
        daily_warnings = []
    errors.extend(hist_errors)
    data_warnings.extend(daily_warnings)

    zt = zt_record_for(limit_pool, code)
    industry = ""
    industry_error = None
    if not include_technicals:
        industry = row["theme"]
    elif zt and zt.get("所属行业"):
        industry = str(zt.get("所属行业", "")).strip()
    else:
        industry, industry_error = fetch_industry(code)
        if industry_error:
            industry = row["theme"]
            data_warnings.append(f"{industry_error} 已使用观察池 theme 作为行业/主题兜底。")

    latest: pd.Series | None = None
    previous: pd.Series | None = None
    if len(hist) >= 1:
        latest = hist.iloc[-1]
    if len(hist) >= 2:
        previous = hist.iloc[-2]
    elif not hist_errors:
        errors.append("最近 30 个自然日内不足两个交易日数据，无法计算较昨日变化。")

    daily_trade_date = latest["日期"].strftime("%Y-%m-%d") if latest is not None else ""
    daily_close = safe_number(latest.get("收盘") if latest is not None else None)
    daily_pct = safe_number(latest.get("涨跌幅") if latest is not None else None)
    daily_volume = safe_number(latest.get("成交量") if latest is not None else None)
    daily_amount = safe_number(latest.get("成交额") if latest is not None else None)
    daily_turnover = safe_number(latest.get("换手率") if latest is not None else None)

    spot = spot_record_for(spot_quotes, code)
    realtime_price = record_number(spot, ["最新价", "最新", "现价", "最新价格"])
    realtime_pct = record_number(spot, ["涨跌幅", "涨幅"])
    realtime_volume = normalize_realtime_volume(record_number(spot, ["成交量", "成交量(手)"]), realtime_data_source)
    realtime_amount = record_number(spot, ["成交额", "成交额(元)"])
    realtime_quote_time = record_text(spot, ["时间戳", "更新时间", "时间"])
    has_realtime_quote = any(value is not None for value in [realtime_price, realtime_pct, realtime_volume, realtime_amount])

    saved_record = saved_records.get(code, {})
    saved_used = False
    saved_source = ""

    primary_price = realtime_price if realtime_price is not None else daily_close
    primary_pct = realtime_pct if realtime_pct is not None else daily_pct
    primary_volume = realtime_volume if realtime_volume is not None else daily_volume
    primary_amount = realtime_amount if realtime_amount is not None else daily_amount
    primary_turnover = daily_turnover
    price_data_source = realtime_data_source if has_realtime_quote else daily_data_source

    if all(value is None for value in [primary_price, primary_pct, primary_volume, primary_amount]) and saved_record:
        saved_used = True
        saved_source = f"上一份已存快照 {saved_snapshot_time or '时间未知'}"
        price_data_source = saved_source
        primary_price = safe_number(saved_record.get("today_close"))
        primary_pct = safe_number(saved_record.get("today_pct_change"))
        primary_volume = safe_number(saved_record.get("today_volume"))
        primary_amount = safe_number(saved_record.get("today_amount"))
        primary_turnover = safe_number(saved_record.get("today_turnover_rate"))
        if saved_record.get("daily_data_source"):
            daily_data_source = str(saved_record.get("daily_data_source"))
        data_warnings.append(f"实时和日线口径均不可用，已回落到{saved_source}。")
    elif not has_realtime_quote:
        data_warnings.append(f"实时/准实时行情不可用，已回落到{daily_data_source}。")

    box_metrics = compute_box_metrics(hist, primary_price, daily_data_source)
    if box_metrics.get("box_upper") is None and saved_record:
        saved_box = saved_box_metrics(saved_record)
        if saved_box.get("box_upper") is not None:
            box_metrics = saved_box
            data_warnings.append("日线箱体字段不可用，已沿用上一份已存快照箱体数据。")
    if box_metrics.get("box_upper") is None and include_technicals:
        data_warnings.append("最近20个交易日高低点不足，箱体上沿/下沿暂不可核验。")

    ma_metrics = compute_ma_metrics(hist, primary_price, daily_data_source)
    if ma_metrics.get("ma5") is None and saved_record:
        saved_ma = saved_ma_metrics(saved_record)
        if saved_ma.get("ma5") is not None:
            ma_metrics = saved_ma
            data_warnings.append("日线均线字段不可用，已沿用上一份已存快照均线数据。")
    if ma_metrics.get("ma5") is None and include_technicals:
        data_warnings.append("日线数据不足，均线字段暂不可核验。")

    today_volume = primary_volume
    yesterday_volume = safe_number(previous.get("成交量") if previous is not None else None)
    volume_change_ratio = None
    if today_volume is not None and yesterday_volume not in (None, 0):
        volume_change_ratio = (today_volume - float(yesterday_volume)) / float(yesterday_volume)

    pct = primary_pct
    limit_pct = limit_pct_for(code, name)
    is_near_limit_up = pct is not None and pct >= limit_pct - 1.0
    is_near_limit_down = pct is not None and pct <= -(limit_pct - 1.0)
    is_volume_down = volume_change_ratio is not None and volume_change_ratio < 0
    is_volume_up = volume_change_ratio is not None and volume_change_ratio > 0
    is_limit_up_pool = zt is not None
    is_shrink_limit_up = bool(is_limit_up_pool and is_volume_down)
    is_volume_rise = bool(pct is not None and pct > 0 and volume_change_ratio is not None and volume_change_ratio >= 0.30)
    is_volume_fall = bool(pct is not None and pct < 0 and volume_change_ratio is not None and volume_change_ratio >= 0.30)
    is_shrink_rise = bool(pct is not None and pct > 0 and is_volume_down)
    is_shrink_pullback = bool(pct is not None and pct < 0 and is_volume_down)
    needs_focus = bool(
        row["priority"] == "high"
        or row["locked"] == "true"
        or is_limit_up_pool
        or is_shrink_limit_up
        or is_volume_rise
        or is_volume_fall
        or errors
    )

    minute_of_day = today.hour * 60 + today.minute
    realtime_trade_date = today.strftime("%Y-%m-%d") if has_realtime_quote and minute_of_day >= 9 * 60 else ""
    trading_date = realtime_trade_date or daily_trade_date or str(saved_record.get("latest_trade_date", ""))
    previous_date = previous["日期"].strftime("%Y-%m-%d") if previous is not None else ""
    warning = ""
    if daily_trade_date and daily_trade_date != today.strftime("%Y-%m-%d") and not has_realtime_quote:
        warning = f"日线最新交易日为 {daily_trade_date}，当前自然日可能非 A 股交易日或日线数据未更新。"

    auto_signals = []
    if is_shrink_limit_up:
        auto_signals.append(f"缩量涨停，缩量强度：{volume_strength(volume_change_ratio)}")
    if is_volume_rise:
        auto_signals.append("放量上涨")
    if is_volume_fall:
        auto_signals.append("放量下跌")
    if is_shrink_rise:
        auto_signals.append("缩量上涨")
    if is_shrink_pullback:
        auto_signals.append("缩量回调")
    if not auto_signals:
        auto_signals.append("暂无显著自动量价信号")

    prompt = "需要重点核验" if needs_focus else "常规观察"
    if errors:
        prompt = "数据缺失或接口异常，报告中必须标注不可核验字段"
    elif saved_used:
        prompt = "实时和日线口径均不可用，已使用上一份已存快照备份，报告中必须标注口径"
    elif daily_warnings:
        prompt = "已优先使用实时/准实时行情，日线备份存在接口提示，报告中需留意来源口径"
    elif is_shrink_limit_up:
        prompt = "重点核验缩量涨停、封板质量和相关新闻"
    elif is_volume_rise:
        prompt = "重点核验放量上涨是否由消息或板块主线驱动"
    elif is_volume_fall:
        prompt = "重点核验放量下跌原因和风险释放程度"

    return {
        "code": code,
        "name": name,
        "theme": row["theme"],
        "priority": row["priority"],
        "locked": row["locked"] == "true",
        "status": row["status"],
        "price_data_source": price_data_source,
        "realtime_quote_available": has_realtime_quote,
        "realtime_data_source": realtime_data_source if has_realtime_quote else "",
        "realtime_quote_time": realtime_quote_time,
        "realtime_quote_date": realtime_trade_date,
        "saved_snapshot_used": saved_used,
        "saved_snapshot_source": saved_source,
        "daily_data_source": daily_data_source,
        "daily_latest_trade_date": daily_trade_date,
        "latest_trade_date": trading_date,
        "today_close": primary_price,
        "today_pct_change": pct,
        "today_volume": today_volume,
        "previous_trade_date": previous_date,
        "previous_volume": yesterday_volume,
        "today_amount": primary_amount,
        "previous_amount": safe_number(previous.get("成交额") if previous is not None else None),
        "today_turnover_rate": primary_turnover,
        **box_metrics,
        **ma_metrics,
        "volume_change_ratio": volume_change_ratio,
        "is_volume_down_vs_previous": is_volume_down,
        "is_volume_up_vs_previous": is_volume_up,
        "volume_strength": volume_strength(volume_change_ratio),
        "is_near_limit_up": is_near_limit_up,
        "is_near_limit_down": is_near_limit_down,
        "is_limit_up_pool": is_limit_up_pool,
        "limit_up_seal_amount": safe_number(zt.get("封板资金") if zt else None),
        "first_limit_up_time": format_em_time(zt.get("首次封板时间") if zt else None),
        "last_limit_up_time": format_em_time(zt.get("最后封板时间") if zt else None),
        "break_limit_up_count": safe_number(zt.get("炸板次数") if zt else None),
        "limit_up_days": safe_number(zt.get("连板数") if zt else None),
        "industry": industry,
        "is_shrink_limit_up": is_shrink_limit_up,
        "is_volume_rise": is_volume_rise,
        "is_volume_fall": is_volume_fall,
        "is_shrink_rise": is_shrink_rise,
        "is_shrink_pullback": is_shrink_pullback,
        "needs_report_focus": needs_focus,
        "auto_signals": auto_signals,
        "report_prompt": prompt,
        "warnings": [*data_warnings, *([warning] if warning else [])],
        "errors": errors,
    }


def blank_error_record(row: pd.Series, errors: list[str]) -> dict[str, Any]:
    return {
        "code": row.get("code", ""),
        "name": row.get("name", ""),
        "theme": row.get("theme", ""),
        "priority": row.get("priority", ""),
        "locked": row.get("locked", "") == "true",
        "status": row.get("status", ""),
        "price_data_source": "暂无可用行情口径",
        "realtime_quote_available": False,
        "realtime_data_source": "",
        "realtime_quote_time": "",
        "realtime_quote_date": "",
        "saved_snapshot_used": False,
        "saved_snapshot_source": "",
        "daily_data_source": "暂无可用日线接口",
        "daily_latest_trade_date": "",
        "latest_trade_date": "",
        "today_close": None,
        "today_pct_change": None,
        "today_volume": None,
        "previous_trade_date": "",
        "previous_volume": None,
        "today_amount": None,
        "previous_amount": None,
        "today_turnover_rate": None,
        "box_lookback_days": 0,
        "box_data_source": "",
        "box_start_date": "",
        "box_end_date": "",
        "box_upper": None,
        "box_lower": None,
        "box_mid": None,
        "box_position_pct": None,
        "box_position": "暂无可核验位置",
        "box_breakout_watch_price": None,
        "box_pullback_watch_price": None,
        "ma_data_source": "",
        "ma5": None,
        "ma10": None,
        "ma20": None,
        "ma60": None,
        "price_vs_ma5_pct": None,
        "price_vs_ma10_pct": None,
        "price_vs_ma20_pct": None,
        "price_vs_ma60_pct": None,
        "price_vs_ma5_position": "unknown",
        "price_vs_ma10_position": "unknown",
        "price_vs_ma20_position": "unknown",
        "price_vs_ma60_position": "unknown",
        "ma_alignment": "unknown",
        "ma_trend_signal": "unknown",
        "volume_change_ratio": None,
        "is_volume_down_vs_previous": False,
        "is_volume_up_vs_previous": False,
        "volume_strength": "暂无可核验数据",
        "is_near_limit_up": False,
        "is_near_limit_down": False,
        "is_limit_up_pool": False,
        "limit_up_seal_amount": None,
        "first_limit_up_time": "",
        "last_limit_up_time": "",
        "break_limit_up_count": None,
        "limit_up_days": None,
        "industry": "",
        "is_shrink_limit_up": False,
        "is_volume_rise": False,
        "is_volume_fall": False,
        "is_shrink_rise": False,
        "is_shrink_pullback": False,
        "needs_report_focus": True,
        "auto_signals": ["结构化行情快照暂未取得该股票字段"],
        "report_prompt": "数据缺失或接口异常，报告中必须标注不可核验字段",
        "warnings": [],
        "errors": errors,
    }


def names(records: list[dict[str, Any]], predicate) -> list[str]:
    return [f'{record["name"]} {record["code"]}' for record in records if predicate(record)]


def build_summary(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "limit_up_pool": names(records, lambda record: record["is_limit_up_pool"]),
        "shrink_limit_up": names(records, lambda record: record["is_shrink_limit_up"]),
        "volume_rise": names(records, lambda record: record["is_volume_rise"]),
        "volume_fall": names(records, lambda record: record["is_volume_fall"]),
        "data_errors": [
            f'{record["name"]} {record["code"]}: {"; ".join(record["errors"])}'
            for record in records
            if record["errors"]
        ],
        "focus_next": names(records, lambda record: record["needs_report_focus"]),
    }


def bullet(items: list[str]) -> str:
    if not items:
        return "- 无"
    return "\n".join(f"- {item}" for item in items)


def render_markdown(payload: dict[str, Any]) -> str:
    watchlist = payload["watchlist_status"]
    summary = payload["summary"]
    records = payload["stocks"]
    warnings = payload["warnings"]

    parts = [
        "# 股票报告结构化行情快照",
        "",
        f"生成时间：{payload['generated_at']}",
        "数据用途：供 ChatGPT 股票早报、午报、晚报生产线读取，用于核验观察池股票的结构化行情数据；优先使用实时/准实时行情口径。",
        "数据源说明：A 股实时/准实时行情、日线、涨停股池和个股行业信息来自 AKShare 对公开行情数据接口的封装。",
        "风险说明：本快照只提供数据核验，不构成买卖建议；若字段缺失，报告生产线不得编造。",
        "",
        "## 快照适用状态",
        "",
        f"- 快照类型：{payload['snapshot_usage']['label']}",
        f"- 适合报告：{payload['snapshot_usage']['best_for']}",
        f"- 生成日期：{payload['snapshot_usage']['generated_date']}",
        f"- 生成时间：中国时间 {payload['snapshot_usage']['generated_time']}",
        f"- 行情口径优先级：{payload['snapshot_usage']['data_priority']}",
        f"- 使用限制：{payload['snapshot_usage']['limitation']}",
        "- 使用规则：",
        bullet(payload["snapshot_usage"]["rules"]),
        "",
    ]
    if warnings:
        parts.extend(["## 数据更新提示", "", bullet(warnings), ""])

    parts.extend(
        [
            "## 一、观察池状态",
            "",
            f"- 当前 active 股票数量：{watchlist['active_count']}",
            f"- 当前 locked 股票数量：{watchlist['locked_count']}",
            "- 本次新增股票：",
            bullet(watchlist["added"]),
            "- 本次降级股票：",
            bullet(watchlist["downgraded"]),
            "- 本次 inactive 股票：",
            bullet(watchlist["inactive"]),
            "- 本次被跳过的 locked 删除请求：",
            bullet(watchlist["skipped_locked_removals"]),
            "- 当前 high priority 股票：",
            bullet(watchlist["high_priority"]),
            "",
            "## 二、重点结论摘要",
            "",
            "- 今日进入涨停股池的观察股：",
            bullet(summary["limit_up_pool"]),
            "- 今日构成缩量涨停的观察股：",
            bullet(summary["shrink_limit_up"]),
            "- 今日明显放量上涨的观察股：",
            bullet(summary["volume_rise"]),
            "- 今日明显放量下跌的观察股：",
            bullet(summary["volume_fall"]),
            "- 今日数据缺失或接口异常的股票：",
            bullet(summary["data_errors"]),
            "- 明天/下一份报告需要重点核验的股票：",
            bullet(summary["focus_next"]),
            "",
            "## 三、逐只股票数据",
            "",
        ]
    )

    for record in records:
        ratio = record["volume_change_ratio"]
        ratio_text = "暂无" if ratio is None else f"{ratio * 100:.2f}%"
        box_position_pct = safe_number(record.get("box_position_pct"))
        box_position_pct_text = "N/A" if box_position_pct is None else f"{box_position_pct:.2f}%"
        ma5_text = fmt(record.get("ma5"))
        ma10_text = fmt(record.get("ma10"))
        ma20_text = fmt(record.get("ma20"))
        ma60_text = fmt(record.get("ma60"))
        price_vs_ma5 = safe_number(record.get("price_vs_ma5_pct"))
        price_vs_ma10 = safe_number(record.get("price_vs_ma10_pct"))
        price_vs_ma20 = safe_number(record.get("price_vs_ma20_pct"))
        price_vs_ma60 = safe_number(record.get("price_vs_ma60_pct"))
        price_vs_ma5_text = "N/A" if price_vs_ma5 is None else f"{price_vs_ma5:.2f}%"
        price_vs_ma10_text = "N/A" if price_vs_ma10 is None else f"{price_vs_ma10:.2f}%"
        price_vs_ma20_text = "N/A" if price_vs_ma20 is None else f"{price_vs_ma20:.2f}%"
        price_vs_ma60_text = "N/A" if price_vs_ma60 is None else f"{price_vs_ma60:.2f}%"
        parts.extend(
            [
                f"### {record['name']} {record['code']}",
                "",
        f"- 主题：{record['theme']}",
        f"- 优先级：{record['priority']}",
        f"- 是否锁定：{'是' if record['locked'] else '否'}",
        f"- 行情主口径：{record.get('price_data_source', '暂无')}",
        f"- 实时/准实时行情可用：{'是' if record.get('realtime_quote_available') else '否'}",
        f"- 实时/准实时数据来源：{record.get('realtime_data_source') or '暂无'}",
        f"- 实时/准实时行情时间：{record.get('realtime_quote_time') or '暂无'}",
        f"- 已存快照备份：{record.get('saved_snapshot_source') or '未使用'}",
        f"- 日线备份来源：{record['daily_data_source']}",
        f"- 日线最新交易日：{record.get('daily_latest_trade_date') or '暂无'}",
        f"- 最新交易日/推定日期：{record['latest_trade_date'] or '暂无'}",
                f"- 最新价/收盘价：{fmt(record['today_close'])}",
                f"- 最新涨跌幅：{fmt_pct(record['today_pct_change'])}",
                f"- 最新成交量：{fmt(record['today_volume'], '手')}",
                f"- 昨日交易日：{record['previous_trade_date'] or '暂无'}",
                f"- 昨日成交量：{fmt(record['previous_volume'], '手')}",
                f"- 较昨日缩量/放量比例：{ratio_text}（{record['volume_strength']}）",
                f"- 最新成交额：{fmt(record['today_amount'], '元')}",
                f"- 昨日成交额：{fmt(record['previous_amount'], '元')}",
                f"- 最新换手率：{fmt_pct(record['today_turnover_rate'])}",
                f"- box_data_source / box range: {record.get('box_data_source') or 'N/A'}; lookback={record.get('box_lookback_days') or 0} trading days ({record.get('box_start_date') or 'N/A'} to {record.get('box_end_date') or 'N/A'})",
                f"- box_upper / box top: {fmt(record.get('box_upper'))}",
                f"- box_lower / box bottom: {fmt(record.get('box_lower'))}",
                f"- box_mid: {fmt(record.get('box_mid'))}",
                f"- box_position: {box_position_pct_text} ({record.get('box_position') or 'N/A'})",
                f"- box_breakout_watch_price / breakout buy watch: {fmt(record.get('box_breakout_watch_price'))}",
                f"- box_pullback_watch_price / pullback buy watch: {fmt(record.get('box_pullback_watch_price'))}",
                f"- ma_data_source: {record.get('ma_data_source') or 'N/A'}",
                f"- ma5 / 5-day MA: {ma5_text}; price_vs_ma5: {price_vs_ma5_text} ({record.get('price_vs_ma5_position') or 'unknown'})",
                f"- ma10 / 10-day MA: {ma10_text}; price_vs_ma10: {price_vs_ma10_text} ({record.get('price_vs_ma10_position') or 'unknown'})",
                f"- ma20 / 20-day MA: {ma20_text}; price_vs_ma20: {price_vs_ma20_text} ({record.get('price_vs_ma20_position') or 'unknown'})",
                f"- ma60 / 60-day MA: {ma60_text}; price_vs_ma60: {price_vs_ma60_text} ({record.get('price_vs_ma60_position') or 'unknown'})",
                f"- ma_alignment: {record.get('ma_alignment') or 'unknown'}",
                f"- ma_trend_signal: {record.get('ma_trend_signal') or 'unknown'}",
                f"- 是否进入涨停股池：{'是' if record['is_limit_up_pool'] else '否'}",
                f"- 是否构成缩量涨停：{'是' if record['is_shrink_limit_up'] else '否'}",
                f"- 封板资金：{limit_pool_text(record, record['limit_up_seal_amount'], '元')}",
                f"- 首次封板时间：{limit_pool_time_text(record, record['first_limit_up_time'])}",
                f"- 最后封板时间：{limit_pool_time_text(record, record['last_limit_up_time'])}",
                f"- 炸板次数：{limit_pool_text(record, record['break_limit_up_count'])}",
                f"- 连板数：{limit_pool_text(record, record['limit_up_days'])}",
                f"- 所属行业：{record['industry'] or '暂无'}",
                f"- 自动量价判定：{'；'.join(record['auto_signals'])}",
                f"- 给报告生产线的提示：{record['report_prompt']}",
            ]
        )
        for warning in record["warnings"]:
            parts.append(f"- 数据更新提示：{warning}")
        for error in record["errors"]:
            parts.append(f"- 异常提示：{error}")
        parts.append("")

    parts.extend(
        [
            "## 四、给 ChatGPT 报告生产线的使用要求",
            "",
            "1. 先做当前报告时点有效性校验：快照生成时间、快照类型、适合报告、生成日期、逐股实时/准实时行情时间和最新交易日/推定日期必须与当前早报/午报/晚报时点匹配。",
            "2. 逐股字段读取顺序：行情主口径、实时/准实时行情可用、实时/准实时数据来源、实时/准实时行情时间、最新交易日/推定日期、最新价、成交量、成交额、涨跌幅、换手率、涨停池、封板资金、炸板次数、连板数、自动量价判定，最后才看日线备份和已存快照备份。",
            "3. 实时/准实时行情可用=是，只说明本快照生成时使用了实时接口；若快照生成时间或快照类型不适合当前报告时点，不得把它当作当前实时数据。",
            "4. 对“缩量涨停、放量突破、封板质量、主升浪候选”等判断，必须优先使用通过时点校验的实时/准实时字段；字段缺失时写明不可核验，不得编造。",
            "5. 若结构化快照未通过实时性校验，报告必须写“结构化快照未通过当前时点有效性校验”，并改用联网实时行情兜底；若兜底也失败，应降低盘面确认分或停止生成盘面结论。",
            "6. 本快照只提供数据核验，不构成买卖建议；报告仍然必须联网搜索新闻、公告、政策、产业动态，不能只看行情快照。",
            "",
        ]
    )
    return "\n".join(parts)


def write_outputs(payload: dict[str, Any], root: Path) -> None:
    latest = root / "output" / "latest"
    history = root / "output" / "history"
    latest.mkdir(parents=True, exist_ok=True)
    history.mkdir(parents=True, exist_ok=True)

    timestamp = now().strftime("%Y-%m-%d-%H%M")
    markdown = render_markdown(payload)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)

    (latest / "report_data.md").write_text(markdown, encoding="utf-8")
    (latest / "report_data.json").write_text(json_text, encoding="utf-8")
    (history / f"{timestamp}-report_data.md").write_text(markdown, encoding="utf-8")
    (history / f"{timestamp}-report_data.json").write_text(json_text, encoding="utf-8")


def collect_snapshot_payload(
    generated_at: datetime | None = None,
    root: Path = ROOT,
    active_codes: set[str] | None = None,
    mode: str = "full",
    spot_result: tuple[pd.DataFrame, str, list[str]] | None = None,
    apply_observation_updates: bool = True,
) -> dict[str, Any]:
    if mode not in {"light", "full"}:
        raise ValueError(f"Unsupported snapshot mode: {mode}")
    generated_at = generated_at or now()
    warnings: list[str] = []
    errors: list[str] = []

    saved_records, saved_snapshot_time = load_saved_snapshot(root)
    spot_quotes, realtime_data_source, realtime_warnings = spot_result or fetch_realtime_spot()
    warnings.extend(realtime_warnings)
    if spot_quotes.empty:
        warnings.append("实时/准实时行情不可用，本次将按日线数据、上一份已存快照顺序兜底。")

    watchlist = read_csv(root / "config" / "watchlist.csv", WATCHLIST_COLUMNS)
    if apply_observation_updates:
        watchlist_status = apply_updates(root)
        watchlist = read_csv(root / "config" / "watchlist.csv", WATCHLIST_COLUMNS)
    else:
        watchlist_status = static_watchlist_status(watchlist, generated_at)
    active = watchlist[watchlist["status"] == "active"].copy()
    if active_codes is not None:
        normalized_codes = {normalize_code(code) for code in active_codes}
        active = active[active["code"].isin(normalized_codes)].copy()
        available_codes = set(active["code"])
        missing_codes = sorted(normalized_codes - available_codes)
        if missing_codes:
            warnings.append(f"观察池配置缺少代码：{', '.join(missing_codes)}")

    if mode == "full":
        limit_pool, limit_pool_error = fetch_limit_up_pool(generated_at.strftime("%Y%m%d"))
        if limit_pool_error:
            warnings.append(limit_pool_error)
    else:
        limit_pool = pd.DataFrame()

    records: list[dict[str, Any]] = []
    for _, row in active.iterrows():
        try:
            records.append(
                build_stock_record(
                    row,
                    limit_pool,
                    generated_at,
                    spot_quotes,
                    realtime_data_source,
                    saved_records,
                    saved_snapshot_time,
                    include_technicals=mode == "full",
                )
            )
        except Exception as exc:
            error_text = f"{row.get('name', '')} {row.get('code', '')} 快照生成失败：{exc}"
            errors.append(error_text)
            records.append(blank_error_record(row, [error_text, traceback.format_exc(limit=3)]))

    for record in records:
        warnings.extend(record.get("warnings", []))

    payload = {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "snapshot_mode": mode,
        "data_usage": "供 ChatGPT 股票早报、午报、晚报生产线读取，用于核验结构化行情字段。",
        "snapshot_usage": snapshot_usage_status(generated_at),
        "data_sources": [
            "AKShare stock_zh_a_spot",
            "AKShare stock_zh_a_spot_em",
            "AKShare stock_zh_a_hist",
            "AKShare stock_zh_a_daily",
            "AKShare stock_zt_pool_em",
            "AKShare stock_individual_info_em",
        ],
        "risk_notice": "本快照只提供数据核验，不构成买卖建议。",
        "watchlist_status": watchlist_status,
        "summary": build_summary(records),
        "stocks": records,
        "warnings": list(dict.fromkeys(warnings)),
        "errors": errors,
    }

    return payload


def static_watchlist_status(watchlist: pd.DataFrame, generated_at: datetime) -> dict[str, Any]:
    active = watchlist[watchlist["status"] == "active"].copy()
    high = active[active["priority"] == "high"]
    locked = active[active["locked"].astype(str).str.lower() == "true"]
    return {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "active_count": int(len(active)),
        "locked_count": int(len(locked)),
        "high_priority": [f'{row["name"]} {row["code"]}'.strip() for _, row in high.iterrows()],
        "added": [],
        "upgraded": [],
        "downgraded": [],
        "inactive": [],
        "skipped_locked_removals": [],
        "actions": [],
    }


def main() -> None:
    payload = collect_snapshot_payload()

    write_outputs(payload, ROOT)
    print(
        f"Snapshot generated: stocks={len(payload['stocks'])}, "
        f"warnings={len(payload['warnings'])}, errors={len(payload['errors'])}"
    )


if __name__ == "__main__":
    main()
