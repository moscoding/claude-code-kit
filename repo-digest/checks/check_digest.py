#!/usr/bin/env python3
"""Проверка практики «Ежедневный дайджест репозитория» (модуль 14).

Запуск из папки digest-work:
    python3 ../claude-code-kit/repo-digest/checks/check_digest.py

Только читает: git log/status/rev-parse, файлы digest-work и
~/.claude/scheduled-tasks/repo-digest/SKILL.md. Эталонные числа — в checks/expected/digest.json.
"""
import json
import pathlib
import re
import subprocess
import sys

KIT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KIT / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

EXPECTED = json.loads((pathlib.Path(__file__).resolve().parent / "expected" / "digest.json").read_text(encoding="utf-8"))
ROOT = pathlib.Path.cwd()
DIGEST = ROOT / "digest" / "2026-05-14.md"
RUN = ROOT / "digest" / "run.json"
PROMPT = ROOT / "digest-prompt.md"
TASK = pathlib.Path.home() / ".claude" / "scheduled-tasks" / "repo-digest" / "SKILL.md"
SINCE = "--since=2026-05-14T00:00:00+03:00"
UNTIL = "--until=2026-05-14T23:59:59+03:00"
BOT = "dependabot[bot]"
SECTIONS = ["Коммиты", "PR", "Бот", "Задачи"]


def git(*args):
    res = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        raise Stop("Git не отвечает в этой папке. Запустите проверку из папки digest-work.")
    return res.stdout


def day_commits():
    rows = []
    for line in git("log", "main", SINCE, UNTIL, "--format=%h%x09%H%x09%an%x09%P%x09%s").splitlines():
        short, full, author, parents, subject = line.split("\t", 4)
        rows.append({"short": short, "full": full, "author": author,
                     "merge": len(parents.split()) > 1, "subject": subject})
    return rows


def sections(text):
    out, current = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            current = m.group(1)
            out[current] = []
        elif current:
            out[current].append(line)
    return out


def total(lines):
    for line in lines:
        m = re.match(r"^\s*Всего:\s*(\d+)\s*$", line)
        if m:
            return int(m.group(1))
    return None


