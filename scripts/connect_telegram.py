"""Utility script to capture Telegram chat ID and link with DarkestMindsbot."""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

TOKEN = "8916057660:AAGdkNPLkgs7oPTOPsI92IgzwEi16D__U54"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

print("Listening for incoming message on @DarkestMindsbot...")
print("Open Telegram and send /start or 'hi' to @DarkestMindsbot!")

url_updates = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

for attempt in range(300):
    try:
        req = urllib.request.Request(url_updates)
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
            results = data.get("result", [])
            if results:
                # Get the latest message
                last_msg = results[-1].get("message", {}) or results[-1].get("my_chat_member", {})
                chat = last_msg.get("chat", {})
                chat_id = chat.get("id")
                first_name = chat.get("first_name", "Creator")
                if chat_id:
                    print(f"FOUND USER: {first_name} (ID: {chat_id})")

                    # Update .env
                    if ENV_PATH.exists():
                        content = ENV_PATH.read_text(encoding="utf-8")
                        new_content = re.sub(
                            r"TELEGRAM_ALLOWED_USER_IDS=.*",
                            f"TELEGRAM_ALLOWED_USER_IDS={chat_id}",
                            content,
                        )
                        ENV_PATH.write_text(new_content, encoding="utf-8")
                        print(f"Updated .env with TELEGRAM_ALLOWED_USER_IDS={chat_id}")

                    # Send welcome message
                    msg_text = (
                        f"🚀 *Darkest Minds 101 Control Room Connected!*\n\n"
                        f"Welcome, {first_name}! Your autonomous YouTube agent is now officially linked to your Telegram.\n\n"
                        f"• You will receive instant notifications with direct YouTube links whenever a new Short is published.\n"
                        f"• Try sending `/status` or `/latest` right here anytime!"
                    )
                    send_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
                    send_payload = json.dumps({
                        "chat_id": chat_id,
                        "text": msg_text,
                        "parse_mode": "Markdown",
                    }).encode("utf-8")
                    send_req = urllib.request.Request(send_url, data=send_payload, headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(send_req, timeout=5)
                    print("Welcome notification sent successfully!")
                    sys.exit(0)
    except Exception as e:
        print(f"Polling check error: {e}")
    time.sleep(2)

print("Timeout waiting for message. You can re-run this script anytime.")
