"""
CLI コマンド体系

サブコマンド:
  analyze   - ローカル画像を分析
  watch     - Chatwork未読を監視して自動分析
  messages  - Chatworkメッセージ確認
  send      - レポートをChatworkに送信
  reports   - レポート一覧/詳細
"""

import argparse
import csv
import glob
import io
import json
import os
import re
import sys
import tempfile
import time

from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = "output"


# ============================================================
# analyze: ローカル画像を分析
# ============================================================
def cmd_analyze(args):
    """ローカル画像をClaude Vision APIで分析してExcel/JSONを生成する。"""
    from src.api.claude import analyze_heatmap_images

    image_paths = args.images
    for p in image_paths:
        if not os.path.exists(p):
            print(f"エラー: ファイルが見つかりません: {p}")
            sys.exit(1)

    print(f"分析中... ({len(image_paths)}枚の画像)")
    analysis = analyze_heatmap_images(image_paths, model=args.model)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # JSON 保存
    page_name = analysis.get("page_name", "unknown")
    version = analysis.get("version", "v1")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(OUTPUT_DIR, f"heatmap_{page_name}_{version}_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"JSON保存: {json_path}")

    # Excel 生成（heatmap_analysis.py の config/blocks を差し替えて実行）
    if not args.json_only:
        try:
            import heatmap_analysis as ha

            ha.config.update({
                "page_name": analysis.get("page_name", ""),
                "version": analysis.get("version", ""),
                "period": analysis.get("period", ""),
                "cv_users": analysis.get("cv_users", 0),
                "click_users": analysis.get("click_users", 0),
                "exit_users": analysis.get("exit_users", 0),
                "findings": analysis.get("findings", []),
            })
            ha.blocks.clear()
            ha.blocks.extend(analysis.get("blocks", []))
            ha.main()
        except Exception as e:
            print(f"Excel生成エラー: {e}")
            print("JSONファイルは正常に保存されています。")

    print(f"\n分析結果サマリー:")
    print(f"  ページ名: {analysis.get('page_name', '不明')}")
    print(f"  ブロック数: {len(analysis.get('blocks', []))}")
    print(f"  CV: {analysis.get('cv_users', 0):,}人 / "
          f"CLICK: {analysis.get('click_users', 0):,}人 / "
          f"離脱: {analysis.get('exit_users', 0):,}人")
    for finding in analysis.get("findings", []):
        print(f"  {finding[:80]}...")


# ============================================================
# watch: Chatwork未読を監視して自動分析
# ============================================================
def cmd_watch(args):
    """Chatwork未読メッセージを監視して画像が投稿されたら自動分析する。"""
    from src.api.chatwork import ChatworkClient
    from src.api.claude import analyze_heatmap_images

    chatwork = ChatworkClient()
    interval = args.interval
    seen_ids = set()

    print(f"Chatwork監視開始 (ルームID: {chatwork.room_id}, 間隔: {interval}秒)")
    print("Ctrl+C で停止")

    while True:
        try:
            messages = chatwork.get_messages()
            for msg in messages:
                msg_id = msg.get("message_id", "")
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                body = msg.get("body", "")
                file_ids = re.findall(r"\[download:(\d+)\]", body)
                if not file_ids:
                    file_ids = re.findall(r"\[file id=(\d+)\]", body, re.IGNORECASE)
                if not file_ids:
                    continue

                print(f"\n画像検出 (msg_id={msg_id}, files={file_ids})")

                with tempfile.TemporaryDirectory() as tmpdir:
                    image_paths = []
                    for fid in file_ids:
                        try:
                            path = chatwork.download_file(fid, save_dir=tmpdir)
                            if path.lower().endswith(
                                (".png", ".jpg", ".jpeg", ".gif", ".webp")
                            ):
                                image_paths.append(path)
                        except Exception as e:
                            print(f"  DL失敗 (id={fid}): {e}")

                    if not image_paths:
                        continue

                    print(f"  分析中... ({len(image_paths)}枚)")
                    analysis = analyze_heatmap_images(image_paths)

                    # CSV 生成
                    csv_path = os.path.join(tmpdir, "heatmap_analysis.csv")
                    _write_csv(analysis, csv_path)

                    # 結果をChatworkに返信
                    summary = _build_chatwork_summary(analysis)
                    chatwork.send_message(summary)
                    chatwork.send_file(csv_path, message="分析結果CSVを添付します。")
                    print(f"  返信完了: {len(analysis.get('blocks', []))}ブロック")

        except KeyboardInterrupt:
            print("\n監視を停止しました。")
            break
        except Exception as e:
            print(f"エラー: {e}")

        time.sleep(interval)


# ============================================================
# messages: Chatworkメッセージ確認
# ============================================================
def cmd_messages(args):
    """Chatworkの最新メッセージを表示する。"""
    from src.api.chatwork import ChatworkClient

    chatwork = ChatworkClient()
    messages = chatwork.get_messages()

    if not messages:
        print("新着メッセージはありません。")
        return

    limit = args.limit
    for msg in messages[-limit:]:
        account = msg.get("account", {})
        name = account.get("name", "不明")
        body = msg.get("body", "")
        msg_id = msg.get("message_id", "")
        print(f"[{msg_id}] {name}:")
        print(f"  {body[:200]}")
        print()


# ============================================================
# send: レポートをChatworkに送信
# ============================================================
def cmd_send(args):
    """レポートファイルをChatworkに送信する。"""
    from src.api.chatwork import ChatworkClient

    chatwork = ChatworkClient()

    report_path = args.report
    if not os.path.exists(report_path):
        # output/ ディレクトリ内で検索
        candidates = glob.glob(os.path.join(OUTPUT_DIR, f"*{report_path}*"))
        if candidates:
            report_path = candidates[0]
        else:
            print(f"エラー: レポートが見つかりません: {report_path}")
            sys.exit(1)

    message = args.message or f"ヒートマップ分析レポート: {os.path.basename(report_path)}"
    result = chatwork.send_file(report_path, message=message)
    print(f"送信完了: {os.path.basename(report_path)}")
    print(f"  file_id: {result.get('file_id', '不明')}")


# ============================================================
# reports: レポート一覧/詳細
# ============================================================
def cmd_reports(args):
    """output/ ディレクトリのレポート一覧を表示する。"""
    if not os.path.exists(OUTPUT_DIR):
        print("レポートはまだありません。")
        return

    files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*")))
    if not files:
        print("レポートはまだありません。")
        return

    if args.detail:
        # 特定レポートの詳細
        target = args.detail
        matches = [f for f in files if target in f]
        if not matches:
            print(f"一致するレポートが見つかりません: {target}")
            return
        path = matches[0]
        if path.endswith(".json"):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"ファイル: {path}")
            print(f"サイズ: {os.path.getsize(path):,} bytes")
        return

    print(f"レポート一覧 ({OUTPUT_DIR}/):")
    for i, f in enumerate(files, 1):
        size = os.path.getsize(f)
        name = os.path.basename(f)
        print(f"  {i}. {name}  ({size:,} bytes)")


