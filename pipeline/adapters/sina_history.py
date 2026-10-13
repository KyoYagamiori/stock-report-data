"""Unadjusted history with request deadlines and no unnecessary qfq requests."""
from __future__ import annotations

import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


class SinaHistory:
    def _bars(self, symbol: str, scale: int, count: int) -> pd.DataFrame:
        query = urlencode({"symbol": symbol, "scale": scale, "ma": "no", "datalen": count})
        request = Request(
            "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/CN_MarketDataService.getKLineData?" + query,
            headers={"Referer": "https://finance.sina.com.cn"},
        )
        with urlopen(request, timeout=20) as response:
            text = response.read().decode("utf-8")
        match = re.search(r"\(\s*(\[.*\])\s*\)", text, re.S)
        if not match:
            raise ValueError("Sina history did not contain a bar array")
        frame = pd.DataFrame(json.loads(match.group(1)))
        if frame.empty:
            raise ValueError("Sina history was empty")
        frame.attrs["source"] = "新浪一分钟历史时点恢复" if scale == 1 else "新浪未复权完成日线"
        return frame

    def stock_zh_a_minute(self, symbol: str, period: str, adjust: str) -> pd.DataFrame:
        if period != "1" or adjust:
            raise ValueError("Recovery requires unadjusted one-minute history")
        return self._bars(symbol, 1, 1970)

    def stock_zh_a_daily(self, symbol: str, start_date: str, end_date: str, adjust: str) -> pd.DataFrame:
        if adjust:
            raise ValueError("Recovery requires unadjusted daily history")
        frame = self._bars(symbol, 240, 161).rename(columns={"day": "date"})
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        return frame[(frame["date"] >= pd.Timestamp(start_date)) &
                     (frame["date"] <= pd.Timestamp(end_date))].copy()

    def stock_zh_a_minute_fallback(self, symbol: str) -> pd.DataFrame:
        # Eastmoney documents volume in lots. Convert once to shares, retaining
        # the amount in CNY. No synthetic rows or later quotes are introduced.
        market = "1" if symbol.startswith("sh") else "0"
        query = urlencode({"secid": market + "." + symbol[2:],
                           "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
                           "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                           "ndays": 5, "iscr": 0, "iscca": 0})
        with urlopen("https://push2his.eastmoney.com/api/qt/stock/trends2/get?" + query, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        data = payload.get("data") or {}
        if str(data.get("code", "")) != symbol[2:]:
            raise ValueError("Eastmoney minute response has the wrong security code")
        rows = [item.split(",") for item in data.get("trends", [])]
        if not rows or any(len(row) != 8 for row in rows):
            raise ValueError("Eastmoney minute response has no valid eight-field rows")
        frame = pd.DataFrame(rows, columns=["day", "open", "close", "high", "low", "volume", "amount", "average"])
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce") * 100
        frame.attrs["source"] = "东方财富一分钟历史时点恢复（成交量手转股，成交额元）"
        return frame
