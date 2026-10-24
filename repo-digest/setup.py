#!/usr/bin/env python3
"""Собирает учебный репозиторий digest-work рядом с набором claude-code-kit.

Практика модуля 15 «Ежедневный дайджест репозитория». Устроен как git-drill/setup.py:
история фиксирована, даты +03:00, хеши коммитов одинаковы на любой машине.

Запуск из папки launch-kit:
    python3 ../claude-code-kit/repo-digest/setup.py
Повторная сборка (старая папка переименовывается, ничего не удаляется):
    python3 ../claude-code-kit/repo-digest/setup.py --fresh
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent
TARGET = KIT_DIR.parent.parent / "digest-work"
STATE_NAME = "kit-digest.json"

PEOPLE = {
    "nikita": ("Никита", "nikita@example.invalid"),
    "olya": ("Оля", "olya@example.invalid"),
    "anya": ("Аня", "anya@example.invalid"),
    "marina": ("Марина", "marina@example.invalid"),
    "bot": ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com"),
    "kit": ("launch-kit (учебная история)", "kit@example.invalid"),
}

README = """# digest-work

Учебная копия репозитория для практики «Ежедневный дайджест репозитория».
Задание — в уроке курса. Здесь можно ошибаться: launch-kit не затронут.

Проверка, из этой папки:

    python3 ../claude-code-kit/repo-digest/checks/check_digest.py
