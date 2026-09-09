"""待確認變更清單產生器。

安全鐵律（對應需求文件二、八）：
- 本檔案「絕對不」呼叫任何 Meta 寫入類端點（update/create/activate/pause）。
- 本檔案只負責「產出建議」，實際變更一律由使用者自行到 Meta Ads Manager 後台操作。
- 一次只列出並建議一項優先變更（若同時符合多項條件，仍全部列出但需人工逐一核准，
  不得將多項變更打包成單一批次動作）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from . import config
from .diagnosis import FullAnalysis
from .fatigue import ORANGE, RED


@dataclass
class PendingChange:
    priority: int
    scope: str          # 層級／對象，例如「廣告：0814_風格圖」
    action: str          # 建議動作
    expected_impact: str
    risk: str
    needs_manual_approval: bool = True  # 恆為 True——本系統不提供自動執行


def build_pending_changes(analysis: FullAnalysis) -> List[PendingChange]:
    changes: List[PendingChange] = []
    priority = 1

    for f in analysis.creative.fatigue_results:
        if f.light == RED:
            changes.append(PendingChange(
                priority=priority,
                scope=f"廣告：{f.ad_name}",
                action="正式更換素材，並將預算從此廣告轉移到已測試過的新素材（請至 Ads Manager 手動操作，一次僅調整此項）",
                expected_impact="轉換率排名有機會脫離「低於平均」，CPR 回落至 P50 基準附近",
                risk="更換素材／轉移預算會重啟該廣告學習期，短期內效率可能先降後升",
            ))
            priority += 1
        elif f.light == ORANGE:
            changes.append(PendingChange(
                priority=priority,
                scope=f"廣告：{f.ad_name}",
                action="啟動新素材小額並行測試（不要關閉此廣告，先不擴大預算）",
                expected_impact="提前驗證下一批素材成效，縮短未來正式換素材的空窗期",
                risk="小額測試樣本數少，需累積至少3-7天數據才能下判斷",
            ))
            priority += 1

    if analysis.account_health.status_anomalies:
        for note in analysis.account_health.status_anomalies:
            changes.append(PendingChange(
                priority=priority,
                scope="帳號健檢",
                action=f"人工確認並視需要至後台處理：{note}",
                expected_impact="排除無誤觸發或殘留干擾，避免預算浪費在異常狀態的廣告上",
                risk="若誤判正常審查中狀態為異常並貿然操作，可能中斷正常流程",
            ))
            priority += 1

    if not analysis.account_health.billing_ok:
        changes.append(PendingChange(
            priority=priority,
            scope="帳號健檢：帳單/付款",
            action="立即至 Meta 後台檢查付款方式與帳單狀態",
            expected_impact="避免因付款問題導致整帳號0花費",
            risk="無（純檢查動作），但延遲處理可能導致廣告全面停止",
        ))
        priority += 1

    if analysis.funnel.exceeds_simple_structure:
        changes.append(PendingChange(
            priority=priority,
            scope="漏斗結構：廣告組合",
            action=(f"目前啟用中廣告數為 {analysis.funnel.active_ads_count} 則，"
                    f"超過建議上限（1活動、最多{config.MAX_ADS_PER_CAMPAIGN}則廣告），建議精簡並集中預算"),
            expected_impact="避免 CBO 機制下的資源互搶，集中預算養出穩定素材",
            risk="暫停多餘廣告前，需先確認哪一則承接了主要轉換量",
        ))
        priority += 1

    return changes
