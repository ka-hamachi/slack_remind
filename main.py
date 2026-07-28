import os
import re
import json
import logging
from datetime import datetime, timedelta
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import anthropic
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

slack = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

CHANNEL_ID = os.environ["SLACK_CHANNEL_ID"]
NOTIFY_CHANNEL_ID = os.environ.get("SLACK_NOTIFY_CHANNEL_ID", CHANNEL_ID)
DAYS_BACK = int(os.environ.get("DAYS_BACK") or "60")


def fetch_messages():
    oldest = (datetime.now() - timedelta(days=DAYS_BACK)).timestamp()
    messages = []
    cursor = None
    while True:
        resp = slack.conversations_history(
            channel=CHANNEL_ID,
            oldest=str(oldest),
            cursor=cursor,
            limit=200,
        )
        messages.extend(resp["messages"])
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    log.info(f"Fetched {len(messages)} messages")
    return messages


def resolve_user_names(messages):
    """Slack の user ID → 表示名 に変換する"""
    user_ids = {m["user"] for m in messages if m.get("user")}
    id_to_name = {}
    for uid in user_ids:
        try:
            info = slack.users_info(user=uid)
            profile = info["user"]["profile"]
            name = profile.get("display_name") or profile.get("real_name") or uid
            id_to_name[uid] = name
        except SlackApiError:
            id_to_name[uid] = uid
    return id_to_name


def build_text_for_analysis(messages, id_to_name):
    lines = []
    for msg in reversed(messages):
        if msg.get("type") != "message" or not msg.get("text"):
            continue
        if msg.get("subtype") == "bot_message" or msg.get("bot_id"):
            continue
        name = id_to_name.get(msg.get("user", ""), "不明")
        lines.append(f"【{name}】\n{msg['text']}")
    return "\n\n---\n\n".join(lines)


SYSTEM_PROMPT = """\
あなたはSlackチャンネルの会話からタスクを抽出するアシスタントです。
"""

USER_PROMPT_TEMPLATE = """\
以下はSlackチャンネルの会話ログです（古い順）。
タスク管理の投稿と通常の会話が混在しています。

【タスク投稿の特徴】
- 「〇〇タスク」「〇〇撮影」のようなヘッダーを持つ
- ①②③ などの番号付きリスト形式
- 担当者名が明示されている
- 取り消し線（~テキスト~ ）が付いているタスクは完了済み

【あなたがすること】
1. タスクが記載されたメッセージを特定する（通常の雑談・質問は無視）
2. 同じ人のタスクリストが複数回登場する場合は「最新のもの」を使う
3. 取り消し線のないタスクのみ「未完了」として抽出する
4. 取り消し線の判定: ~テキスト~ 形式（チルダで囲まれている）= 完了済み
5. ①②③…の番号付きタスクは番号順にすべて漏れなく抽出する
6. タスクへのコメント・メモ（→以降の文章）はタスク名に含めない
7. 「〇〇さん、以下のタスクが未完了です」のようなリマインド通知文は無視する

必ずJSONのみを返してください（説明文は不要）:
{{
  "persons": [
    {{
      "name": "担当者名（さん不要）",
      "incomplete_tasks": ["①タスク名の簡潔な説明", "②タスク名の簡潔な説明"]
    }}
  ]
}}

タスクが全くない場合: {{"persons": []}}

--- 会話ログ ---
{text}
"""


def analyze_with_claude(text):
    prompt = USER_PROMPT_TEMPLATE.format(text=text)
    resp = ai.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    log.info(f"Claude response: {raw[:300]}")
    # JSON部分だけ抽出
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        log.warning("JSON not found in Claude response")
        return {"persons": []}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        log.error(f"JSON parse error: {e}")
        return {"persons": []}


def build_notification(task_data):
    parts = []
    for person in task_data.get("persons", []):
        tasks = person.get("incomplete_tasks", [])
        if not tasks:
            continue
        task_lines = "\n".join(f"　{t}" for t in tasks)
        parts.append(f"*{person['name']}さん*、以下のタスクが未完了です。\n{task_lines}")
    return "\n\n".join(parts)


def send_notification(text):
    if not text:
        log.info("No incomplete tasks found. Nothing to notify.")
        return
    slack.chat_postMessage(
        channel=NOTIFY_CHANNEL_ID,
        text=text,
        mrkdwn=True,
    )
    log.info("Notification sent.")


def run():
    log.info("Starting daily task check...")
    messages = fetch_messages()
    if not messages:
        log.info("No messages found.")
        return
    id_to_name = resolve_user_names(messages)
    text = build_text_for_analysis(messages, id_to_name)
    task_data = analyze_with_claude(text)
    notification = build_notification(task_data)
    send_notification(notification)
    log.info("Done.")


if __name__ == "__main__":
    run()
