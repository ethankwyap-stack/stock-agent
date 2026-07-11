"""Send a message via Telegram bot API."""
import os
import requests


def send(text):
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/sendMessage"
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    for i in range(0, len(text), 4000):  # Telegram caps messages at 4096 chars
        r = requests.post(url, json={"chat_id": chat_id, "text": text[i:i + 4000]},
                          timeout=30)
        r.raise_for_status()
