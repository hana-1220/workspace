"""
Discord DM送信スクリプト
使い方: python3 discord_dm_send.py "メッセージ1" "メッセージ2" ...
または: パイプで入力 echo "メッセージ" | python3 discord_dm_send.py
"""
import json
import os
import subprocess
import sys
import time

BOT_TOKEN = os.environ.get("DISCORD_DM_BOT_TOKEN", "")
USER_ID = os.environ.get("DISCORD_DM_USER_ID", "")
BASE_URL = "https://discord.com/api/v10"


def send_dm(messages):
    # Create DM channel
    result = subprocess.run(
        ["curl", "-s", "-H", f"Authorization: Bot {BOT_TOKEN}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"recipient_id": USER_ID}),
         f"{BASE_URL}/users/@me/channels"],
        capture_output=True, text=True
    )
    dm = json.loads(result.stdout)
    channel_id = dm.get("id")
    if not channel_id:
        print(f"Failed to create DM channel: {dm}")
        return False

    url = f"{BASE_URL}/channels/{channel_id}/messages"
    for i, msg in enumerate(messages, 1):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"content": msg}, f, ensure_ascii=False)
            tmpfile = f.name

        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "-H", f"Authorization: Bot {BOT_TOKEN}",
             "-H", "Content-Type: application/json",
             "-d", f"@{tmpfile}", url],
            capture_output=True, text=True
        )
        os.unlink(tmpfile)
        status = result.stdout.strip()
        print(f"Sent {i}/{len(messages)}: {status}")
        if status != "200":
            print(f"  Error sending message {i}")
        if i < len(messages):
            time.sleep(1.5)

    return True


if __name__ == "__main__":
    if len(sys.argv) > 1:
        messages = sys.argv[1:]
    elif not sys.stdin.isatty():
        messages = [line.strip() for line in sys.stdin if line.strip()]
    else:
        print("Usage: python3 discord_dm_send.py 'message1' 'message2' ...")
        sys.exit(1)

    send_dm(messages)
