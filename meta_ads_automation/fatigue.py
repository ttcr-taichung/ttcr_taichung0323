"""五、素材更換判斷與提前預警——燈號邏輯。

依文件優先序由重到輕檢查：紅 → 橘 → 黃 → 綠。符合任一項條件即亮對應燈號。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import config

GREEN, YELLOW, ORANGE, RED = "🟢", "🟡", "🟠", "🔴"

ACTIONS = {
    GREEN: "維持現狀，不用動作",
    YELLOW: "本週起應開始準備下一批素材，預計2-3週內會進入疲乏期（目前素材仍可繼續投放）",
    ORANGE: "建議立即啟動新素材小額測試（與現有素材並行，不要直接關掉舊的），驗證新素材前先不擴大預算",
    RED: "建議正式更換素材，把預算從舊素材轉移到已測試過的新素材",
}


@dataclass
class FatigueInput:
    ad_name: str
    weeks_running: Optional[int]
    frequency: float
    conversion_rank: str  # "高於平均" / "平均" / "低於平均" / "資料不足"
    ctr_change_pct_vs_2wk_ago: Optional[float]  # 負數代表衰退
    consecutive_low_rank_count: int  # 含本次
    cpr: Optional[float]
    cpr_p50_benchmark: float
    cpr_above_p50_30pct_streak_days: int


@dataclass
class FatigueResult:
    ad_name: str
    weeks_running: Optional[int]
    frequency: float
    conversion_rank: str
    light: str
    action: str
    reasons: list


def evaluate_fatigue(inp: FatigueInput) -> FatigueResult:
    reasons = []
    weeks = inp.weeks_running if inp.weeks_running is not None else 0

    cpr_threshold = inp.cpr_p50_benchmark * 1.3
    cpr_over_30pct = inp.cpr is not None and inp.cpr > cpr_threshold

    # 🔴 紅燈：轉換率排名連續2次「低於平均」，或 CPR 高於 P50 基準30%以上且維持5天以上
    if inp.consecutive_low_rank_count >= 2:
        reasons.append(f"轉換率排名連續 {inp.consecutive_low_rank_count} 次回報皆為「低於平均」")
        return FatigueResult(inp.ad_name, inp.weeks_running, inp.frequency, inp.conversion_rank,
                              RED, ACTIONS[RED], reasons)
    if cpr_over_30pct and inp.cpr_above_p50_30pct_streak_days >= 5:
        reasons.append(
            f"CPR NT${inp.cpr:.0f} 較 P50 基準 NT${inp.cpr_p50_benchmark:.0f} 高出 "
            f"{(inp.cpr / inp.cpr_p50_benchmark - 1) * 100:.0f}%，已維持 "
            f"{inp.cpr_above_p50_30pct_streak_days} 天"
        )
        return FatigueResult(inp.ad_name, inp.weeks_running, inp.frequency, inp.conversion_rank,
                              RED, ACTIONS[RED], reasons)

    # 🟠 橘燈：Frequency > 2.5，或 CTR 較兩週前衰退 > 20%
    if inp.frequency > config.COLD_AUDIENCE_FREQUENCY_WARNING_RANGE[1]:
        reasons.append(f"Frequency {inp.frequency:.2f} 已超過 2.5")
        return FatigueResult(inp.ad_name, inp.weeks_running, inp.frequency, inp.conversion_rank,
                              ORANGE, ACTIONS[ORANGE], reasons)
    if inp.ctr_change_pct_vs_2wk_ago is not None and inp.ctr_change_pct_vs_2wk_ago <= -20:
        reasons.append(f"CTR 較兩週前衰退 {abs(inp.ctr_change_pct_vs_2wk_ago):.1f}%")
        return FatigueResult(inp.ad_name, inp.weeks_running, inp.frequency, inp.conversion_rank,
                              ORANGE, ACTIONS[ORANGE], reasons)

    # 🟡 黃燈：投放已滿6週，或 Frequency 落在 2.0-2.5 區間
    low, high = config.COLD_AUDIENCE_FREQUENCY_WARNING_RANGE
    if weeks >= config.FATIGUE_PREP_START_WEEK:
        reasons.append(f"投放已滿 {weeks} 週（達 {config.FATIGUE_PREP_START_WEEK} 週門檻）")
        return FatigueResult(inp.ad_name, inp.weeks_running, inp.frequency, inp.conversion_rank,
                              YELLOW, ACTIONS[YELLOW], reasons)
    if low <= inp.frequency <= high:
        reasons.append(f"Frequency {inp.frequency:.2f} 落在 {low}-{high} 警戒區間")
        return FatigueResult(inp.ad_name, inp.weeks_running, inp.frequency, inp.conversion_rank,
                              YELLOW, ACTIONS[YELLOW], reasons)

    # 🟢 綠燈：其餘情況（投放 < 6週、Frequency < 2.0、轉換率排名非低於平均）
    reasons.append("投放未滿6週、Frequency < 2.0，且轉換率排名非「低於平均」")
    return FatigueResult(inp.ad_name, inp.weeks_running, inp.frequency, inp.conversion_rank,
                          GREEN, ACTIONS[GREEN], reasons)