# ============================================================
# ヘルパー
# ============================================================
def _write_csv(analysis: dict, path: str):
    """分析結果をCSVファイルに書き出す。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "No", "ブロック名", "位置",
            "CV滞在", "CLICK滞在", "離脱滞在",
            "累計離脱%", "Click反応", "CV反応",
            "分析メモ", "施策案",
        ])
        for i, b in enumerate(analysis.get("blocks", []), 1):
            writer.writerow([
                i, b["name"], b["position"],
                b["cv_dwell"], b["click_dwell"], b["exit_dwell"],
                b["cum_exit"], b["click_resp"], b["cv_resp"],
                b["memo"], b["action"],
            ])


def _build_chatwork_summary(analysis: dict) -> str:
    """Chatwork用サマリーメッセージを生成する。"""
    lines = [
        f"[info][title]ヒートマップ分析完了: {analysis.get('page_name', '不明')}[/title]",
        f"バージョン: {analysis.get('version', '-')}",
        f"CV: {analysis.get('cv_users', 0):,}人 / "
        f"CLICK: {analysis.get('click_users', 0):,}人 / "
        f"離脱: {analysis.get('exit_users', 0):,}人",
        f"ブロック数: {len(analysis.get('blocks', []))}",
        "",
    ]
    for finding in analysis.get("findings", []):
        lines.append(finding)
    lines.append("[/info]")
    return "\n".join(lines)


# ============================================================
# メイン
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        prog="heatmap",
        description="SquadBeyond ヒートマップ分析ツール",
    )
    subparsers = parser.add_subparsers(dest="command", help="サブコマンド")

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="ローカル画像を分析")
    p_analyze.add_argument("images", nargs="+", help="分析する画像ファイル")
    p_analyze.add_argument(
        "--model", default="claude-opus-4-6", help="Claudeモデル (default: claude-opus-4-6)"
    )
    p_analyze.add_argument(
        "--json-only", action="store_true", help="JSONのみ出力（Excel生成をスキップ）"
    )
    p_analyze.set_defaults(func=cmd_analyze)

    # watch
    p_watch = subparsers.add_parser("watch", help="Chatwork未読を監視して自動分析")
    p_watch.add_argument(
        "--interval", type=int, default=30, help="監視間隔（秒, default: 30）"
    )
    p_watch.set_defaults(func=cmd_watch)

    # messages
    p_msg = subparsers.add_parser("messages", help="Chatworkメッセージ確認")
    p_msg.add_argument(
        "--limit", type=int, default=10, help="表示件数 (default: 10)"
    )
    p_msg.set_defaults(func=cmd_messages)

    # send
    p_send = subparsers.add_parser("send", help="レポートをChatworkに送信")
    p_send.add_argument("--report", required=True, help="送信するレポートファイル")
    p_send.add_argument("--message", help="添付メッセージ")
    p_send.set_defaults(func=cmd_send)

    # reports
    p_reports = subparsers.add_parser("reports", help="レポート一覧/詳細")
    p_reports.add_argument("--detail", help="詳細表示するレポートのキーワード")
    p_reports.set_defaults(func=cmd_reports)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
