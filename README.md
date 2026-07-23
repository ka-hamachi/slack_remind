# Slack タスクリマインダー Bot

Slackチャンネルの会話からタスクを自動検出し、毎日14:00（JST）に未完了タスクを通知します。

---

## セットアップ手順

### 1. Slack App を作成する

1. https://api.slack.com/apps にアクセス → **Create New App** → **From scratch**
2. App名（例: `TaskReminder`）とワークスペースを選択
3. 左メニュー **OAuth & Permissions** → **Bot Token Scopes** に以下を追加:
   - `channels:history` （チャンネルメッセージ読み取り）
   - `groups:history` （プライベートチャンネルの場合）
   - `chat:write` （メッセージ送信）
   - `users:read` （ユーザー名取得）
4. **Install to Workspace** → **Bot User OAuth Token** をコピー（`xoxb-...`）
5. 対象チャンネルにBotをInvite: チャンネルで `/invite @TaskReminder`

### 2. チャンネルIDの確認

Slackでチャンネルを右クリック → **チャンネル詳細を表示** → 一番下にIDが表示される（`C` で始まる）

### 3. Anthropic API Key を取得

https://console.anthropic.com/ でAPIキーを作成

### 4. ローカルでテスト

```bash
cp .env.example .env
# .env を編集して各値を設定

pip install -r requirements.txt
python main.py
```

---

## Railway でのデプロイ（PCオフでも動作）

### 1. GitHubにリポジトリを作成してpush

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/あなた/slack-remind.git
git push -u origin main
```

### 2. Railway にデプロイ

1. https://railway.app にアクセス → GitHubでログイン
2. **New Project** → **Deploy from GitHub repo** → このリポジトリを選択
3. 左メニュー **Variables** に以下を追加:
   ```
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_CHANNEL_ID=C...
   SLACK_NOTIFY_CHANNEL_ID=C...
   ANTHROPIC_API_KEY=sk-ant-...
   DAYS_BACK=60
   ```
4. **Settings** → **Deploy** → Cron Schedule が `0 5 * * *` になっていることを確認
   - これは UTC 05:00 = JST 14:00 に相当

---

## 動作の仕組み

- 毎日14:00（JST）に起動
- 過去60日分のメッセージをSlack APIで取得
- Claude が会話の中からタスクブロックを識別
- `~テキスト~`（取り消し線）がないタスク = 未完了と判定
- 担当者ごとに通知メッセージを生成して送信

## 通知の例

```
高山さん、以下のタスクが未完了です。
　①オフライン店舗を作る
　②ガチャガチャの開発と設置
　③海外で売れるように

亀井さん、以下のタスクが未完了です。
　①台本作成
```

## タスク完了のマーク方法

Slackでタスクのテキストを選択 → 書式設定 → **取り消し線（S）** をクリック

例: `~①オフライン店舗を作る~` → 完了済みと判定される
