# SquadBeyond ヒートマップ分析システム

## あなたの役割
SquadBeyondのヒートマップスクリーンショットを受け取り、ブロック別に分析してExcelレポートを自動生成する。
Chatwork連携により、画像投稿→自動分析→CSV返信のワークフローも対応。

## プロジェクト構成

```
heatmap-analyzer/
├── CLAUDE.md              # このファイル（プロジェクト仕様）
├── requirements.txt       # Python依存パッケージ
├── .env.example           # 環境変数テンプレート
├── .env                   # 環境変数（git管理外）
├── Procfile               # Railway/Render デプロイ用
├── Dockerfile             # コンテナデプロイ用
├── heatmap_analysis.py    # Excel レポート生成エンジン
├── pdf_to_images.py       # PDF → ページ別PNG変換
├── src/
│   ├── api/
│   │   ├── claude.py      # Claude Vision API（画像→JSON分析）
│   │   └── chatwork.py    # Chatwork API（メッセージ/ファイル送受信）
│   ├── server.py          # Flask Webhook サーバー
│   └── cli.py             # CLIコマンド体系
├── input/                 # 入力ファイル配置場所
├── pdf_pages/             # 変換済みPNGページ
└── output/                # 生成レポート（Excel/JSON/CSV）
```

## 環境変数（.env）

```
ANTHROPIC_API_KEY=       # Claude API キー
CHATWORK_API_TOKEN=      # Chatwork API トークン
CHATWORK_ROOM_ID=        # Chatwork ルームID
PORT=8080                # Webhook サーバーポート
```

## CLIコマンド

```bash
# ローカル画像を分析 → Excel + JSON 出力
python -m src.cli analyze image1.png image2.png

# JSON のみ出力
python -m src.cli analyze --json-only image1.png

# Chatwork 未読を監視して自動分析
python -m src.cli watch --interval 30

# Chatwork メッセージ確認
python -m src.cli messages --limit 10

# レポートを Chatwork に送信
python -m src.cli send --report output/heatmap_xxx.xlsx

# レポート一覧
python -m src.cli reports
python -m src.cli reports --detail heatmap_xxx
```

## Webhook サーバー

```bash
# ローカル起動
python -m src.server

# 本番（gunicorn）
gunicorn src.server:app --bind 0.0.0.0:8080

# Docker
docker build -t heatmap-analyzer .
docker run -p 8080:8080 --env-file .env heatmap-analyzer
```

### エンドポイント
- `GET /health` — ヘルスチェック
- `POST /webhook/chatwork` — Chatwork Webhook 受信

### Chatwork Webhook 動作
1. Chatwork にヒートマップ画像が投稿される
2. Webhook が画像ファイルをダウンロード
3. Claude Vision API で自動分析
4. サマリーメッセージ + CSV ファイルを Chatwork に返信

## ワークフロー

### A. ローカル分析（CLI）
1. `python -m src.cli analyze page_01.png page_02.png ...`
2. Claude Vision API が画像を分析 → JSON生成
3. heatmap_analysis.py が JSON を基に Excel 生成
4. `output/` にレポート出力

### B. Chatwork 自動分析（Webhook / Watch）
1. Chatwork にヒートマップ画像を投稿
2. Webhook or Watch がファイルを検出・ダウンロード
3. Claude Vision API で分析
4. CSV + サマリーを Chatwork に自動返信

### C. 手動分析（従来方式）
1. `heatmap_analysis.py` の config と blocks を手動で書き換え
2. `python heatmap_analysis.py` を実行
3. `output/` に Excel が生成される

## Claude Vision API 分析仕様

### 入力
- ヒートマップスクリーンショット（PNG/JPG）をbase64エンコードして送信
- 複数ページの画像を一度に送信可能

### 出力（JSON）
```json
{
  "page_name": "LP名",
  "version": "v1",
  "period": "分析期間",
  "cv_users": 810,
  "click_users": 2407,
  "exit_users": 4793,
  "findings": ["発見1", "発見2", "発見3"],
  "blocks": [
    {
      "name": "ブロック名",
      "position": "0-5%",
      "cv_dwell": 4,
      "click_dwell": 3,
      "exit_dwell": 2,
      "cum_exit": 12,
      "click_resp": "△",
      "cv_resp": "×",
      "memo": "分析メモ",
      "action": "★ 施策案"
    }
  ]
}
```

## Excel出力仕様

### Sheet1: ブロック別分析
列: No / ブロック名 / 位置 / CV滞在 / CLICK滞在 / 離脱滞在 / 滞在総合 / 根拠 / 累計離脱% / 区間離脱% / 離脱リスク / Click反応 / CV反応 / 関心度 / 改善優先度 / 分析メモ / 施策案

### Sheet2: サマリー
- 最大の発見（3列比較のインサイト）
- 3列の滞在パターン比較表
- TOP改善アクション

### Sheet3: 離脱カーブ
位置×累計離脱%×残留率×区間離脱%

### Sheet4: スコア算出ロジック

## スコア算出

### 滞在時間（5段階）
- 5=🔴長い（赤）, 4=🟠やや長（オレンジ）, 3=🟡普通（黄）, 2=🟢やや短（黄緑）, 1=🔵短い（緑〜青）

### 滞在（総合）= 人数加重平均
```
総合 = CV滞在×(CV人数/全体) + CLICK滞在×(CLICK人数/全体) + 離脱滞在×(離脱人数/全体)
```
人数不明時のデフォルト：CV=13%, CLICK=30%, 離脱=57%

### 関心度
```
関心度 = CV滞在×0.2 + CLICK滞在×0.2 + クリック反応×0.3 + CV反応×0.3
```
反応スコア: ◎=3, ○=2, △=1, ×=0

### 改善優先度
- 🔴最優先：区間離脱4%+ or 離脱高×関心低
- 🟡要改善：区間離脱2-3% or ばらつきあり
- 🟢維持：離脱低×関心高

## スタイル定数
```python
dwell_fills = {5:'FF3B30', 4:'FF9500', 3:'FFCC00', 2:'A8D5BA', 1:'5AC8FA'}
exit_fills = {'4+':'C0392B', '3':'E74C3C', '2':'F39C12', '0-1':'27AE60'}
priority_fills = {'🔴':'FFCCCC', '🟡':'FFF3CD', '🟢':'D4EDDA'}
interest_fills = {'2.5+':'1B5E20', '2.0+':'4CAF50', '1.5+':'FFC107', '<1.5':'FF5722'}
```

## セル見切れ防止（必須）
全セルにwrap_text=True。行高さは日本語文字幅（×1.8）を考慮して自動計算。
必ず auto_row_heights() を全シートに適用すること。

## 分析メモの書き方
- 3列の色の違いを具体的に記述
- ユーザー数を引用（例：「離脱した4,700人には響いていない」）
- 施策案は★マークで優先度を示す
