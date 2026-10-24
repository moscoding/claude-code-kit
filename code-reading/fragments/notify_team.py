# Фрагмент D. Учебный файл курса «Основы Claude Code»: только для чтения.
raise SystemExit("Учебный фрагмент для чтения. Не запускайте его.")

import json
import urllib.request

BOT_TOKEN = "tok_live_EXAMPLE_4f9c2a7d1b"
CHAT = "launch-team"

def notify(text):
    body = json.dumps({"chat": CHAT, "text": text}).encode()
    url = "https://chat.example/api/send?token=" + BOT_TOKEN
    urllib.request.urlopen(urllib.request.Request(url, data=body))

notify("Недельная сводка готова")