"""

# (день, время, автор, подпись, ветка или None для main). Ветки создаются от текущей main.
# Все времена +03:00. Merge-коммиты описаны отдельно.
HISTORY = [
    ("2026-05-12", "10:00", "kit", "Учебный репозиторий: README и папка дайджестов", None),
    ("2026-05-12", "15:00", "nikita", "Задачи запуска на 12 мая", None),
    # 13 мая: 9 коммитов в main (8 обычных + merge #6)
    ("2026-05-13", "10:10", "olya", "Текст первого экрана: черновик", None),
    ("2026-05-13", "10:40", "nikita", "Выгрузка каналов за неделю", None),
    ("2026-05-13", "11:20", "anya", "Дизайн первого экрана", None),
    ("2026-05-13", "12:00", "marina", "Юридические формулировки: черновик", None),
    ("2026-05-13", "12:45", "nikita", "fix: дата в подвале страницы", None),
    ("2026-05-13", "13:30", "nikita", "Недельная сводка по каналам", "nikita/report-weeks"),
    ("MERGE", "2026-05-13", "14:10", "olya", 6, "nikita/report-weeks", "Недельная сводка по каналам"),
    ("2026-05-13", "15:00", "olya", "Подзаголовок страницы статуса", None),
    ("2026-05-13", "16:30", "anya", "Цвета блоков страницы", None),
    # 14 мая: 14 коммитов в main = 9 людей + 2 бота + 3 merge
    ("2026-05-14", "11:05", "marina", "Юридические формулировки в подвале", None),
    ("2026-05-14", "11:20", "bot", "Bump actions/setup-python from 5 to 6", None),
    ("2026-05-14", "11:30", "olya", "Текст первого экрана: финальная версия", "olya/first-screen-text"),
    ("2026-05-14", "11:45", "anya", "Макет блока тарифов", "anya/pricing-block"),
    ("2026-05-14", "12:00", "nikita", "fix: CPL считать только при лидах больше нуля", "nikita/cpl-fix"),
    ("2026-05-14", "12:15", "nikita", "Отчёт: колонка CPL в недельной сводке", None),
    ("2026-05-14", "12:30", "olya", "fix: опечатка в заголовке страницы статуса", None),
    ("2026-05-14", "12:45", "bot", "Bump actions/checkout from 5 to 6", None),
    ("REVERT", "2026-05-14", "13:00", "nikita", "revert: Отчёт: колонка CPL в недельной сводке"),
    ("2026-05-14", "13:15", "anya", "Иконки каналов в легенде графика", None),
    ("2026-05-14", "13:30", "olya", "README: как пересобрать страницу", None),
    ("MERGE", "2026-05-14", "13:45", "nikita", 7, "olya/first-screen-text", "Текст первого экрана"),
    ("MERGE", "2026-05-14", "14:00", "olya", 8, "anya/pricing-block", "Блок тарифов на первом экране"),
    ("MERGE", "2026-05-14", "14:15", "anya", 10, "nikita/cpl-fix", "CPL без деления на ноль"),
    # Ловушка: коммит 14 мая в неслитой ветке
    ("2026-05-14", "15:10", "anya", "WIP: новые цвета блоков", "anya/wip-colors"),
    # 15 мая: снимок задач и статус. Не раньше 11:00 +03:00, чтобы и подсчёт без пояса в датах
    # давал 14 коммитов за 14 мая от UTC−8 (Лос-Анджелес) до UTC+10 (Владивосток).
    ("ISSUES", "2026-05-15", "11:30", "kit", "Снимок задач на 15 мая"),
    ("2026-05-15", "12:10", "nikita", "Статус на 15 мая", None),
]


def fail(msg):
    print(msg)
    sys.exit(2)


def git(*args, who=None, when=None):
    env = dict(os.environ)
    if who:
        name, email = PEOPLE[who]
        kit_name, kit_email = PEOPLE["kit"]
        env.update(GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=when,
                   GIT_COMMITTER_NAME=kit_name, GIT_COMMITTER_EMAIL=kit_email,
                   GIT_COMMITTER_DATE=when)
    res = subprocess.run(["git", "-C", str(TARGET), *args], env=env, capture_output=True, text=True)
    if res.returncode != 0:
        fail(f"Команда git {' '.join(args)} не выполнилась:\n{res.stderr.strip()}")
    return res.stdout.strip()


def stamp(day, hm):
    return f"{day}T{hm}:00+03:00"


def note_file(subject):
    slug = "".join(ch if ch.isalnum() else "-" for ch in subject.lower()).strip("-")
    return TARGET / "notes" / f"{slug[:48]}.md"


def commit(day, hm, who, subject):
    git("add", "-A")
    git("-c", "commit.gpgsign=false", "commit", "--no-verify", "-q", "-m", subject,
        who=who, when=stamp(day, hm))
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
        while (TARGET.parent / f"digest-work-old-{n}").exists():
            n += 1
        TARGET.rename(TARGET.parent / f"digest-work-old-{n}")
        print(f"Старая папка переименована в digest-work-old-{n}.")

    TARGET.mkdir()
    (TARGET / "notes").mkdir()
    (TARGET / "digest").mkdir()
    (TARGET / "inputs").mkdir()
    git("init", "-q")
    git("symbolic-ref", "HEAD", "refs/heads/main")
    probe = subprocess.run(["git", "-C", str(TARGET), "config", "user.name"], capture_output=True, text=True)
    if not probe.stdout.strip():
        git("config", "user.name", "Студент launch-kit")
        git("config", "user.email", "student@example.invalid")

    (TARGET / "README.md").write_text(README, encoding="utf-8")
    (TARGET / "digest" / ".gitkeep").write_text("", encoding="utf-8")
    cpl_sha = None
    for item in HISTORY:
        if item[0] == "MERGE":
            _, day, hm, who, num, branch, title = item
            msg = f"Merge pull request #{num} from {branch}\n\n{title}"
            git("-c", "commit.gpgsign=false", "-c", "merge.log=false", "merge", "--no-ff", "--no-verify", "-q",
                "-m", msg, branch,
                who=who, when=stamp(day, hm))
            continue
        if item[0] == "REVERT":
            _, day, hm, who, subject = item
            git("revert", "--no-commit", cpl_sha)
            commit(day, hm, who, subject)
            continue
        if item[0] == "ISSUES":
            _, day, hm, who, subject = item
            shutil.copy(KIT_DIR / "inputs" / "issues.json", TARGET / "inputs" / "issues.json")
            commit(day, hm, who, subject)
            continue
        day, hm, who, subject, branch = item
        if branch:
            git("switch", "-q", "-c", branch)
        note_file(subject).write_text(f"{subject}\n", encoding="utf-8")
        sha = commit(day, hm, who, subject)
        if subject.startswith("Отчёт: колонка CPL"):
            cpl_sha = sha
        if branch:
            git("switch", "-q", "main")

    state = {"head": git("rev-parse", "HEAD")}
    (TARGET / ".git" / STATE_NAME).write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"Готово: {TARGET}")
    print("Откройте новую сессию Claude Code в папке digest-work.")


if __name__ == "__main__":
    main()
