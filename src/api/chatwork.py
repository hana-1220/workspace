"""
Chatwork API 連携モジュール

メッセージ送信・ファイル送信・ファイルダウンロード機能を提供する。
CHATWORK_API_TOKEN, CHATWORK_ROOM_ID は .env から読み込む。
"""

import os
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.chatwork.com/v2"


class ChatworkClient:
    """Chatwork API クライアント"""

    def __init__(self, api_token: Optional[str] = None, room_id: Optional[str] = None):
        self.api_token = api_token or os.environ.get("CHATWORK_API_TOKEN", "")
        self.room_id = room_id or os.environ.get("CHATWORK_ROOM_ID", "")
        if not self.api_token:
            raise ValueError(
                "CHATWORK_API_TOKEN が設定されていません。"
                ".env ファイルまたは環境変数で設定してください。"
            )

    @property
    def _headers(self) -> dict:
        return {"X-ChatWorkToken": self.api_token}

    def send_message(self, body: str, room_id: Optional[str] = None) -> dict:
        """テキストメッセージを送信する。"""
        rid = room_id or self.room_id
        url = f"{BASE_URL}/rooms/{rid}/messages"
        resp = requests.post(url, headers=self._headers, data={"body": body})
        resp.raise_for_status()
        return resp.json()

    def send_file(
        self,
        file_path: str,
        message: str = "",
        room_id: Optional[str] = None,
    ) -> dict:
        """ファイルをアップロードして送信する。"""
        rid = room_id or self.room_id
        url = f"{BASE_URL}/rooms/{rid}/files"
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            files = {"file": (filename, f)}
            data = {"message": message} if message else {}
            resp = requests.post(
                url, headers=self._headers, files=files, data=data
            )
        resp.raise_for_status()
        return resp.json()

    def get_messages(
        self, room_id: Optional[str] = None, force: bool = True
    ) -> List[dict]:
        """メッセージ一覧を取得する。"""
        rid = room_id or self.room_id
        url = f"{BASE_URL}/rooms/{rid}/messages"
        params = {"force": 1 if force else 0}
        resp = requests.get(url, headers=self._headers, params=params)
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json()

    def get_file_info(
        self, file_id: str, room_id: Optional[str] = None
    ) -> dict:
        """ファイル情報（ダウンロードURL含む）を取得する。"""
        rid = room_id or self.room_id
        url = f"{BASE_URL}/rooms/{rid}/files/{file_id}"
        params = {"create_download_url": 1}
        resp = requests.get(url, headers=self._headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def download_file(
        self, file_id: str, save_dir: str = "input", room_id: Optional[str] = None
    ) -> str:
        """ファイルをダウンロードしてローカルに保存する。パスを返す。"""
        file_info = self.get_file_info(file_id, room_id)
        download_url = file_info.get("download_url", "")
        if not download_url:
            raise ValueError(f"ダウンロードURLが取得できません: file_id={file_id}")

        filename = file_info.get("filename", f"file_{file_id}")
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, filename)

        resp = requests.get(download_url, headers=self._headers)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(resp.content)

        return save_path

    def get_rooms(self) -> List[dict]:
        """ルーム一覧を取得する。"""
        url = f"{BASE_URL}/rooms"
        resp = requests.get(url, headers=self._headers)
        resp.raise_for_status()
        return resp.json()
