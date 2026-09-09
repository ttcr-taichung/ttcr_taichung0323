"""把 Meta API 的原始回應（唯讀）組裝成 ReportData。全檔僅呼叫 api_client 的 GET 方法，
不做任何寫入判斷或寫入呼叫。
"""
from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from . import config, metrics
from .api_client import MetaMarketingReadOnlyClient, extract_messaging_conversions, extract_cost_per_messaging_conversion
from .models import AccountSnapshot, AdSnapshot, AdsetSnapshot, CampaignSnapshot, MonthToDate, ReportData, TrendMonth
from .state_store import StateStore

ACTIVE_LIKE_STATUSES = {"ACTIVE"}
PAUSED_LIKE_STATUSES = {"PAUSED", "ADSET_PAUSED", "CAMPAIGN_PAUSED"}


def default_period_start(today: date) -> date:
    """未曾執行過時，依今天是週一或週五推算預設查詢區間起點。"""
    weekday = today.weekday()  # Mon=0 ... Sun=6
    if weekday == 0:  # 週一 -> 涵蓋上週五至今
        return today - timedelta(days=3)
    if weekday == 4:  # 週五 -> 涵蓋本週一至今
        return today - timedelta(days=4)
    return today - timedelta(days=7)  # 手動執行時的保守預設


def weekday_label(today: date) -> str:
    weekday = today.weekday()
    if weekday == 0:
        return "mon"
    if weekday == 4:
        return "fri"
    return "manual"


def next_review_date(today: date) -> date:
    weekday = today.weekday()
    if weekday in (0, 1, 2, 3):  # 週一~週四 -> 下次是本週五
        return today + timedelta(days=4 - weekday)
    return today + timedelta(days=(7 - weekday))  # 週五~週日 -> 下次是下週一


def _parse_meta_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
        return dt.replace(tzinfo=None)
    except ValueError:
        return None


def _classify_status_bucket(effective_status: str) -> str:
    if effective_status in ACTIVE_LIKE_STATUSES:
        return "active"
    if effective_status in PAUSED_LIKE_STATUSES:
        return "paused"
    return "other"  # PENDING_REVIEW, DISAPPROVED, WITH_ISSUES, IN_PROCESS...


