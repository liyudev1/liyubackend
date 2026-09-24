from environ import Env
import requests

env = Env()

Env.read_env()

TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")


def send_telegram_message(message: str,CHAT_ID):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, data=payload)
    if response.status_code != 200:
        print(f"Failed to send message: {response.text}")
    return response.json()
