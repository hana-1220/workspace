#!/usr/bin/env python3
"""
CATs CV通知 — Render Webサービス用ラッパー
バックグラウンドスレッドでCV通知ループを実行しつつ、
ヘルスチェック用のHTTPサーバーを提供する
"""

import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from cats_cv_notify import run_loop


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass  # ログ抑制


def main():
    # CV通知ループをバックグラウンドで起動
    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    print("[SERVER] CV notify thread started")

    # ヘルスチェック用HTTPサーバー
    port = int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"[SERVER] Health check listening on :{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