def fetch_live_data(client: MetaMarketingReadOnlyClient, state: StateStore,
                     today: Optional[date] = None) -> ReportData:
    today = today or date.today()
    generated_at = datetime.utcnow()

    last_run = state.get_last_run()
    if last_run and last_run.get("period_end"):
        period_start = date.fromisoformat(last_run["period_end"])
    else:
        period_start = default_period_start(today)
    period_end = today
    trigger_weekday = weekday_label(today)

    # ---------------- 帳號 / 活動 ----------------
    account_raw = client.get_account_status()
    account = AccountSnapshot(
        id=account_raw.get("id", config.AD_ACCOUNT_FULL_ID),
        name=account_raw.get("name", config.ACCOUNT_DISPLAY_NAME),
        account_status=account_raw.get("account_status"),
        disable_reason=account_raw.get("disable_reason"),
        amount_spent=metrics.safe_float(account_raw.get("amount_spent")),
        balance=metrics.safe_float(account_raw.get("balance")),
        currency=account_raw.get("currency", "TWD"),
        spend_cap=metrics.safe_float(account_raw.get("spend_cap")) or None,
        funding_source_ok=account_raw.get("account_status") == 1,
        raw=account_raw,
    )

    campaign_raw = client.get_campaign_info()
    campaign = CampaignSnapshot(
        id=campaign_raw.get("id", config.CAMPAIGN_ID),
        name=campaign_raw.get("name", config.CAMPAIGN_NAME),
        status=campaign_raw.get("status", "UNKNOWN"),
        effective_status=campaign_raw.get("effective_status", "UNKNOWN"),
        daily_budget=metrics.safe_float(campaign_raw.get("daily_budget")) or None,
        lifetime_budget=metrics.safe_float(campaign_raw.get("lifetime_budget")) or None,
        created_time=campaign_raw.get("created_time"),
    )

    # ---------------- 廣告組合（受眾設定） ----------------
    adsets_raw = client.get_adsets_in_campaign()
    adsets: List[AdsetSnapshot] = []
    for a in adsets_raw:
        targeting = a.get("targeting", {}) or {}
        has_interest = bool(targeting.get("flexible_spec") or targeting.get("interests"))
        adsets.append(AdsetSnapshot(
            id=a.get("id"), name=a.get("name", ""),
            effective_status=a.get("effective_status", "UNKNOWN"),
            daily_budget=metrics.safe_float(a.get("daily_budget")) or None,
            has_interest_targeting=has_interest,
        ))

    # ---------------- CPR 基準（優先用帳戶自身歷史 P25/P50/P75，不足90天資料則退回歷史基準表）
    cpr_benchmark = _compute_cpr_benchmark(client, today)

    # ---------------- 廣告清單 + 本期成效 ----------------
    ads_meta = client.get_ads_in_campaign()
    period_insights = client.get_insights(
        config.CAMPAIGN_ID, level="ad",
        since=period_start.isoformat(), until=period_end.isoformat(),
    )
    insights_by_ad: Dict[str, dict] = {row.get("ad_id"): row for row in period_insights if row.get("ad_id")}

    # 兩週前同長度區間，供 CTR 趨勢比較
    baseline_since = period_start - timedelta(days=14)
    baseline_until = period_end - timedelta(days=14)
    baseline_insights = client.get_insights(
        config.CAMPAIGN_ID, level="ad",
        since=baseline_since.isoformat(), until=baseline_until.isoformat(),
    )
    baseline_by_ad: Dict[str, dict] = {row.get("ad_id"): row for row in baseline_insights if row.get("ad_id")}

    ads: List[AdSnapshot] = []
    active_count = 0
    paused_count = 0

    for meta in ads_meta:
        ad_id = meta.get("id")
        effective_status = meta.get("effective_status", "UNKNOWN")
        bucket = _classify_status_bucket(effective_status)
        if bucket == "active":
            active_count += 1
        elif bucket == "paused":
            paused_count += 1

        created_dt = _parse_meta_time(meta.get("created_time"))
        weeks_running = None
        if created_dt:
            weeks_running = max((today - created_dt.date()).days // 7, 0)
            state.record_first_seen(ad_id, meta.get("created_time"))

        row = insights_by_ad.get(ad_id, {})
        actions = row.get("actions")
        cost_per_action = row.get("cost_per_action_type")

        ctr_now = metrics.safe_float(row.get("ctr"))
        baseline_row = baseline_by_ad.get(ad_id, {})
        ctr_2wk_ago = metrics.safe_float(baseline_row.get("ctr"), default=None) if baseline_row else None
        ctr_change_pct = metrics.pct_change(ctr_now, ctr_2wk_ago) if ctr_2wk_ago else None

        conversion_rank = metrics.classify_ranking(row.get("conversion_rate_ranking"))
        state.push_conversion_rank(ad_id, conversion_rank, generated_at.isoformat())
        consecutive_low = state.consecutive_low_rank_count(ad_id)

        cpr = extract_cost_per_messaging_conversion(cost_per_action)
        p50 = cpr_benchmark["p50"]
        is_above_30pct = cpr is not None and cpr > p50 * 1.3
        state.push_cpr_above_p50_flag(ad_id, today.isoformat(), is_above_30pct)
        streak_days = state.cpr_above_p50_streak_days(ad_id)

        state.push_ctr(ad_id, period_end.isoformat(), ctr_now)

        status_anomaly = None
        impressions = metrics.safe_int(row.get("impressions"))
        if effective_status == "ACTIVE" and impressions == 0:
            status_anomaly = "顯示 ACTIVE 但本期曝光為 0，需人工確認是否為矛盾狀態"
        elif effective_status in {"PENDING_REVIEW", "CAMPAIGN_PAUSED", "DISAPPROVED", "WITH_ISSUES"}:
            status_anomaly = f"狀態異常：{effective_status}"

        ads.append(AdSnapshot(
            ad_id=ad_id,
            name=meta.get("name", ad_id),
            effective_status=effective_status,
            adset_id=meta.get("adset_id"),
            created_time=meta.get("created_time"),
            weeks_running=weeks_running,
            spend=metrics.safe_float(row.get("spend")),
            impressions=impressions,
            reach=metrics.safe_int(row.get("reach")),
            clicks=metrics.safe_int(row.get("clicks")),
            ctr=ctr_now,
            cpm=metrics.safe_float(row.get("cpm")),
            cpc=metrics.safe_float(row.get("cpc")),
            frequency=metrics.safe_float(row.get("frequency")),
            messaging_conversions=extract_messaging_conversions(actions),
            cost_per_messaging_conversion=cpr,
            quality_rank_raw=row.get("quality_ranking"),
            engagement_rank_raw=row.get("engagement_rate_ranking"),
            conversion_rank_raw=row.get("conversion_rate_ranking"),
            quality_rank=metrics.classify_ranking(row.get("quality_ranking")),
            engagement_rank=metrics.classify_ranking(row.get("engagement_rate_ranking")),
            conversion_rank=conversion_rank,
            ctr_2wk_ago=ctr_2wk_ago,
            ctr_change_pct=ctr_change_pct,
            consecutive_low_conversion_rank=consecutive_low,
            cpr_above_p50_30pct_streak_days=streak_days,
            status_anomaly=status_anomaly,
        ))

    # ---------------- 當月累積 ----------------
    month_start = today.replace(day=1)
    mtd_insights = client.get_insights(
        config.CAMPAIGN_ID, level="campaign",
        since=month_start.isoformat(), until=today.isoformat(),
    )
    mtd_row = mtd_insights[0] if mtd_insights else {}
    mtd_spend = metrics.safe_float(mtd_row.get("spend"))
    mtd_messages = extract_messaging_conversions(mtd_row.get("actions"))
    month_to_date = MonthToDate(
        spend=mtd_spend,
        messages=mtd_messages,
        cpr=(mtd_spend / mtd_messages) if mtd_messages else None,
        month_label=f"{today.month}月(至{today.month}/{today.day})",
    )

    # ---------------- 近3個月趨勢 ----------------
    three_month_trend = _build_three_month_trend(client, today)

    # ---------------- 週轉換事件量（受眾資料充足判斷） ----------------
    last7 = client.get_insights(config.CAMPAIGN_ID, level="campaign", date_preset="last_7d")
    last7_row = last7[0] if last7 else {}
    weekly_conversions_7d = extract_messaging_conversions(last7_row.get("actions"))

    last30 = client.get_insights(config.CAMPAIGN_ID, level="campaign", date_preset="last_30d")
    last30_row = last30[0] if last30 else {}
    conversions_30d = extract_messaging_conversions(last30_row.get("actions"))
    weekly_conversions_30d_avg = round(conversions_30d / (30 / 7), 1)

    # ---------------- 成效診斷：本期 vs 上期 活動層級彙總 ----------------
    current_campaign_agg = _campaign_agg(client, period_start, period_end)
    span = (period_end - period_start).days or 7
    prev_start = period_start - timedelta(days=span)
    prev_end = period_start
    previous_campaign_agg = _campaign_agg(client, prev_start, prev_end)

    return ReportData(
        generated_at=generated_at,
        period_start=period_start,
        period_end=period_end,
        trigger_weekday=trigger_weekday,
        account=account,
        campaign=campaign,
        ads=ads,
        adsets=adsets,
        month_to_date=month_to_date,
        three_month_trend=three_month_trend,
        weekly_conversions_7d=weekly_conversions_7d,
        weekly_conversions_30d_avg=weekly_conversions_30d_avg,
        active_ads_count=active_count,
        paused_ads_count=paused_count,
        cpr_benchmark=cpr_benchmark,
        current_campaign_agg=current_campaign_agg,
        previous_campaign_agg=previous_campaign_agg,
    )


def _campaign_agg(client: MetaMarketingReadOnlyClient, since: date, until: date) -> dict:
    rows = client.get_insights(config.CAMPAIGN_ID, level="campaign",
                                since=since.isoformat(), until=until.isoformat())
    row = rows[0] if rows else {}
    spend = metrics.safe_float(row.get("spend"))
    clicks = metrics.safe_int(row.get("clicks"))
    messages = extract_messaging_conversions(row.get("actions"))
    return {
        "spend": spend,
        "impressions": metrics.safe_int(row.get("impressions")),
        "clicks": clicks,
        "ctr": metrics.safe_float(row.get("ctr")),
        "cpm": metrics.safe_float(row.get("cpm")),
        "messaging_conversions": messages,
        "cvr": round(messages / clicks * 100, 2) if clicks else None,
        "cpr": (spend / messages) if messages else None,
    }


def _compute_cpr_benchmark(client: MetaMarketingReadOnlyClient, today: date) -> dict:
    """優先以帳戶自身近90天週度 CPR 分布計算 P25/P50/P75；資料不足8週則退回歷史基準表。"""
    since = today - timedelta(days=90)
    rows = client.get_insights(
        config.CAMPAIGN_ID, level="campaign",
        since=since.isoformat(), until=today.isoformat(),
        time_increment="7",
    )
    weekly_cprs = []
    for row in rows:
        spend = metrics.safe_float(row.get("spend"))
        messages = extract_messaging_conversions(row.get("actions"))
        if messages:
            weekly_cprs.append(spend / messages)

    if len(weekly_cprs) >= 8:
        q = statistics.quantiles(weekly_cprs, n=4, method="inclusive")
        return {"p25": round(q[0], 0), "p50": round(q[1], 0), "p75": round(q[2], 0), "source": "live"}
    return {**config.CPR_BENCHMARK_FALLBACK, "source": "fallback"}


def _build_three_month_trend(client: MetaMarketingReadOnlyClient, today: date) -> List[TrendMonth]:
    since = (today.replace(day=1) - timedelta(days=62)).replace(day=1)
    rows = client.get_insights(
        config.CAMPAIGN_ID, level="campaign",
        since=since.isoformat(), until=today.isoformat(),
        time_increment="monthly",
    )
    trend: List[TrendMonth] = []
    for row in rows:
        date_start = row.get("date_start")
        month_num = int(date_start.split("-")[1]) if date_start else None
        label = f"{month_num}月" if month_num else (date_start or "")
        spend = metrics.safe_float(row.get("spend"))
        messages = extract_messaging_conversions(row.get("actions"))
        note = config.MONTHLY_HISTORY.get(label, {}).get("note", "")
        trend.append(TrendMonth(
            label=label, spend=spend, messages=messages,
            cpr=(spend / messages) if messages else None,
            note=note, is_live=True,
        ))
    return trend
