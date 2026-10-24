#!/usr/bin/env python3
"""Собирает учебный репозиторий leaked-key-drill рядом с набором claude-code-kit.

Урок «Секреты и мок-данные», модуль 15. В истории пять коммитов: ключ из .env попал
в третий и «удалён» пятым. Ключ учебный и нигде не действует.

Запуск из папки launch-kit:
    python3 ../claude-code-kit/security-drills/leaked-key/setup.py
Повторная сборка (старая папка переименовывается, ничего не удаляется):
    python3 ../claude-code-kit/security-drills/leaked-key/setup.py --fresh
Для приёмки: --target <папка> собирает репозиторий в указанном месте.
"""
import os
import subprocess
import sys
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent
DEFAULT_TARGET = KIT_DIR.parents[2] / "leaked-key-drill"
AUTHOR = ("Никита", "nikita@example.invalid")
MOCK_KEY = "ads_live_TEST_9f3K2mQ7xL"  # учебный, нигде не действует

README = """# leaked-key-drill

Учебный репозиторий для урока «Секреты и мок-данные». Ключ в истории учебный.
Задание — в уроке курса.
"""

REPORT_PY = '''"""Недельный отчёт по каналам: читает inputs/ads.csv, пишет outputs/report.md."""
import csv
from pathlib import Path

rows = list(csv.DictReader(open("inputs/ads.csv", encoding="utf-8")))
total = sum(int(r["spend"]) for r in rows)
Path("outputs").mkdir(exist_ok=True)
Path("outputs/report.md").write_text(f"Расход за неделю: {total} ₽\\n", encoding="utf-8")
'''

ADS_CSV = "channel,spend\nsearch,17400\nsocial,9800\n"

FETCH_PY = '''"""Скачивает выгрузку из рекламного кабинета. Ключ берёт из переменной окружения."""
import os

API_KEY = os.environ["ADS_API_KEY"]
print("Выгрузка: учебная заглушка, запрос не отправляется.")
'''

ENV_EXAMPLE = "ADS_API_KEY=\n"
ENV_FILE = f"ADS_API_KEY={MOCK_KEY}\n"
REPORT_MD = "Расход за неделю: 27200 ₽\n"
GITIGNORE = ".env\n__pycache__/\n"

# (подпись, дата, {путь: содержимое или None для удаления})
COMMITS = [
    ("Первая версия отчёта", "2026-05-11T10:00:00+03:00",
     {"README.md": README, "scripts/report.py": REPORT_PY, "inputs/ads.csv": ADS_CSV}),
    ("Выгрузка из рекламного кабинета", "2026-05-12T11:00:00+03:00",
     {"scripts/fetch_ads.py": FETCH_PY, ".env.example": ENV_EXAMPLE}),
    ("Настройки для запуска", "2026-05-12T16:30:00+03:00",
     {".env": ENV_FILE}),
    ("Отчёт за неделю 11 мая", "2026-05-13T09:15:00+03:00",
     {"outputs/report.md": REPORT_MD}),
    ("Убрал .env из репозитория", "2026-05-14T12:00:00+03:00",
     {".env": None, ".gitignore": GITIGNORE}),
]


def git(target, *args, date=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "XDG_CONFIG_HOME"}
    env.update({
        "GIT_AUTHOR_NAME": AUTHOR[0], "GIT_AUTHOR_EMAIL": AUTHOR[1],
        "GIT_COMMITTER_NAME": AUTHOR[0], "GIT_COMMITTER_EMAIL": AUTHOR[1],
        "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(target),  # чужие глобальные настройки git не влияют
    })
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", str(target), "-c", "commit.gpgsign=false", *args], check=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def main():
    args = sys.argv[1:]
    target = DEFAULT_TARGET
    if "--target" in args:
        target = Path(args[args.index("--target") + 1]).resolve()
    if target.exists():
        if "--fresh" not in args:
            print(f"Папка {target.name} уже есть. Чтобы собрать заново, добавьте --fresh.")
            sys.exit(2)
        n = 1
        while target.with_name(f"{target.name}-old{n}").exists():
            n += 1
        target.rename(target.with_name(f"{target.name}-old{n}"))
    target.mkdir(parents=True)
    git(target, "init", "-q", "-b", "main")
    for message, date, files in COMMITS:
        for rel, content in files.items():
            path = target / rel
            if content is None:
                git(target, "rm", "-q", rel)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            git(target, "add", rel)
        git(target, "commit", "-q", "-m", message, date=date)
    print(f"Готово: ../{target.name}, коммитов: {len(COMMITS)}.")


if __name__ == "__main__":
    main()
