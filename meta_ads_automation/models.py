"""共用資料結構（純資料容器，不含 API 呼叫或寫入邏輯）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@dataclass
class AccountSnapshot:
    id: str
    name: str
    account_status: Any
    disable_reason: Any
    amount_spent: float
    balance: float
    currency: str
    spend_cap: Optional[float]
    funding_source_ok: bool
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CampaignSnapshot:
    id: str
    name: str
    status: str
    effective_status: str
    daily_budget: Optional[float]
    lifetime_budget: Optional[float]
    created_time: Optional[str]


@dataclass
class AdSnapshot:
    ad_id: str
    name: str
    effective_status: str
    adset_id: Optional[str]
    created_time: Optional[str]

    weeks_running: Optional[int] = None

    spend: float = 0.0
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    ctr: float = 0.0
    cpm: float = 0.0
    cpc: float = 0.0
    frequency: float = 0.0

    messaging_conversions: int = 0
    cost_per_messaging_conversion: Optional[float] = None  # 即 CPR

    quality_rank_raw: Optional[str] = None
    engagement_rank_raw: Optional[str] = None
    conversion_rank_raw: Optional[str] = None
    quality_rank: str = "資料不足"
    engagement_rank: str = "資料不足"
    conversion_rank: str = "資料不足"

    ctr_2wk_ago: Optional[float] = None
    ctr_change_pct: Optional[float] = None

    consecutive_low_conversion_rank: int = 0
    cpr_above_p50_30pct_streak_days: int = 0

    status_anomaly: Optional[str] = None  # e.g. "0曝光但顯示ACTIVE"


@dataclass
class MonthToDate:
    spend: float
    messages: int
    cpr: Optional[float]
    month_label: str


@dataclass
class TrendMonth:
    label: str
    spend: float
    messages: int
    cpr: Optional[float]
    note: str = ""
    is_live: bool = True


@dataclass
class AdsetSnapshot:
    id: str
    name: str
    effective_status: str
    daily_budget: Optional[float]
    has_interest_targeting: bool


@dataclass
class ReportData:
    generated_at: datetime
    period_start: date
    period_end: date
    trigger_weekday: str  # "mon" | "fri"

    account: AccountSnapshot
    campaign: CampaignSnapshot
    ads: List[AdSnapshot]
    adsets: List[AdsetSnapshot] = field(default_factory=list)

    month_to_date: MonthToDate = None
    three_month_trend: List[TrendMonth] = field(default_factory=list)

    weekly_conversions_7d: int = 0
    weekly_conversions_30d_avg: float = 0.0

    active_ads_count: int = 0
    paused_ads_count: int = 0

    cpr_benchmark: Dict[str, Any] = field(default_factory=dict)  # {"p25":.., "p50":.., "p75":.., "source": "live"|"fallback"}
    current_campaign_agg: Dict[str, Any] = field(default_factory=dict)
    previous_campaign_agg: Dict[str, Any] = field(default_factory=dict)
