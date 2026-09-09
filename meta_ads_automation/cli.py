"""命令列入口。

用法：
  python -m meta_ads_automation.cli report            # 立即執行一次唯讀分析並產出報告
  python -m meta_ads_automation.cli report --demo     # 離線示範資料，不需要 Token、不呼叫 API
  python -m meta_ads_automation.cli schedule          # 啟動排程（每週一、週五自動執行）
  python -m meta_ads_automation.cli pending           # 只顯示本期待確認的變更清單
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from .demo_data import build_demo_data
from .diagnosis import run_full_analysis
from .pending_changes import build_pending_changes
from .pipeline import run_report_pipeline


def _cmd_report(args: argparse.Namespace) -> None:
    markdown = run_report_pipeline(demo=args.demo, save=not args.no_save)
    print(markdown)


def _cmd_pending(args: argparse.Namespace) -> None:
    today = date.today()
    if args.demo:
        report_data = build_demo_data(today)
    else:
        from .api_client import MetaMarketingReadOnlyClient
        from .data_pipeline import fetch_live_data
        from .state_store import StateStore
        client = MetaMarketingReadOnlyClient()
        report_data = fetch_live_data(client, StateStore(), today)

    analysis = run_full_analysis(report_data, today)
    changes = build_pending_changes(analysis)
    if not changes:
        print("本期無需人工確認之變更事項。")
        return
    print("優先序 | 層級/對象 | 動作 | 預期影響 | 風險")
    for c in changes:
        print(f"{c.priority} | {c.scope} | {c.action} | {c.expected_impact} | {c.risk}")
    print("\n⚠️ 以上皆需人工核准後自行至 Meta Ads Manager 後台操作，本系統不會自動執行任何寫入動作。")


def _cmd_schedule(_args: argparse.Namespace) -> None:
    from .scheduler import start_scheduler
    start_scheduler()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meta_ads_automation",
        description="空房子廣告投放｜Meta Marketing API 自動化分析系統（唯讀分析 + 待確認清單，不含自動寫入）",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="顯示 DEBUG 等級日誌")
    sub = parser.add_subparsers(dest="command", required=True)

    p_report = sub.add_parser("report", help="立即執行一次七大面向分析並產出報告（唯讀）")
    p_report.add_argument("--demo", action="store_true", help="使用離線示範資料，不需要 META_ACCESS_TOKEN")
    p_report.add_argument("--no-save", action="store_true", help="只印出報告，不寫入 reports/ 目錄")
    p_report.set_defaults(func=_cmd_report)

    p_pending = sub.add_parser("pending", help="只顯示本期待確認的變更清單（不產出完整報告、不落地存檔）")
    p_pending.add_argument("--demo", action="store_true", help="使用離線示範資料")
    p_pending.set_defaults(func=_cmd_pending)

    p_schedule = sub.add_parser("schedule", help="啟動排程：每週一、週五自動執行唯讀分析並產出報告")
    p_schedule.set_defaults(func=_cmd_schedule)

    return parser


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args.func(args)


if __name__ == "__main__":
    main()
