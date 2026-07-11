"""Send a message via Telegram bot API."""
import os
import re
import requests


def send(text):
    # tokens/ids never contain whitespace — strip paste-mangled spaces/newlines
    token = re.sub(r"\s+", "", os.environ["TELEGRAM_TOKEN"])
    chat_id = re.sub(r"\s+", "", os.environ["TELEGRAM_CHAT_ID"])
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for i in range(0, len(text), 4000):  # Telegram caps messages at 4096 chars
        r = requests.post(url, json={"chat_id": chat_id, "text": text[i:i + 4000]},
                          timeout=30)
        r.raise_for_status()
