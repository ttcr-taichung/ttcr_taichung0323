"""單次執行的完整流程：抓資料（唯讀）→ 七大面向分析 → 待確認清單 → 報告排版 → 落地存檔。
不含任何寫入 API 呼叫。
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Optional

from .api_client import MetaMarketingReadOnlyClient
from .data_pipeline import fetch_live_data
from .demo_data import build_demo_data
from .diagnosis import run_full_analysis
from .pending_changes import build_pending_changes
from .report_builder import build_report_markdown
from .state_store import StateStore

logger = logging.getLogger(__name__)

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")


def run_report_pipeline(demo: bool = False, today: Optional[date] = None, save: bool = True) -> str:
    today = today or date.today()
    state = StateStore()

    if demo:
        report_data = build_demo_data(today)
    else:
        client = MetaMarketingReadOnlyClient()
        report_data = fetch_live_data(client, state, today)

    analysis = run_full_analysis(report_data, today)
    pending = build_pending_changes(analysis)
    markdown = build_report_markdown(report_data, analysis, pending, today)

    if not demo:
        state.set_last_run(
            datetime.utcnow().isoformat(),
            report_data.period_start.isoformat(),
            report_data.period_end.isoformat(),
        )
        state.save()

    if save:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        filename = f"{today.isoformat()}_{'demo' if demo else 'live'}.md"
        path = os.path.join(REPORTS_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(markdown)
        logger.info("報告已儲存：%s", path)

    return markdown
