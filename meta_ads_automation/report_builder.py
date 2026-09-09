"""將 FullAnalysis + PendingChange 清單，排版成需求文件「七、輸出報告固定格式（範本）」
所規定的 Markdown 報告。本檔案純粹做文字排版，不含任何資料運算或 API 呼叫。
"""
from __future__ import annotations

from datetime import date
from typing import List

from . import config, metrics
from .data_pipeline import next_review_date
from .diagnosis import FullAnalysis
from .fatigue import GREEN, ORANGE, RED, YELLOW
from .models import ReportData
from .pending_changes import PendingChange

_LIGHT_SEVERITY = {RED: 3, ORANGE: 2, YELLOW: 1, GREEN: 0}


def _one_line_conclusion(analysis: FullAnalysis) -> str:
    fatigue_results = analysis.creative.fatigue_results
    if fatigue_results:
        worst = max(fatigue_results, key=lambda f: _LIGHT_SEVERITY.get(f.light, -1))
        if worst.light == RED:
            return f"⚠️ 「{worst.ad_name}」已達紅燈，建議本週內完成正式換素材並轉移預算。"
        if worst.light == ORANGE:
            return f"🟠 「{worst.ad_name}」進入橘燈，建議立即啟動新素材小額並行測試。"
        if worst.light == YELLOW:
            return f"🟡 「{worst.ad_name}」已達黃燈，本週起應開始準備下一批素材候選。"

    if analysis.diagnosis.worst_stage:
        return (f"整體燈號健康，但「{analysis.diagnosis.worst_stage}」較上期衰退 "
                f"{abs(analysis.diagnosis.worst_stage_change_pct):.1f}%，本期建議優先處理此卡點。")
    return "整體投放表現穩定，維持現狀即可，持續監控。"


def _fatigue_table(analysis: FullAnalysis) -> str:
    header = "| 廣告 | 投放週數 | Frequency | 轉換率排名 | 燈號 | 建議動作 |\n|---|---|---|---|---|---|"
    rows = []
    for f in analysis.creative.fatigue_results:
        week_label = f"第{f.weeks_running + 1}週" if f.weeks_running is not None else "資料不足"
        rows.append(f"| {f.ad_name} | {week_label} | {f.frequency:.2f} | {f.conversion_rank} | {f.light} | {f.action} |")
    if not rows:
        rows.append("| 目前無啟用中廣告 | - | - | - | - | - |")
    return "\n".join([header, *rows])


def _section1(analysis: FullAnalysis) -> str:
    ah = analysis.account_health
    lines = ["| 廣告 | 品質排名 | 互動率排名 | 轉換率排名 |", "|---|---|---|---|"]
    for row in ah.ranking_rows:
        lines.append(f"| {row['ad_name']} | {row['quality']} | {row['engagement']} | {row['conversion']} |")
    lines.append("")
    lines.append("**排名低於平均的廣告：** " + ("、".join(ah.below_average_ads) if ah.below_average_ads else "無"))
    lines.append("**狀態異常：** " + ("；".join(ah.status_anomalies) if ah.status_anomalies else "無"))
    lines.append(f"**帳單/付款狀態：** {ah.billing_note}")
    return "\n".join(lines)


def _section2(analysis: FullAnalysis) -> str:
    a = analysis.audience
    lines = [
        f"**受眾策略：** 目前{'仍維持' if a.is_broad_audience else '未維持'}「廣泛受眾、不設興趣標籤」"
        f"（此為已驗證的正確策略，非必要不建議變更）",
        f"**近7天轉換事件數：** {a.weekly_conversions_7d} 次｜**近30天週均：** {a.weekly_conversions_30d_avg} 次/週",
        f"**資料充足判斷：** {'已達' if a.data_sufficient else '尚未達'} "
        f"{config.WEEKLY_CONVERSION_SUFFICIENT_THRESHOLD} 次/週的「資料充足」門檻",
        "**開新受眾測試：** 本次報告未收到擴大受眾測試之請求，暫不產出新受眾清單；"
        "如需測試，請明確提出，將套用「受眾偵察五問」邏輯產出可建清單，但不會主動建立。",
    ]
    return "\n".join(lines)


