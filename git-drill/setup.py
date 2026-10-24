#!/usr/bin/env python3
"""Собирает учебный репозиторий git-drill-work рядом с набором claude-code-kit.

Запуск из папки launch-kit:
    python3 ../claude-code-kit/git-drill/setup.py
Повторная сборка (старая папка переименовывается, ничего не удаляется):
    python3 ../claude-code-kit/git-drill/setup.py --fresh
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent
TARGET = KIT_DIR.parent.parent / "git-drill-work"
STATE_NAME = "kit-drill.json"
BASE_DATE = "2026-05-14T{:02d}:00:00+03:00"

PEOPLE = {
    "nikita": ("Никита", "nikita@example.invalid"),
    "olya": ("Оля", "olya@example.invalid"),
    "kit": ("launch-kit (учебная история)", "kit@example.invalid"),
}

README = """# git-drill-work

Учебная копия страницы статуса запуска для практики «Ветка, конфликт и откат».
Задание — в уроке курса. Здесь можно ошибаться: launch-kit не затронут.

Проверка, из этой папки:

    python3 ../claude-code-kit/git-drill/checks/check_git_drill.py
"""

TASKS = """task,owner,due,status,note
Дизайн первого экрана,Аня,2026-05-13,готово,
Финальный текст первого экрана,,2026-05-19,в работе,
Юридические формулировки,Марина,2026-05-15,в работе,
CSV с рекламными каналами,Никита,2026-05-14,не начато,
Настройка A/B-теста,Аня,2026-05-19,блокер,ждёт финальный текст
Аналитика событий,Никита,2026-05-12,готово,
"""

SUBTITLE_BASE = '<p class="subtitle">Лендинг сервиса еженедельных отчётов · запуск 20 мая</p>'
SUBTITLE_OLYA = '<p class="subtitle">Лендинг «Отчёт за 5 минут» · запуск 20 мая</p>'
SUBTITLE_DATE = '<p class="subtitle">Лендинг сервиса еженедельных отчётов · запуск 22 мая</p>'
VERDICT_BASE = '<p class="verdict">Запуск под риском</p>'
VERDICT_BAD = '<p class="verdict">Запуск по плану</p>'
FOOTER_BASE = '<p class="note">Пример: учебные данные на 15 мая.</p>'
FOOTER_DATE = FOOTER_BASE + '\n<p class="updated">Обновлено 15 мая в 10:00</p>'

STATUS = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Статус запуска</title>
</head>
<body>
<header>
<h1>Статус запуска</h1>
{subtitle}
</header>

<main>
{verdict}

<section>
<h2>Блокеры и просрочки</h2>
<ul>
<li>Настройка A/B-теста — Аня — блокер: ждёт финальный текст</li>
<li>CSV с рекламными каналами — Никита — просрочено</li>
</ul>
</section>

<section>
<h2>В работе</h2>
<ul>
<li>Финальный текст первого экрана — ответственный не назначен</li>
<li>Юридические формулировки — Марина</li>
</ul>
</section>

<section>
<h2>Готово</h2>
<ul>
<li>Дизайн первого экрана — Аня</li>
<li>Аналитика событий — Никита</li>
</ul>
</section>

<p class="total">Всего задач: 6</p>
</main>

<footer>
{footer}
</footer>
</body>
</html>
"""


def status(subtitle=SUBTITLE_BASE, verdict=VERDICT_BASE, footer=FOOTER_BASE):
    return STATUS.format(subtitle=subtitle, verdict=verdict, footer=footer)


def fail(msg):
    print(msg)
    sys.exit(2)


def git(*args, author=None, date=None):
    env = dict(os.environ)
    if author:
        name, email = PEOPLE[author]
        kit_name, kit_email = PEOPLE["kit"]
        env.update(
            GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=date,
            GIT_COMMITTER_NAME=kit_name, GIT_COMMITTER_EMAIL=kit_email,
            GIT_COMMITTER_DATE=date,
        )
    res = subprocess.run(["git", "-C", str(TARGET), *args], env=env,
                         capture_output=True, text=True)
    if res.returncode != 0:
        fail(f"Команда git {' '.join(args)} не выполнилась:\n{res.stderr.strip()}")
    return res.stdout.strip()


def write(name, text):
    with open(TARGET / name, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def commit(message, author, hour):
    git("add", "-A")
    git("-c", "commit.gpgsign=false", "commit", "--no-verify", "-q", "-m", message,
        author=author, date=BASE_DATE.format(hour))
    return git("rev-parse", "HEAD")


def main():
    if shutil.which("git") is None:
        fail("Git не найден. Установите инструменты разработчика: xcode-select --install")
    if sys.version_info < (3, 9):
        fail("Нужен Python 3.9 или новее: python3 --version")
    if TARGET.exists():
        if "--fresh" not in sys.argv:
            fail(f"Папка {TARGET} уже есть. Продолжайте в ней или запустите setup.py --fresh: "
                 "старая папка будет переименована, а не удалена.")
        n = 1
        while (TARGET.parent / f"git-drill-work-old-{n}").exists():
            n += 1
        TARGET.rename(TARGET.parent / f"git-drill-work-old-{n}")
        print(f"Старая папка переименована в git-drill-work-old-{n}.")

    TARGET.mkdir()
    git("init", "-q")
    git("symbolic-ref", "HEAD", "refs/heads/main")
    # Подпись студента для его собственных коммитов, если глобальной нет.
    probe = subprocess.run(["git", "-C", str(TARGET), "config", "user.name"],
                           capture_output=True, text=True)
    if not probe.stdout.strip():
        git("config", "user.name", "Студент launch-kit")
        git("config", "user.email", "student@example.invalid")

    state = {}
    write("README.md", README)
    write("tasks.csv", TASKS)
    state["c1"] = commit("Задачи запуска на 15 мая", "nikita", 10)

    write("status.html", status())
    state["c2"] = commit("Страница статуса: первая версия", "olya", 11)

    git("branch", "copy-ola")
    git("switch", "-q", "copy-ola")
    write("status.html", status(subtitle=SUBTITLE_OLYA))
    state["o1"] = commit("Подзаголовок: название сервиса из текста первого экрана", "olya", 12)

    git("switch", "-q", "main")
    write("status.html", status(verdict=VERDICT_BAD))
    state["c3"] = commit("Обновить вывод страницы", "nikita", 13)

    write("status.html", status(subtitle=SUBTITLE_DATE, verdict=VERDICT_BAD))
    state["c4"] = commit("Перенести запуск на 22 мая", "nikita", 14)

    write("status.html", status(subtitle=SUBTITLE_DATE, verdict=VERDICT_BAD, footer=FOOTER_DATE))
    state["c5"] = commit("Дата обновления в подвале", "olya", 15)

    (TARGET / ".git" / STATE_NAME).write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"Готово: {TARGET}")
    print("Ветки: main (5 коммитов) и copy-ola (1 коммит от второго).")
    print("Откройте новую сессию Claude Code в папке git-drill-work.")


if __name__ == "__main__":
    main()
