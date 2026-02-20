"""
Webhook サーバー（Flask）

Chatwork にヒートマップ画像が投稿されたら自動で分析し、CSV を返信する。
Railway / Render にデプロイ可能な構成。
"""

import csv
import io
import os
import re
import tempfile

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

app = Flask(__name__)


def _create_app_dependencies():
    """遅延インポートで依存モジュールを読み込む。"""
    from src.api.chatwork import ChatworkClient
    from src.api.claude import analyze_heatmap_images

    return ChatworkClient(), analyze_heatmap_images


def _analysis_to_csv(analysis: dict) -> str:
    """分析結果をCSV文字列に変換する。"""
    output = io.StringIO()
    writer = csv.writer(output)

    # ヘッダー
    writer.writerow([
        "No", "ブロック名", "位置",
        "CV滞在", "CLICK滞在", "離脱滞在",
        "累計離脱%", "Click反応", "CV反応",
        "分析メモ", "施策案",
    ])

    blocks = analysis.get("blocks", [])
    prev_exit = 0
    for i, b in enumerate(blocks, 1):
        section_exit = round(b["cum_exit"] - prev_exit, 1)
        prev_exit = b["cum_exit"]
        writer.writerow([
            i, b["name"], b["position"],
            b["cv_dwell"], b["click_dwell"], b["exit_dwell"],
            b["cum_exit"], b["click_resp"], b["cv_resp"],
            b["memo"], b["action"],
        ])

    return output.getvalue()


def _build_summary_message(analysis: dict) -> str:
    """分析結果のサマリーメッセージを生成する。"""
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


@app.route("/health", methods=["GET"])
def health():
    """ヘルスチェック"""
    return jsonify({"status": "ok"})


@app.route("/webhook/chatwork", methods=["POST"])
def chatwork_webhook():
    """
    Chatwork Webhook エンドポイント。
    画像ファイル付きメッセージを受信したら自動分析 → CSV返信。
    """
    payload = request.get_json(silent=True) or {}

    event_type = payload.get("webhook_event_type")
    if event_type != "message_created":
        return jsonify({"status": "ignored", "reason": "not message_created"})

    event = payload.get("webhook_event", {})
    body = event.get("body", "")
    room_id = str(event.get("room_id", ""))

    # メッセージ中のファイル参照を検出: [file id=XXX]
    file_ids = re.findall(r"\[download:(\d+)\]", body)
    if not file_ids:
        # [file id=XXX] 形式も試す
        file_ids = re.findall(r"\[file id=(\d+)\]", body, re.IGNORECASE)
    if not file_ids:
        return jsonify({"status": "ignored", "reason": "no files"})

    try:
        chatwork, analyze = _create_app_dependencies()

        # ファイルをダウンロード
        image_paths = []
        with tempfile.TemporaryDirectory() as tmpdir:
            for fid in file_ids:
                try:
                    path = chatwork.download_file(fid, save_dir=tmpdir, room_id=room_id)
                    # 画像ファイルのみ対象
                    if path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                        image_paths.append(path)
                except Exception as e:
                    app.logger.warning(f"ファイルDL失敗 (id={fid}): {e}")

            if not image_paths:
                return jsonify({"status": "ignored", "reason": "no image files"})

            # Claude Vision API で分析
            analysis = analyze(image_paths)

            # CSV を生成して一時ファイルに保存
            csv_content = _analysis_to_csv(analysis)
            csv_path = os.path.join(tmpdir, "heatmap_analysis.csv")
            with open(csv_path, "w", encoding="utf-8-sig") as f:
                f.write(csv_content)

            # サマリーメッセージ送信
            summary = _build_summary_message(analysis)
            chatwork.send_message(summary, room_id=room_id)

            # CSV ファイル送信
            chatwork.send_file(
                csv_path,
                message="分析結果CSVを添付します。",
                room_id=room_id,
            )

        return jsonify({"status": "ok", "blocks": len(analysis.get("blocks", []))})

    except Exception as e:
        app.logger.error(f"Webhook処理エラー: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