def _section3(analysis: FullAnalysis) -> str:
    f = analysis.funnel
    lines = [
        f"**當月累積花費：** {metrics.format_money(f.mtd_spend)}｜**月預算：** {metrics.format_money(f.monthly_budget)}"
        f"｜**達成率：** {f.achievement_rate_pct}%" + ("（⚠️ 已超支）" if f.is_overspend else ""),
        f"**單組廣告日預算下限：** {metrics.format_money(f.min_daily_budget_floor)}"
        f"（＝ allowed CPA × 50 ÷ 7）",
        f"**目前活動日預算：** {metrics.format_money(f.current_daily_budget) if f.current_daily_budget else 'N/A'}"
        + (f"｜**帳戶規模可支撐約：** {f.supportable_ad_groups} 組廣告" if f.supportable_ad_groups else ""),
        f"**結構提醒：** 應維持「1活動、最多{config.MAX_ADS_PER_CAMPAIGN}則廣告」的極簡結構，除非預算規模改變。"
        + (f" ⚠️ 目前啟用中廣告數為 {f.active_ads_count} 則，已超出建議上限。" if f.exceeds_simple_structure else
           f" 目前啟用中廣告數為 {f.active_ads_count} 則，符合建議上限。"),
    ]
    return "\n".join(lines)


def _section4(analysis: FullAnalysis) -> str:
    rows = ["| 廣告 | CTR | CPM | Frequency | CPR |", "|---|---|---|---|---|"]
    for r in analysis.creative.ad_rows:
        cpr_str = metrics.format_money(r["cpr"]) if r["cpr"] else "N/A"
        rows.append(f"| {r['ad_name']} | {r['ctr']:.2f}% | {metrics.format_money(r['cpm'])} | "
                    f"{r['frequency']:.2f} | {cpr_str} |")
    if len(rows) == 2:
        rows.append("| 目前無啟用中廣告 | - | - | - | - |")

    cycle_low, cycle_high = config.FATIGUE_CYCLE_WEEKS_RANGE
    note = (f"**疲乏判斷邏輯：** 同批素材 Frequency > 2.0-2.5 且 CTR 週衰退 > 20%，"
            f"或轉換率排名連續兩次落在「低於平均」，即判定進入疲乏期。\n"
            f"**歷史規律：** 本活動素材疲乏週期約為 {cycle_low}-{cycle_high} 週，"
            f"建議投放滿 {config.FATIGUE_PREP_START_WEEK} 週即開始準備下一批素材，不要等排名掉到低於平均才行動。\n"
            f"詳細燈號請見報告最上方「🚦素材燈號提醒」。")
    return "\n".join(rows) + "\n\n" + note


def _section5(analysis: FullAnalysis) -> str:
    return analysis.seasonal.message


