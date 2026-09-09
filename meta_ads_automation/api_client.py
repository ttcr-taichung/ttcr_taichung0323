"""Meta Marketing API 唯讀客戶端。

安全鐵律：本檔案「只允許 HTTP GET」，全檔不得出現任何 POST/DELETE 呼叫。
任何寫入需求（暫停/啟用廣告、改預算等）一律不得在此新增方法，
只能透過 pending_changes.py 產出待確認清單，交由使用者自行到 Meta Ads Manager 後台操作。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterable, List, Optional

import requests

from . import config

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.facebook.com"

# 私訊型轉換事件（Messaging）常見 action_type，涵蓋不同 API 版本命名
MESSAGING_ACTION_TYPES = (
    "onsite_conversion.messaging_conversation_started_7d",
    "onsite_conversion.total_messaging_connection",
    "onsite_conversion.messaging_first_reply",
    "onsite_conversion.messaging_user_depth_2_message_send",
)


class MetaAPIError(RuntimeError):
    pass


class MetaMarketingReadOnlyClient:
    """僅封裝 GET 請求的 Meta Graph API 客戶端。"""

    def __init__(self, access_token: Optional[str] = None, api_version: Optional[str] = None,
                 max_retries: int = 3, timeout: int = 30):
        self.access_token = access_token or config.require_access_token()
        self.api_version = api_version or config.META_API_VERSION
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = requests.Session()

    # ------------------------------------------------------------------
    # 底層：只有 GET，沒有其他 HTTP method
    # ------------------------------------------------------------------
    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{GRAPH_BASE_URL}/{self.api_version}/{path.lstrip('/')}"
        params = dict(params or {})
        params["access_token"] = self.access_token

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("Meta API GET 失敗（第 %s 次）：%s", attempt, exc)
                time.sleep(min(2 ** attempt, 10))
                continue

            if resp.status_code == 200:
                return resp.json()

            body = _safe_json(resp)
            err = (body or {}).get("error", {})
            code = err.get("code")
            # 429 / 限流相關錯誤碼可重試，其餘視為不可重試
            if resp.status_code == 429 or code in (4, 17, 32, 613):
                last_error = MetaAPIError(f"HTTP {resp.status_code}: {err}")
                logger.warning("Meta API 限流/暫時性錯誤（第 %s 次）：%s", attempt, err)
                time.sleep(min(2 ** attempt, 10))
                continue

            raise MetaAPIError(f"Meta API 呼叫失敗 HTTP {resp.status_code}: {err} (url={url})")

        raise MetaAPIError(f"Meta API 呼叫重試 {self.max_retries} 次後仍失敗：{last_error}")

    def _get_paged(self, path: str, params: Optional[Dict[str, Any]] = None,
                    max_pages: int = 20) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        data = self._get(path, params)
        results.extend(data.get("data", []))

        pages = 1
        next_url = data.get("paging", {}).get("next")
        while next_url and pages < max_pages:
            resp = self.session.get(next_url, timeout=self.timeout)
            if resp.status_code != 200:
                break
            data = resp.json()
            results.extend(data.get("data", []))
            next_url = data.get("paging", {}).get("next")
            pages += 1
        return results

    # ------------------------------------------------------------------
    # 帳號層
    # ------------------------------------------------------------------
    def get_account_status(self) -> Dict[str, Any]:
        fields = ",".join([
            "account_status", "disable_reason", "amount_spent", "balance",
            "currency", "spend_cap", "funding_source_details", "name",
        ])
        return self._get(config.AD_ACCOUNT_FULL_ID, {"fields": fields})

    # ------------------------------------------------------------------
    # 活動 / 廣告層
    # ------------------------------------------------------------------
    def get_campaign_info(self, campaign_id: str = config.CAMPAIGN_ID) -> Dict[str, Any]:
        fields = ",".join(["id", "name", "status", "effective_status", "daily_budget",
                            "lifetime_budget", "created_time", "start_time", "stop_time"])
        return self._get(campaign_id, {"fields": fields})

    def get_ads_in_campaign(self, campaign_id: str = config.CAMPAIGN_ID) -> List[Dict[str, Any]]:
        fields = ",".join([
            "id", "name", "status", "effective_status", "adset_id", "created_time",
            "updated_time", "creative{id,name,thumbnail_url}",
        ])
        return self._get_paged(f"{campaign_id}/ads", {"fields": fields, "limit": 100})

    def get_adsets_in_campaign(self, campaign_id: str = config.CAMPAIGN_ID) -> List[Dict[str, Any]]:
        fields = ",".join([
            "id", "name", "status", "effective_status", "daily_budget",
            "lifetime_budget", "targeting", "optimization_goal", "created_time",
        ])
        return self._get_paged(f"{campaign_id}/adsets", {"fields": fields, "limit": 100})

    # ------------------------------------------------------------------
    # Insights（成效數據）
    # ------------------------------------------------------------------
    INSIGHT_FIELDS = ",".join([
        "ad_id", "ad_name", "adset_id", "campaign_id", "spend", "impressions",
        "reach", "clicks", "ctr", "cpm", "cpc", "frequency", "actions",
        "cost_per_action_type", "quality_ranking", "engagement_rate_ranking",
        "conversion_rate_ranking", "date_start", "date_stop",
    ])

    def get_insights(self, object_id: str, level: str = "ad",
                      since: Optional[str] = None, until: Optional[str] = None,
                      date_preset: Optional[str] = None,
                      time_increment: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "level": level,
            "fields": self.INSIGHT_FIELDS,
            "limit": 200,
        }
        if since and until:
            params["time_range"] = f'{{"since":"{since}","until":"{until}"}}'
        elif date_preset:
            params["date_preset"] = date_preset
        if time_increment:
            params["time_increment"] = time_increment
        return self._get_paged(f"{object_id}/insights", params)


def _safe_json(resp: requests.Response) -> Optional[Dict[str, Any]]:
    try:
        return resp.json()
    except ValueError:
        return None


def extract_messaging_conversions(actions: Optional[Iterable[Dict[str, Any]]]) -> int:
    if not actions:
        return 0
    total = 0
    matched = False
    for a in actions:
        atype = a.get("action_type", "")
        if atype in MESSAGING_ACTION_TYPES:
            total += int(float(a.get("value", 0)))
            matched = True
    if matched:
        return total
    # fallback：找不到已知 action_type 時，退而求其次比對關鍵字
    for a in actions:
        if "messaging" in a.get("action_type", ""):
            total += int(float(a.get("value", 0)))
    return total


def extract_cost_per_messaging_conversion(cost_per_action_type: Optional[Iterable[Dict[str, Any]]]) -> Optional[float]:
    if not cost_per_action_type:
        return None
    for c in cost_per_action_type:
        if c.get("action_type") in MESSAGING_ACTION_TYPES or "messaging" in c.get("action_type", ""):
            try:
                return float(c.get("value"))
            except (TypeError, ValueError):
                return None
    return None
