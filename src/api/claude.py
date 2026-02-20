"""
Claude Vision API によるヒートマップ画像の自動分析モジュール

ヒートマップ画像をbase64でClaude APIに送信し、
ブロック分割・スコア算出結果をJSON形式で返す。
"""

import base64
import json
import mimetypes
import os
from typing import Dict, List, Optional, Tuple

import anthropic
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """\
あなたはSquadBeyondヒートマップ分析の専門家です。
ヒートマップのスクリーンショット画像を受け取り、以下の手順で分析してください。

## 1. ページ情報の読み取り
- ページ名、バージョン（わかれば）
- 3列の種類（通常: CV / CLICK / 離脱）
- 各列のユーザー数（ヘッダーの緑タグの数字）

## 2. ブロック分割（15-40ブロック程度）
- ビジュアルの切れ目、コンテンツの役割変化で区切る
- 各ブロックにブロック名とページ位置（%）を付与

## 3. 各ブロックのデータ読取

### 滞在時間（5段階、3列それぞれ）
- 5 = 長い（赤）
- 4 = やや長い（オレンジ）
- 3 = 普通（黄）
- 2 = やや短い（黄緑）
- 1 = 短い（緑〜青）

### 離脱率
離脱ヒートマップの%表示から累計離脱%を読み取る

### クリック/CV反応
- ◎ = 多い
- ○ = あり
- △ = 少ない
- × = なし

## 4. 分析メモ・施策案
- 3列の色の違いを具体的に記述（例：「CV列赤 vs 離脱列青」）
- ユーザー数を引用して記述
- 施策案には★マークで優先度を示す（★★★ > ★★ > ★）

## 出力フォーマット
必ず以下のJSON構造で返してください。JSON以外のテキストは含めないでください。
"""

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "page_name": {"type": "string", "description": "ページ名"},
        "version": {"type": "string", "description": "バージョン名"},
        "period": {"type": "string", "description": "分析期間"},
        "cv_users": {"type": "integer", "description": "CVユーザー数"},
        "click_users": {"type": "integer", "description": "CLICKユーザー数"},
        "exit_users": {"type": "integer", "description": "離脱ユーザー数"},
        "findings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3列比較から得られた主要な発見（3つ）",
        },
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "ブロック名"},
                    "position": {
                        "type": "string",
                        "description": "ページ位置（例: 0-5%）",
                    },
                    "cv_dwell": {
                        "type": "integer",
                        "description": "CV列の滞在時間（1-5）",
                    },
                    "click_dwell": {
                        "type": "integer",
                        "description": "CLICK列の滞在時間（1-5）",
                    },
                    "exit_dwell": {
                        "type": "integer",
                        "description": "離脱列の滞在時間（1-5）",
                    },
                    "cum_exit": {
                        "type": "number",
                        "description": "累計離脱率（%）",
                    },
                    "click_resp": {
                        "type": "string",
                        "description": "クリック反応（◎/○/△/×）",
                    },
                    "cv_resp": {
                        "type": "string",
                        "description": "CV反応（◎/○/△/×）",
                    },
                    "memo": {"type": "string", "description": "分析メモ"},
                    "action": {"type": "string", "description": "施策案"},
                },
                "required": [
                    "name",
                    "position",
                    "cv_dwell",
                    "click_dwell",
                    "exit_dwell",
                    "cum_exit",
                    "click_resp",
                    "cv_resp",
                    "memo",
                    "action",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "page_name",
        "version",
        "period",
        "cv_users",
        "click_users",
        "exit_users",
        "findings",
        "blocks",
    ],
    "additionalProperties": False,
}


def _encode_image(image_path: str) -> Tuple[str, str]:
    """画像ファイルをbase64エンコードし、(data, media_type)を返す。"""
    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type is None:
        mime_type = "image/png"
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, mime_type


def analyze_heatmap_images(
    image_paths: List[str],
    model: str = "claude-opus-4-6",
    api_key: Optional[str] = None,
) -> dict:
    """
    複数のヒートマップ画像をClaude Vision APIで分析する。

    Args:
        image_paths: 画像ファイルパスのリスト
        model: 使用するClaudeモデルID
        api_key: APIキー（省略時は環境変数から読み込み）

    Returns:
        分析結果のdict（config + blocks構造）
    """
    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    content = []
    for path in image_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(f"画像が見つかりません: {path}")
        data, media_type = _encode_image(path)
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data,
                },
            }
        )

    content.append(
        {
            "type": "text",
            "text": (
                "上記のヒートマップスクリーンショットを分析してください。"
                "3列（CV / CLICK / 離脱）の色の違いに注目し、"
                "ブロックごとの滞在時間・離脱率・反応を読み取ってください。"
            ),
        }
    )

    response = client.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": ANALYSIS_SCHEMA,
            }
        },
    )

    result_text = response.content[0].text
    return json.loads(result_text)


def analyze_single_image(
    image_path: str,
    model: str = "claude-opus-4-6",
    api_key: Optional[str] = None,
) -> dict:
    """単一のヒートマップ画像を分析する。"""
    return analyze_heatmap_images([image_path], model=model, api_key=api_key)
