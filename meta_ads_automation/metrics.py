"""共用的數值換算與排名分類工具（純函式，不含任何 API 呼叫）。"""
from __future__ import annotations

from typing import Optional


def classify_ranking(raw_value: Optional[str]) -> str:
    """把 Meta 原生的 quality_ranking / engagement_rate_ranking / conversion_rate_ranking
    字串（如 ABOVE_AVERAGE, AVERAGE, BELOW_AVERAGE_35, UNKNOWN）轉成中文分類。
    """
    if not raw_value or raw_value == "UNKNOWN":
        return "資料不足"
    v = raw_value.upper()
    if v.startswith("ABOVE_AVERAGE"):
        return "高於平均"
    if v == "AVERAGE":
        return "平均"
    if v.startswith("BELOW_AVERAGE"):
        return "低於平均"
    return "資料不足"


def pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """回傳 current 相較 previous 的變化百分比（例如 -20 代表衰退 20%）。"""
    if current is None or previous in (None, 0):
        return None
    return round((current - previous) / previous * 100, 1)


def safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def format_money(value: float) -> str:
    return f"NT${value:,.0f}"


def format_pct(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"
