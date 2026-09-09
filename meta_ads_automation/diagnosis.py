"""七大面向分析引擎——純運算，輸入 ReportData，輸出結構化分析結果供 report_builder 排版。
不含任何 API 呼叫，也不含任何寫入判斷（寫入建議一律交給 pending_changes.py 產出待確認清單）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from . import config, metrics
from .fatigue import FatigueInput, FatigueResult, evaluate_fatigue
from .models import ReportData


# ---------------------------------------------------------------------------
# 1. 帳號健檢
# ---------------------------------------------------------------------------
@dataclass
class AccountHealth:
    ranking_rows: List[Dict[str, str]]
    below_average_ads: List[str]
    status_anomalies: List[str]
    billing_ok: bool
    billing_note: str


def analyze_account_health(report: ReportData) -> AccountHealth:
    ranking_rows = []
    below_average_ads = []
    status_anomalies = []

    for ad in report.ads:
        ranking_rows.append({
            "ad_name": ad.name,
            "quality": ad.quality_rank,
            "engagement": ad.engagement_rank,
            "conversion": ad.conversion_rank,
        })
        if "低於平均" in (ad.quality_rank, ad.engagement_rank, ad.conversion_rank):
            below_average_ads.append(ad.name)
        if ad.status_anomaly:
            status_anomalies.append(f"{ad.name}：{ad.status_anomaly}")

    account_status = report.account.account_status
    disable_reason = report.account.disable_reason
    billing_ok = (account_status == 1) and (not disable_reason or disable_reason == 0)
    if billing_ok:
        billing_note = "帳單/付款狀態正常"
    else:
        billing_note = (f"⚠️ 帳號狀態異常（account_status={account_status}, "
                         f"disable_reason={disable_reason}），此帳戶歷史上曾因付款問題導致整帳號0花費，需立即人工確認")

    return AccountHealth(ranking_rows, below_average_ads, status_anomalies, billing_ok, billing_note)


# ---------------------------------------------------------------------------
# 2. 受眾建構
# ---------------------------------------------------------------------------
@dataclass
class AudienceBuilding:
    is_broad_audience: bool
    weekly_conversions_7d: int
    weekly_conversions_30d_avg: float
    data_sufficient: bool


def analyze_audience(report: ReportData) -> AudienceBuilding:
    is_broad = all(not a.has_interest_targeting for a in report.adsets) if report.adsets else True
    threshold = config.WEEKLY_CONVERSION_SUFFICIENT_THRESHOLD
    data_sufficient = (report.weekly_conversions_7d >= threshold) or (report.weekly_conversions_30d_avg >= threshold)
    return AudienceBuilding(is_broad, report.weekly_conversions_7d, report.weekly_conversions_30d_avg, data_sufficient)


# ---------------------------------------------------------------------------
# 3. 漏斗結構
# ---------------------------------------------------------------------------
@dataclass
class FunnelStructure:
    mtd_spend: float
    monthly_budget: float
    achievement_rate_pct: float
    is_overspend: bool
    min_daily_budget_floor: float
    current_daily_budget: Optional[float]
    supportable_ad_groups: Optional[float]
    active_ads_count: int
    exceeds_simple_structure: bool


def analyze_funnel(report: ReportData) -> FunnelStructure:
    mtd_spend = report.month_to_date.spend
    budget = config.MONTHLY_BUDGET_TWD
    achievement_rate = round(mtd_spend / budget * 100, 1) if budget else 0.0
    cpa = report.cpr_benchmark.get("p50", config.CPR_BENCHMARK_FALLBACK["p50"])
    floor = config.min_daily_budget_floor(cpa)
    daily_budget = report.campaign.daily_budget
    supportable = round(daily_budget / floor, 2) if daily_budget and floor else None

    return FunnelStructure(
        mtd_spend=mtd_spend, monthly_budget=budget, achievement_rate_pct=achievement_rate,
        is_overspend=mtd_spend > budget, min_daily_budget_floor=floor,
        current_daily_budget=daily_budget, supportable_ad_groups=supportable,
        active_ads_count=report.active_ads_count,
        exceeds_simple_structure=report.active_ads_count > config.MAX_ADS_PER_CAMPAIGN,
    )


# ---------------------------------------------------------------------------
# 4. 素材策略（含燈號）
# ---------------------------------------------------------------------------
def evaluate_all_fatigue(report: ReportData) -> List[FatigueResult]:
    results = []
    p50 = report.cpr_benchmark.get("p50", config.CPR_BENCHMARK_FALLBACK["p50"])
    for ad in report.ads:
        if ad.effective_status != "ACTIVE":
            continue
        inp = FatigueInput(
            ad_name=ad.name,
            weeks_running=ad.weeks_running,
            frequency=ad.frequency,
            conversion_rank=ad.conversion_rank,
            ctr_change_pct_vs_2wk_ago=ad.ctr_change_pct,
            consecutive_low_rank_count=ad.consecutive_low_conversion_rank,
            cpr=ad.cost_per_messaging_conversion,
            cpr_p50_benchmark=p50,
            cpr_above_p50_30pct_streak_days=ad.cpr_above_p50_30pct_streak_days,
        )
        results.append(evaluate_fatigue(inp))
    return results


@dataclass
class CreativeStrategy:
    ad_rows: List[Dict[str, Any]]
    fatigue_results: List[FatigueResult]


def analyze_creative_strategy(report: ReportData) -> CreativeStrategy:
    ad_rows = []
    for ad in report.ads:
        if ad.effective_status != "ACTIVE":
            continue
        ad_rows.append({
            "ad_name": ad.name,
            "ctr": ad.ctr,
            "cpm": ad.cpm,
            "frequency": ad.frequency,
            "cpr": ad.cost_per_messaging_conversion,
        })
    fatigue_results = evaluate_all_fatigue(report)
    return CreativeStrategy(ad_rows, fatigue_results)


# ---------------------------------------------------------------------------
# 5. 檔期規劃
# ---------------------------------------------------------------------------
@dataclass
class SeasonalPlanning:
    in_prompt_window: bool
    in_prewarm_or_peak: bool
    days_to_prewarm_start: int
    prewarm_start_date: date
    message: str


def analyze_seasonal(report: ReportData, today: Optional[date] = None) -> SeasonalPlanning:
    today = today or report.period_end
    cfg = config.SEASONAL_CAMPAIGN
    year = today.year
    prewarm_start = date(year, cfg["prewarm_start_month"], cfg["prewarm_start_day"])
    if prewarm_start < today - timedelta(days=60):
        prewarm_start = date(year + 1, cfg["prewarm_start_month"], cfg["prewarm_start_day"])

    days_to_prewarm = (prewarm_start - today).days
    d_low, d_high = cfg["prompt_window_days"]
    in_prompt_window = d_low <= days_to_prewarm <= d_high if days_to_prewarm >= 0 else False
    in_peak = (today.month == cfg["prewarm_start_month"] and today.day >= cfg["prewarm_start_day"]) or \
              (cfg["peak_start_month"] <= today.month <= cfg["peak_end_month"])

    if in_peak:
        message = f"目前已進入「{cfg['name']}」預熱/蓄水期，應確保檔期素材與文案已到位"
    elif in_prompt_window:
        message = (f"距離「{cfg['name']}」預熱期起點（{prewarm_start.isoformat()}）僅剩 {days_to_prewarm} 天，"
                   f"落在 D-{d_high} 至 D-{d_low} 提醒窗口內，建議開始準備檔期素材與文案")
    else:
        message = f"距離「{cfg['name']}」預熱期起點（{prewarm_start.isoformat()}）尚有 {days_to_prewarm} 天，暫不需啟動檔期準備"

    return SeasonalPlanning(in_prompt_window, in_peak, days_to_prewarm, prewarm_start, message)


# ---------------------------------------------------------------------------
# 6. 成效診斷（電商黃金公式定位）
# ---------------------------------------------------------------------------
STAGE_LABELS = {
    "cpm": "曝光取得(CPM)",
    "ctr": "點擊(CTR)",
    "cvr": "轉換(CVR)",
    "cpr": "客單/整體效率(CPR)",
}

REFERRAL_SKILL_BY_STAGE = {
    "cpm": "meta-funnel-budget",
    "ctr": "meta-creative-strategy",
    "cvr": "meta-trust-assets",
    "cpr": "meta-performance-diagnosis",
}


@dataclass
class DiagnosisResult:
    stage_table: List[Dict[str, Any]]
    worst_stage: Optional[str]
    worst_stage_change_pct: Optional[float]
    root_cause: str
    prescription: Dict[str, str]
    referral_skill: Optional[str]
    benchmark_source: str


def analyze_diagnosis(report: ReportData, fatigue_results: List[FatigueResult]) -> DiagnosisResult:
    cur = report.current_campaign_agg or {}
    prev = report.previous_campaign_agg or {}

    stage_table = []
    changes: Dict[str, Optional[float]] = {}
    for key in ("cpm", "ctr", "cvr", "cpr"):
        cur_v = cur.get(key)
        prev_v = prev.get(key)
        change = metrics.pct_change(cur_v, prev_v)
        changes[key] = change
        stage_table.append({
            "key": key,
            "stage": STAGE_LABELS[key],
            "current": cur_v,
            "previous": prev_v,
            "change_pct": change,
        })

    # CPM/CTR/CVR 惡化方向：CPM上升、CTR下降、CVR下降、CPR上升 都是變差
    def severity(key: str, change: Optional[float]) -> float:
        if change is None:
            return -1
        if key in ("ctr", "cvr"):
            return -change  # 下降(負值)轉正，越大越嚴重
        return change  # cpm, cpr：上升越大越嚴重

    ranked = sorted(changes.items(), key=lambda kv: severity(kv[0], kv[1]), reverse=True)
    worst_key, worst_change = ranked[0] if ranked else (None, None)
    worst_stage = STAGE_LABELS.get(worst_key) if worst_key and worst_change is not None and severity(worst_key, worst_change) > 0 else None

    # 找出病因最具體的廣告：在 worst 面向上退步最多的廣告
    root_cause = "本期各面向數據皆與上期相近，尚未觀察到明顯卡點"
    if worst_key == "ctr":
        worst_ad = min(
            (a for a in report.ads if a.effective_status == "ACTIVE" and a.ctr_change_pct is not None),
            key=lambda a: a.ctr_change_pct, default=None,
        )
        if worst_ad:
            root_cause = f"{worst_ad.name} 的 CTR 較兩週前衰退 {abs(worst_ad.ctr_change_pct):.1f}%，是本期 CTR 卡點主因"
    elif worst_key in ("cpm", "cpr"):
        worst_ad = max(
            (a for a in report.ads if a.effective_status == "ACTIVE" and a.cost_per_messaging_conversion),
            key=lambda a: a.cost_per_messaging_conversion, default=None,
        )
        if worst_ad:
            p50 = report.cpr_benchmark.get("p50", config.CPR_BENCHMARK_FALLBACK["p50"])
            diff_pct = (worst_ad.cost_per_messaging_conversion / p50 - 1) * 100 if p50 else 0
            root_cause = (f"{worst_ad.name} 的 CPR NT${worst_ad.cost_per_messaging_conversion:.0f} "
                          f"較 P50 基準 NT${p50:.0f} 高出 {diff_pct:.0f}%")
    elif worst_key == "cvr":
        root_cause = f"整體活動 CVR 較上期衰退 {abs(worst_change):.1f}%，卡在點擊後未能完成私訊開啟"

    # 處方箋：優先看是否有紅/橘燈素材，其次看漏斗卡點；一次只建議改一項
    prescription = _build_prescription(fatigue_results, worst_key, root_cause)
    referral_skill = REFERRAL_SKILL_BY_STAGE.get(worst_key) if worst_key else None

    return DiagnosisResult(
        stage_table=stage_table, worst_stage=worst_stage, worst_stage_change_pct=worst_change,
        root_cause=root_cause, prescription=prescription, referral_skill=referral_skill,
        benchmark_source=report.cpr_benchmark.get("source", "fallback"),
    )


def _build_prescription(fatigue_results: List[FatigueResult], worst_key: Optional[str], root_cause: str) -> Dict[str, str]:
    red = [f for f in fatigue_results if f.light == "🔴"]
    orange = [f for f in fatigue_results if f.light == "🟠"]

    if red:
        return {
            "priority": "1",
            "action": f"正式更換素材：將預算從「{red[0].ad_name}」轉移到已測試過的新素材",
            "expected_impact": "預期 CPR 回落至 P50 基準附近，轉換率排名脫離「低於平均」",
            "risk": "新素材若未經小額測試驗證，可能出現學習期波動",
            "observation_period": "7天",
        }
    if orange:
        return {
            "priority": "1",
            "action": f"啟動新素材小額並行測試（不關閉「{orange[0].ad_name}」）",
            "expected_impact": "驗證新素材效率，為後續正式換素材預作準備",
            "risk": "小額測試期間數據量少，需至少累積3-7天再下判斷",
            "observation_period": "3-7天",
        }
    if worst_key:
        return {
            "priority": "1",
            "action": f"針對「{root_cause}」進行一項調整（例如優化該面向對應素材或文案）",
            "expected_impact": "改善本期最主要的卡點面向",
            "risk": "調整後需觀察至少3-7天趨勢，避免用單日數字下判斷",
            "observation_period": "3-7天",
        }
    return {
        "priority": "-",
        "action": "維持現狀，無需調整",
        "expected_impact": "-",
        "risk": "-",
        "observation_period": "-",
    }


# ---------------------------------------------------------------------------
# 7. 目前投放總覽
# ---------------------------------------------------------------------------
@dataclass
class CurrentOverview:
    rows: List[Dict[str, Any]]
    active_ads_count: int
    paused_ads_count: int


def analyze_overview(report: ReportData) -> CurrentOverview:
    rows = []
    for ad in report.ads:
        if ad.effective_status in ("ACTIVE", "PENDING_REVIEW", "IN_PROCESS", "WITH_ISSUES"):
            rows.append({
                "ad_name": ad.name,
                "status": ad.effective_status,
                "spend": ad.spend,
                "reach": ad.reach,
                "frequency": ad.frequency,
                "cpr": ad.cost_per_messaging_conversion,
            })
    return CurrentOverview(rows, report.active_ads_count, report.paused_ads_count)


# ---------------------------------------------------------------------------
# 彙總
# ---------------------------------------------------------------------------
@dataclass
class FullAnalysis:
    account_health: AccountHealth
    audience: AudienceBuilding
    funnel: FunnelStructure
    creative: CreativeStrategy
    seasonal: SeasonalPlanning
    diagnosis: DiagnosisResult
    overview: CurrentOverview


def run_full_analysis(report: ReportData, today: Optional[date] = None) -> FullAnalysis:
    account_health = analyze_account_health(report)
    audience = analyze_audience(report)
    funnel = analyze_funnel(report)
    creative = analyze_creative_strategy(report)
    seasonal = analyze_seasonal(report, today)
    diagnosis = analyze_diagnosis(report, creative.fatigue_results)
    overview = analyze_overview(report)
    return FullAnalysis(account_health, audience, funnel, creative, seasonal, diagnosis, overview)