def load_run():
    try:
        return json.loads(RUN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


check = Check("Проверка практики «Ежедневный дайджест репозитория»")
STATE = {}


@check.before
def _():
    if not (ROOT / ".git" / "kit-digest.json").exists():
        raise Stop("Это не папка digest-work. Перейдите в неё (cd ../digest-work) или соберите её:",
                   "python3 ../claude-code-kit/repo-digest/setup.py")
    rows = day_commits()
    if len(rows) != EXPECTED["day_total"]:
        raise Stop("История digest-work изменилась: за 14 мая другое число коммитов.",
                   "Соберите репозиторий заново: python3 ../claude-code-kit/repo-digest/setup.py --fresh")
    STATE["rows"] = rows
    STATE["text"] = DIGEST.read_text(encoding="utf-8") if DIGEST.exists() else ""
    STATE["sec"] = sections(STATE["text"])
    STATE["run"] = load_run()


@check.criterion("история")
def _():
    head = json.loads((ROOT / ".git" / "kit-digest.json").read_text(encoding="utf-8"))["head"]
    changed = [l for l in git("status", "--porcelain").splitlines() if not l.startswith("??")]
    ok = git("rev-parse", "HEAD").strip() == head and not changed
    return Result(ok, pass_="История и отслеживаемые файлы не изменились",
                  fail="В репозитории новый коммит или правки в отслеживаемых файлах",
                  hint="инструкция запрещает коммитить и менять файлы; посмотрите git status и git log -3.")


@check.criterion("инструкция")
def _():
    text = PROMPT.read_text(encoding="utf-8") if PROMPT.exists() else ""
    ok = all(s in text for s in ("digest/2026-05-14.md", "Критерий успеха", "ОСТАНОВКА"))
    return Result(ok, pass_="digest-prompt.md с критерием успеха и правилом остановки",
                  fail="Нет digest-prompt.md или в нём нет критерия успеха и правила остановки",
                  hint="шаг ❸: файл создают из текста урока дословно.")


@check.criterion("разделы")
def _():
    ok = bool(STATE["text"]) and list(STATE["sec"].keys())[:4] == SECTIONS
    return Result(ok, pass_="digest/2026-05-14.md с разделами Коммиты, PR, Бот, Задачи",
                  fail="Нет digest/2026-05-14.md или разделы не те и не в том порядке",
                  hint="формат — в digest-prompt.md: заголовки «## Коммиты», «## PR», «## Бот», «## Задачи».")


@check.criterion("коммиты")
def _():
    lines = STATE["sec"].get("Коммиты", [])
    body = "\n".join(lines)
    people = [r for r in STATE["rows"] if not r["merge"] and r["author"] != BOT]
    others = [r for r in STATE["rows"] if r not in people]
    listed = all(re.search(r"\b%s" % r["short"][:7], body) for r in people)
    clean = not any(re.search(r"\b%s" % r["short"][:7], body) for r in others)
    wip = git("rev-parse", "--short=7", "anya/wip-colors").strip()
    ok = total(lines) == EXPECTED["people"] and listed and clean and wip not in body
    return Result(ok, pass_="«Коммиты»: число и список коммитов людей совпадают с историей main",
                  fail="«Коммиты»: число или список не совпадают с историей main",
                  hint="в раздел не входят merge-коммиты, коммиты dependabot[bot] и коммиты неслитых веток.")


@check.criterion("pr")
def _():
    lines = STATE["sec"].get("PR", [])
    nums = set(re.findall(r"#(\d+)", "\n".join(lines)))
    ok = total(lines) == len(EXPECTED["prs"]) and nums == {str(n) for n in EXPECTED["prs"]}
    return Result(ok, pass_="«PR»: слитые за день PR совпадают",
                  fail="«PR»: число или номера PR не совпадают",
                  hint="PR за день — merge-коммиты «Merge pull request #N» с датой 14 мая.")


@check.criterion("бот")
def _():
    ok = total(STATE["sec"].get("Бот", [])) == EXPECTED["bot"]
    return Result(ok, pass_="«Бот»: число коммитов dependabot[bot] совпадает",
                  fail="«Бот»: число не совпадает", hint="считают коммиты автора dependabot[bot] в main за 14 мая.")


@check.criterion("задачи")
def _():
    body = "\n".join(STATE["sec"].get("Задачи", []))
    m = re.search(r"Открытых:\s*(\d+).*?bug:\s*(\d+).*?дольше 7 дней:\s*(\d+)", body, re.S)
    ok = bool(m) and [int(x) for x in m.groups()] == EXPECTED["issues"]
    return Result(ok, pass_="«Задачи»: открытые, bug и без исполнителя совпадают с inputs/issues.json",
                  fail="«Задачи»: числа не совпадают с inputs/issues.json или строка не в заданном виде",
                  hint="считают только открытые задачи; «дольше 7 дней» — без assignees и созданные раньше 2026-05-08.")


@check.criterion("run.json")
def _():
    run = STATE["run"]
    ok = isinstance(run, dict) and run.get("type") == "result"
    return Result(ok, pass_="digest/run.json — итог запуска claude -p в JSON",
                  fail="Нет digest/run.json или это не итог запуска с --output-format json",
                  hint="шаг ❹: вывод запуска перенаправляют в digest/run.json.")


@check.criterion("исход")
def _():
    run = STATE["run"] or {}
    ok = run.get("subtype") == "success" and run.get("is_error") is False
    return Result(ok, pass_="Запуск завершился успешно: subtype success, is_error false",
                  fail=f"Запуск не успешен: subtype {run.get('subtype')!r}",
                  hint="прочитайте errors и permission_denials в run.json, поправьте инструкцию и запустите снова.")


@check.criterion("бюджет")
def _():
    run = STATE["run"] or {}
    turns, cost = run.get("num_turns"), run.get("total_cost_usd")
    stopped = run.get("subtype") in ("error_max_turns", "error_max_budget_usd")  # остановлен лимитом
    ok = isinstance(turns, int) and turns <= EXPECTED["max_turns"] and isinstance(cost, (int, float)) \
        and cost <= EXPECTED["max_budget_usd"] and not stopped
    return Result(ok, pass_="Запуск уложился в 12 ходов и 0,50 $ по оценке",
                  fail="Запуск вышел за 12 ходов или 0,50 $, или в run.json нет этих полей",
                  hint="запускайте ровно командой из шага ❹: с --max-turns 12 и --max-budget-usd 0.50.")


@check.criterion("задача Desktop")
def _():
    text = TASK.read_text(encoding="utf-8") if TASK.exists() else ""
    ok = "digest-prompt.md" in text
    return Result(ok, pass_="Локальная задача repo-digest сохранена и ссылается на digest-prompt.md",
                  fail="Локальная задача repo-digest не найдена или не ссылается на digest-prompt.md",
                  hint="шаг ❻: Name — repo-digest, в Instructions — файл digest-prompt.md.")


if __name__ == "__main__":
    check.run()
