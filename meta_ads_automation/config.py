"""固定設定值。監控範圍與門檻皆取自需求文件「空房子廣告投放｜自動化分析系統提示詞」，
不可在程式碼中隨意擴大監控範圍——若要調整，需使用者明確二次確認後才能修改本檔。
"""
import os

# ---------------------------------------------------------------------------
# API 連線設定（Token 一律從環境變數讀取，絕不寫死在程式碼中）
# ---------------------------------------------------------------------------
META_API_VERSION = os.environ.get("META_API_VERSION", "v21.0")
META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN")  # 必填，啟動時檢查

# ---------------------------------------------------------------------------
# 一、監控範圍（固定，不可自行擴大）
# ---------------------------------------------------------------------------
AD_ACCOUNT_ID = "393708079461309"  # 空房子設計
AD_ACCOUNT_FULL_ID = f"act_{AD_ACCOUNT_ID}"
CAMPAIGN_ID = "120246233437410243"
CAMPAIGN_NAME = "2026空房子_裝修_私訊_0616_0930行銷活動"
ACCOUNT_DISPLAY_NAME = "空房子設計"

EXCLUDED_CAMPAIGN_NAMES = ["潛在顧客_0804系列", "興趣受眾系列"]
EXCLUDED_ACCOUNTS = {
    "同齊咖啡": "915888767193668",
    "河堤": "1908358303334005",
}

# ---------------------------------------------------------------------------
# 三、固定回報週期
# ---------------------------------------------------------------------------
REPORT_WEEKDAYS = ("mon", "fri")  # 每週一、週五觸發
REPORT_HOUR = int(os.environ.get("META_REPORT_HOUR", "9"))
REPORT_MINUTE = int(os.environ.get("META_REPORT_MINUTE", "0"))
REPORT_TIMEZONE = os.environ.get("META_REPORT_TIMEZONE", "Asia/Taipei")

# ---------------------------------------------------------------------------
# 二 / 三 / 四、業務門檻常數
# ---------------------------------------------------------------------------
MONTHLY_BUDGET_TWD = 15000
WEEKLY_CONVERSION_SUFFICIENT_THRESHOLD = 50  # 週均轉換事件數「資料充足」門檻
MAX_ADS_PER_CAMPAIGN = 2  # 極簡結構：1活動、最多2則廣告

# 冷受眾週頻次警戒線
COLD_AUDIENCE_FREQUENCY_WARNING_RANGE = (2.0, 2.5)

# 素材疲乏歷史週期（週）
FATIGUE_CYCLE_WEEKS_RANGE = (6, 8)
FATIGUE_PREP_START_WEEK = 6  # 滿6週即應開始準備下一批素材

# 檔期規劃：農曆年前裝修潮
SEASONAL_CAMPAIGN = {
    "name": "農曆年前裝修潮",
    "prewarm_start_month": 10,   # 10月中開始預熱
    "prewarm_start_day": 15,
    "peak_start_month": 11,      # 11-12月為蓄水高峰
    "peak_end_month": 12,
    "prompt_window_days": (30, 45),  # 檔期前 D-45 至 D-30 主動提示
}

# ---------------------------------------------------------------------------
# 六、歷史基準數據（用於成效診斷的比較基礎）
# ---------------------------------------------------------------------------
MONTHLY_HISTORY = {
    "6月": {"spend": 10593, "messages": 49, "cpr": 216, "note": "健康期（0623/0629為主力）"},
    "7月": {"spend": 20689, "messages": 91, "cpr": 227, "note": "花費放大近2倍，效率仍穩健"},
    "8月": {"spend": 13781, "messages": 51, "cpr": 270, "note": "疲乏期，轉換率排名掉至「低於平均-倒數35%」"},
    "9月(至9/8)": {"spend": 4880, "messages": 18, "cpr": 271, "note": "換新素材(0901)後，轉換率排名回升至「高於平均」"},
}

AD_HISTORICAL_REFERENCE = {
    "0623/0629（初代）": {
        "period": "6月", "cpr_range": (168, 267),
        "fatigue_signal": "投放約8週後（8月）CPR升至270-291，排名轉差",
    },
    "0806": {
        "period": "8月", "cpr_range": (286, 286),
        "fatigue_signal": "短期測試",
    },
    "0814": {
        "period": "8-9月", "cpr_range": (227, 239),
        "fatigue_signal": "9月狀態顯示「處理中」需留意審查結果",
    },
    "0901": {
        "period": "9月起", "cpr_range": (258, 258),
        "fatigue_signal": "剛上線，轉換率排名「高於平均」，健康期",
    },
}

# 累積數據不足 90 天前，成效診斷暫代使用的 P25/P50/P75 CPR 基準
# （取自歷史 CPR 區間估算：168-291 之間）
CPR_BENCHMARK_FALLBACK = {"p25": 200, "p50": 250, "p75": 280}

STRATEGY_DECISIONS_LOCKED = [
    "廣泛受眾（不設興趣標籤）優於加設「室內設計」等軟性興趣標籤",
    "私訊型（Messaging）優化目標的轉換效率，遠優於名單型（Leads）——名單型曾出現 "
    "CPR 766-2,704 的失控案例，已判定不適合目前的表單/流程設計，暫緩該路線",
    "同一廣告組合內放置 2 則以上廣告，必然出現資源互搶（CBO 機制下系統會偏好其中一則），"
    "此活動歷史上已多次驗證此現象",
]


def min_daily_budget_floor(cpa: float = None, weekly_target: int = WEEKLY_CONVERSION_SUFFICIENT_THRESHOLD) -> float:
    """單組日預算下限 = allowed CPA × 50 ÷ 7"""
    cpa = cpa if cpa is not None else CPR_BENCHMARK_FALLBACK["p50"]
    return round(cpa * weekly_target / 7, 0)


def require_access_token() -> str:
    if not META_ACCESS_TOKEN:
        raise RuntimeError(
            "缺少環境變數 META_ACCESS_TOKEN。請在執行前設定："
            "export META_ACCESS_TOKEN=你的Meta長期存取權杖，"
            "絕不可將 Token 寫死於程式碼中。"
        )
    return META_ACCESS_TOKEN
