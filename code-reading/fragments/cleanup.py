# Фрагмент B. Учебный файл курса «Основы Claude Code»: только для чтения.
raise SystemExit("Учебный фрагмент для чтения. Не запускайте его.")

import time
from pathlib import Path

MAX_AGE_DAYS = 30
cutoff = time.time() - MAX_AGE_DAYS * 24 * 3600

for path in Path(".").glob("**/*.csv"):
    if path.stat().st_mtime < cutoff:
        path.unlink()
        print("Удалён старый файл:", path)