def _section6(analysis: FullAnalysis) -> str:
    d = analysis.diagnosis
    lines = ["**階段定位表：**", "| 階段 | 本期 | 上期 | 變化 |", "|---|---|---|---|"]

    def _fmt_stage_value(key: str, value):
        if value is None:
            return "N/A"
        if key in ("ctr", "cvr"):
            return f"{value:.2f}%"
        if key in ("cpm", "cpr"):
            return metrics.format_money(value)
        return str(value)

    for row in d.stage_table:
        lines.append(
            f"| {row['stage']} | {_fmt_stage_value(row['key'], row['current'])} | "
            f"{_fmt_stage_value(row['key'], row['previous'])} | {metrics.format_pct(row['change_pct'])} |"
        )
    benchmark_note = ("採用帳戶自身近90天週度數據計算之 P25/P50/P75" if d.benchmark_source == "live"
                       else "累積數據不足90天，暫代使用文件「歷史基準表」")
    lines.append("")
    lines.append(f"**基準來源：** {benchmark_note}")
    lines.append(f"**排查結果：** " + (f"本期主要卡在「{d.worst_stage}」" if d.worst_stage else "本期各面向皆與上期相近，無明顯卡點"))
    lines.append(f"**病因：** {d.root_cause}")
    lines.append("")
    lines.append("**處方箋：**")
    lines.append("| 優先序 | 動作 | 預期影響 | 風險 | 觀察期 |")
    lines.append("|---|---|---|---|---|")
    p = d.prescription
    lines.append(f"| {p['priority']} | {p['action']} | {p['expected_impact']} | {p['risk']} | {p['observation_period']} |")
    lines.append("")
    lines.append("**轉診建議：** " + (f"可進一步使用「{d.referral_skill}」技能深入分析" if d.referral_skill else "無需轉診"))
    return "\n".join(lines)


def _section7(analysis: FullAnalysis) -> str:
    lines = ["| 廣告 | 狀態 | 花費 | 觸及 | Frequency | CPR |", "|---|---|---|---|---|---|"]
    for r in analysis.overview.rows:
        cpr_str = metrics.format_money(r["cpr"]) if r["cpr"] else "N/A"
        lines.append(f"| {r['ad_name']} | {r['status']} | {metrics.format_money(r['spend'])} | "
                     f"{r['reach']} | {r['frequency']:.2f} | {cpr_str} |")
    if len(lines) == 2:
        lines.append("| 無資料 | - | - | - | - | - |")
    lines.append("")
    lines.append(f"**已關閉廣告數量：** {analysis.overview.paused_ads_count} 則（確認無誤觸發或殘留干擾）")
    return "\n".join(lines)


def _pending_changes_section(changes: List[PendingChange]) -> str:
    if not changes:
        return "本期無需人工確認之變更事項。"
    lines = ["| 優先序 | 動作 | 預期影響 | 風險 | 是否需人工核准 |", "|---|---|---|---|---|"]
    for c in changes:
        approval = "是" if c.needs_manual_approval else "否"
        lines.append(f"| {c.priority} | [{c.scope}] {c.action} | {c.expected_impact} | {c.risk} | {approval} |")
    lines.append("")
    lines.append("⚠️ 以上變更皆不會由本系統自動執行，請人工核准後自行至 Meta Ads Manager 後台操作，且一次只改一項。")
    return "\n".join(lines)


def build_report_markdown(report: ReportData, analysis: FullAnalysis,
                           pending_changes: List[PendingChange], today: date = None) -> str:
    today = today or report.period_end
    period_label = f"{report.period_start.isoformat()} ~ {report.period_end.isoformat()}"

    parts = [
        f"# 空房子・0616_0930活動週報｜{period_label}",
        "",
        "## 一句話結論",
        "",
        _one_line_conclusion(analysis),
        "",
        "## 🚦素材燈號提醒（必列於最上方，優先於七大面向）",
        "",
        _fatigue_table(analysis),
        "",
        "## 1. 帳號健檢",
        "",
        _section1(analysis),
        "",
        "## 2. 受眾建構",
        "",
        _section2(analysis),
        "",
        "## 3. 漏斗結構",
        "",
        _section3(analysis),
        "",
        "## 4. 素材策略",
        "",
        _section4(analysis),
        "",
        "## 5. 檔期規劃",
        "",
        _section5(analysis),
        "",
        "## 6. 成效診斷",
        "",
        _section6(analysis),
        "",
        "## 7. 目前投放總覽",
        "",
        _section7(analysis),
        "",
        "## 本期需要人工確認的變更事項（若有）",
        "",
        _pending_changes_section(pending_changes),
        "",
        f"## 下次回顧：{next_review_date(today).isoformat()}",
        "",
    ]
    return "\n".join(parts)
