# 空房子廣告投放｜Meta Marketing API 自動化分析系統

依照《空房子廣告投放｜自動化分析系統提示詞》完整規格實作。只做兩件事：

1. **讀取類功能**（唯讀）：查詢廣告成效、計算素材燈號、產出七大面向分析報告——排程自動執行。
2. **寫入類功能**：只產出「待確認清單」，**不會**呼叫任何 Meta 寫入類 API（暫停/啟用廣告、改預算等），
   需要使用者人工核准後，自行到 Meta Ads Manager 後台操作。

## 安全鐵律（強制遵守，見程式碼中對應註解）

- `api_client.py` 全檔只允許 `HTTP GET`，沒有任何 POST/DELETE 呼叫。
- 全套件（含 `pending_changes.py`）**不存在**任何寫入 Meta API 的函式。
- 監控範圍固定為單一帳號（393708079461309・空房子設計）＋單一活動
  （120246233437410243・2026空房子_裝修_私訊_0616_0930行銷活動），寫死於 `config.py`，
  若要擴大範圍需修改程式碼並經人工二次確認，系統不會自動延伸。
- Token 一律從環境變數 `META_ACCESS_TOKEN` 讀取，程式碼中沒有任何寫死的憑證。

## 安裝

```bash
cd meta_ads_automation
pip install -r requirements.txt
cp .env.example .env   # 編輯 .env 填入 META_ACCESS_TOKEN，或直接 export 環境變數
```

## 使用方式

```bash
# 立即執行一次唯讀分析並產出報告（需要 META_ACCESS_TOKEN）
python -m meta_ads_automation.cli report

# 不需要 Token：用離線示範資料預覽報告格式
python -m meta_ads_automation.cli report --demo

# 只看本期「待確認清單」（不落地存檔）
python -m meta_ads_automation.cli pending

# 啟動排程：每週一、週五 09:00 (Asia/Taipei，可用環境變數調整) 自動執行分析並產出報告
python -m meta_ads_automation.cli schedule
```

報告會存到 `meta_ads_automation/reports/YYYY-MM-DD_live.md`（或 `_demo.md`），
執行狀態（上次回報時間、每則廣告的排名歷史、CTR 趨勢等）存在
`meta_ads_automation/state/state.json`，供下次執行計算「連續兩次低於平均」
「投放週數」「CTR 較兩週前衰退」等需要跨次比較的邏輯。

### 用 cron 或系統排程取代內建 scheduler

若不想長駐執行 `schedule` 指令，也可以直接用 crontab 呼叫 `report`：

```cron
0 9 * * 1,5 cd /path/to/meta_ads_automation/.. && /usr/bin/python3 -m meta_ads_automation.cli report >> /var/log/meta_ads_report.log 2>&1
```

## 模組說明

| 檔案 | 用途 |
|---|---|
| `config.py` | 監控範圍、業務門檻、歷史基準數據等固定設定值 |
| `api_client.py` | Meta Graph API 唯讀客戶端（只有 GET） |
| `models.py` | 共用資料結構 |
| `state_store.py` | 本地 JSON 狀態檔，追蹤跨次比較所需的歷史 |
| `data_pipeline.py` | 把 API 回應組裝成 `ReportData` |
| `demo_data.py` | 離線示範資料，供無 Token 時預覽報告格式 |
| `metrics.py` | 數值換算、排名分類等純函式 |
| `fatigue.py` | 五、素材更換判斷與提前預警——燈號邏輯 |
| `diagnosis.py` | 七大面向分析引擎 |
| `pending_changes.py` | 待確認清單產生器（**不含任何寫入呼叫**） |
| `report_builder.py` | 依範本排版最終 Markdown 報告 |
| `pipeline.py` | 串起以上模組的單次執行流程 |
| `scheduler.py` | 每週一、週五自動觸發 |
| `cli.py` | 命令列入口 |

## 已知限制與待人工確認事項

- 「CPR 較 P50 基準高出 30% 以上且維持 5 天以上」中的「維持天數」，是以report 觸發日期（週一/週五）
  反推的近似值，非逐日監控；如需逐日精準判斷，需改為每日排程。
- 帳戶自身 P25/P50/P75 CPR 基準：累積週資料 ≥ 8 週時採用即時計算，否則自動退回文件中的
  歷史基準表（詳見 `config.CPR_BENCHMARK_FALLBACK`）。
- 「受眾偵察五問」清單僅在使用者明確提出擴大受眾測試需求時才產出，例行報告不會主動建立。
