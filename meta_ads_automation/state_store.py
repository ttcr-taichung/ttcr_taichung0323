"""本地狀態存檔：記錄上次觸發時間、每則廣告的排名歷史（供連續兩次低於平均判斷）、
以及 CTR 週趨勢，供燈號與診斷邏輯比對用。純本地 JSON 檔，不涉及任何外部寫入。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

DEFAULT_STATE_PATH = os.environ.get(
    "META_ADS_STATE_PATH",
    os.path.join(os.path.dirname(__file__), "state", "state.json"),
)

_EMPTY_STATE = {
    "last_run": None,          # {"timestamp": iso, "period_start": iso, "period_end": iso}
    "ads": {},                 # ad_id -> {"conversion_rank_history": [...], "ctr_history": [{"date":..,"ctr":..}], "first_seen": iso}
}


def _load(path: str = DEFAULT_STATE_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        return json.loads(json.dumps(_EMPTY_STATE))
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return json.loads(json.dumps(_EMPTY_STATE))


def _save(state: Dict[str, Any], path: str = DEFAULT_STATE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


class StateStore:
    def __init__(self, path: str = DEFAULT_STATE_PATH):
        self.path = path
        self.state = _load(path)

    def save(self) -> None:
        _save(self.state, self.path)

    # ---------------- last run / period window ----------------
    def get_last_run(self) -> Optional[Dict[str, str]]:
        return self.state.get("last_run")

    def set_last_run(self, timestamp: str, period_start: str, period_end: str) -> None:
        self.state["last_run"] = {
            "timestamp": timestamp,
            "period_start": period_start,
            "period_end": period_end,
        }

    # ---------------- per-ad history ----------------
    def get_ad_record(self, ad_id: str) -> Dict[str, Any]:
        return self.state["ads"].setdefault(ad_id, {
            "conversion_rank_history": [],
            "ctr_history": [],
            "first_seen": None,
        })

    def record_first_seen(self, ad_id: str, created_time_iso: str) -> None:
        rec = self.get_ad_record(ad_id)
        if not rec.get("first_seen"):
            rec["first_seen"] = created_time_iso

    def push_conversion_rank(self, ad_id: str, rank_label: str, run_timestamp: str, keep: int = 10) -> None:
        rec = self.get_ad_record(ad_id)
        rec["conversion_rank_history"].append({"timestamp": run_timestamp, "rank": rank_label})
        rec["conversion_rank_history"] = rec["conversion_rank_history"][-keep:]

    def consecutive_low_rank_count(self, ad_id: str) -> int:
        """回傳目前連續「低於平均」的次數（含本次已寫入的最新一筆）。"""
        rec = self.get_ad_record(ad_id)
        history = rec.get("conversion_rank_history", [])
        count = 0
        for entry in reversed(history):
            if entry.get("rank") == "低於平均":
                count += 1
            else:
                break
        return count

    def push_ctr(self, ad_id: str, date_iso: str, ctr: float, keep: int = 20) -> None:
        rec = self.get_ad_record(ad_id)
        rec["ctr_history"].append({"date": date_iso, "ctr": ctr})
        rec["ctr_history"] = rec["ctr_history"][-keep:]

    def ctr_two_weeks_ago(self, ad_id: str, weeks: int = 2) -> Optional[float]:
        rec = self.get_ad_record(ad_id)
        history = rec.get("ctr_history", [])
        if len(history) <= weeks:
            return history[0]["ctr"] if history else None
        return history[-(weeks + 1)]["ctr"]

    def weeks_running(self, ad_id: str, as_of: Optional[datetime] = None) -> Optional[int]:
        rec = self.get_ad_record(ad_id)
        first_seen = rec.get("first_seen")
        if not first_seen:
            return None
        as_of = as_of or datetime.utcnow()
        started = datetime.fromisoformat(first_seen.replace("Z", "+00:00")).replace(tzinfo=None)
        delta_days = (as_of - started).days
        return max(delta_days // 7, 0)

    def cpr_above_p50_streak_days(self, ad_id: str) -> int:
        """回傳目前連續高於 P50 門檻的期間跨了幾個日曆天（以最早與最新一次記錄的日期差計算）。
        因報告每週僅觸發兩次（週一、週五），此為以回報日期反推的近似值。
        """
        rec = self.get_ad_record(ad_id)
        dates = rec.get("cpr_above_p50_dates", [])
        if len(dates) < 2:
            return 0
        from datetime import date as _date
        first = _date.fromisoformat(dates[0])
        last = _date.fromisoformat(dates[-1])
        return (last - first).days

    def push_cpr_above_p50_flag(self, ad_id: str, date_iso: str, is_above: bool, keep: int = 30) -> None:
        rec = self.get_ad_record(ad_id)
        dates: List[str] = rec.setdefault("cpr_above_p50_dates", [])
        if is_above:
            dates.append(date_iso)
        else:
            dates.clear()
        rec["cpr_above_p50_dates"] = dates[-keep:]
