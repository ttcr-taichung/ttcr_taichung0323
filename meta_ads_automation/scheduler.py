"""每週一、週五自動觸發第1項（讀取類）分析並產出報告。
本檔案只呼叫 pipeline.run_report_pipeline（純唯讀），絕不觸發任何寫入動作。
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config
from .pipeline import run_report_pipeline

logger = logging.getLogger(__name__)


def _scheduled_job() -> None:
    try:
        markdown = run_report_pipeline(demo=False)
        logger.info("排程報告執行完成，長度 %d 字元", len(markdown))
    except Exception:
        # 任何 API 或資料錯誤都只記錄、不中斷排程本身，避免下次觸發時間被錯過
        logger.exception("排程報告執行失敗，本次略過，將於下次排程時間（週一/週五）重試")


def start_scheduler() -> None:
    scheduler = BlockingScheduler(timezone=config.REPORT_TIMEZONE)
    scheduler.add_job(
        _scheduled_job,
        CronTrigger(
            day_of_week="mon,fri",
            hour=config.REPORT_HOUR,
            minute=config.REPORT_MINUTE,
            timezone=config.REPORT_TIMEZONE,
        ),
        id="meta_ads_weekly_report",
        misfire_grace_time=3600,
        coalesce=True,
    )
    logger.info(
        "排程已啟動：每週一、週五 %02d:%02d (%s) 自動執行唯讀分析並產出報告",
        config.REPORT_HOUR, config.REPORT_MINUTE, config.REPORT_TIMEZONE,
    )
    scheduler.start()
