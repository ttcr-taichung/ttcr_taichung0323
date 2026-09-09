"""離線示範資料——不呼叫任何 API，僅用於在沒有 META_ACCESS_TOKEN 時預覽報告格式。
數值為示意用途，執行 `python -m meta_ads_automation.cli report --demo` 可產出範例報告。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import config
from .data_pipeline import default_period_start, weekday_label
from .models import AccountSnapshot, AdSnapshot, AdsetSnapshot, CampaignSnapshot, MonthToDate, ReportData, TrendMonth


def build_demo_data(today: date = None) -> ReportData:
    today = today or date.today()
    period_start = default_period_start(today)

    account = AccountSnapshot(
        id=config.AD_ACCOUNT_FULL_ID, name=config.ACCOUNT_DISPLAY_NAME,
        account_status=1, disable_reason=0, amount_spent=4880, balance=0,
        currency="TWD", spend_cap=None, funding_source_ok=True, raw={},
    )
    campaign = CampaignSnapshot(
        id=config.CAMPAIGN_ID, name=config.CAMPAIGN_NAME, status="ACTIVE",
        effective_status="ACTIVE", daily_budget=500, lifetime_budget=None,
        created_time="2026-06-16T00:00:00+0800",
    )

    ad_0901 = AdSnapshot(
        ad_id="demo_0901", name="0901_收納", effective_status="ACTIVE",
        adset_id="demo_adset_1", created_time="2026-09-01T00:00:00+0800",
        weeks_running=1, spend=2400, impressions=42000, reach=21000, clicks=580,
        ctr=1.38, cpm=57.1, cpc=4.14, frequency=1.6,
        messaging_conversions=9, cost_per_messaging_conversion=258,
        quality_rank_raw="ABOVE_AVERAGE", engagement_rank_raw="AVERAGE",
        conversion_rank_raw="ABOVE_AVERAGE", quality_rank="高於平均",
        engagement_rank="平均", conversion_rank="高於平均",
        ctr_2wk_ago=1.42, ctr_change_pct=-2.8,
        consecutive_low_conversion_rank=0, cpr_above_p50_30pct_streak_days=0,
    )
    ad_0814 = AdSnapshot(
        ad_id="demo_0814", name="0814_風格圖", effective_status="ACTIVE",
        adset_id="demo_adset_1", created_time="2026-07-17T00:00:00+0800",
        weeks_running=8, spend=2480, impressions=38500, reach=15200, clicks=410,
        ctr=1.06, cpm=64.4, cpc=6.05, frequency=2.6,
        messaging_conversions=6, cost_per_messaging_conversion=413,
        quality_rank_raw="BELOW_AVERAGE_20", engagement_rank_raw="BELOW_AVERAGE_10",
        conversion_rank_raw="BELOW_AVERAGE_35", quality_rank="低於平均",
        engagement_rank="低於平均", conversion_rank="低於平均",
        ctr_2wk_ago=1.45, ctr_change_pct=-26.9,
        consecutive_low_conversion_rank=2, cpr_above_p50_30pct_streak_days=6,
    )

    month_to_date = MonthToDate(spend=4880, messages=18, cpr=271,
                                 month_label=f"{today.month}月(至{today.month}/{today.day})")
    three_month_trend = [
        TrendMonth(label="7月", spend=20689, messages=91, cpr=227,
                   note=config.MONTHLY_HISTORY["7月"]["note"]),
        TrendMonth(label="8月", spend=13781, messages=51, cpr=270,
                   note=config.MONTHLY_HISTORY["8月"]["note"]),
        TrendMonth(label="9月(至9/8)", spend=4880, messages=18, cpr=271,
                   note=config.MONTHLY_HISTORY["9月(至9/8)"]["note"]),
    ]

    adsets = [AdsetSnapshot(id="demo_adset_1", name="廣泛受眾_不設興趣", effective_status="ACTIVE",
                             daily_budget=500, has_interest_targeting=False)]

    return ReportData(
        generated_at=datetime.utcnow(), period_start=period_start, period_end=today,
        trigger_weekday=weekday_label(today),
        account=account, campaign=campaign, ads=[ad_0901, ad_0814], adsets=adsets,
        month_to_date=month_to_date, three_month_trend=three_month_trend,
        weekly_conversions_7d=9, weekly_conversions_30d_avg=15.5,
        active_ads_count=2, paused_ads_count=0,
        cpr_benchmark={**config.CPR_BENCHMARK_FALLBACK, "source": "fallback"},
        current_campaign_agg={"spend": 2400, "impressions": 42000, "clicks": 580, "ctr": 1.38,
                               "cpm": 57.1, "messaging_conversions": 9, "cvr": 1.55, "cpr": 267},
        previous_campaign_agg={"spend": 2200, "impressions": 39000, "clicks": 610, "ctr": 1.56,
                                "cpm": 56.4, "messaging_conversions": 10, "cvr": 1.64, "cpr": 220},
    )
