"""Проверка практики «Три бага в недельном отчёте».

Запуск из папки launch-kit:
    python3 ../claude-code-kit/buggy-report/checks/check_bugs.py

Критерии:
1. учебные данные и файлы тестов совпадают с набором (хеш);
2. в .claude/settings.json есть правило deny на правку tests/;
3. python3 -m unittest проходит: все тесты зелёные, ни один не пропущен;
4. после версии Никиты изменён только scripts/report.py;
5–10. скрытые случаи из checks/expected/hidden_cases.json.

Только стандартная библиотека. Эталон не печатается.
"""
import csv
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT.parent / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

PROJECT = Path.cwd()
PROTECTED = ["tests/test_report.py", "tests/__init__.py", "inputs/campaigns-weeks.csv"]
ALLOWED_CHANGES = {"scripts/report.py", "outputs/weekly-summary.csv",
                   ".claude/settings.local.json"}
DENY_RULES = {"Edit(/tests/**)", "Edit(tests/**)", "Edit(./tests/**)"}
MIN_TESTS = 7

check = Check("Проверка практики «Три бага в недельном отчёте»")
state = {}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=PROJECT, capture_output=True,
                          text=True)


def blob_hash(path):
    return git("hash-object", str(path)).stdout.strip()


@check.before
def _():
    if not (PROJECT / ".git").exists():
        raise Stop("Не найден Git-репозиторий в текущей папке.",
                   "Запускайте проверку из корня launch-kit.")
    missing = [p for p in ["scripts/report.py"] + PROTECTED
               if not (PROJECT / p).exists()]
    if missing:
        raise Stop("Нет файлов: " + ", ".join(missing) + ".",
                   "Скопируйте их из ../claude-code-kit/buggy-report/ по шагу ❷ практики.")


@check.criterion("protected")
def _():
    changed = [p for p in PROTECTED if sha256(PROJECT / p) != sha256(KIT / p)]
    return Result(not changed,
                  pass_="Тесты и учебные данные совпадают с набором",
                  fail="Изменены защищённые файлы: " + ", ".join(changed),
                  hint=["в задаче «почини код» тесты и данные не меняются.",
                        "Верните их командой git checkout -- <файл> и чините scripts/report.py."])


@check.criterion("deny")
def _():
    path = PROJECT / ".claude" / "settings.json"
    rules = []
    if path.exists():
        try:
            rules = json.loads(path.read_text(encoding="utf-8")) \
                .get("permissions", {}).get("deny", [])
        except (ValueError, AttributeError):
            rules = []
    ok = any(rule.replace(" ", "") in DENY_RULES for rule in rules)
    return Result(ok,
                  pass_="Правило deny закрывает tests/ от правок Claude",
                  fail="В .claude/settings.json нет правила deny для tests/",
                  hint="добавьте в permissions.deny строку \"Edit(/tests/**)\" (шаг ❷).")


@check.criterion("unittest")
def _():
    run = subprocess.run([sys.executable, "-m", "unittest"], cwd=PROJECT,
                         capture_output=True, text=True, timeout=120)
    out = run.stdout + run.stderr
    found = re.search(r"Ran (\d+) tests?", out)
    ran = int(found.group(1)) if found else 0
    skipped = re.search(r"skipped=\d+|expected failures=\d+", out)
    ok = run.returncode == 0 and ran >= MIN_TESTS and not skipped
    if ran < MIN_TESTS:
        hint = (f"запустилось тестов: {ran}, а должно быть не меньше {MIN_TESTS}. "
                "Проверьте, что tests/__init__.py на месте и команда идёт из корня launch-kit.")
    elif skipped:
        hint = "часть тестов пропущена или помечена как ожидаемо падающая: так зелёный цвет ничего не доказывает."
    else:
        last = [line for line in out.strip().splitlines() if line.strip()][-1:]
        hint = ["прочитайте блоки FAIL и ERROR в выводе python3 -m unittest: имя теста и строку AssertionError.",
                "Последняя строка вывода: " + (last[0] if last else "пусто")]
    return Result(ok,
                  pass_=f"python3 -m unittest: тестов {ran}, все зелёные",
                  fail="python3 -m unittest не проходит",
                  hint=hint)


def find_baseline():
    """Последний коммит, где scripts/report.py совпадает с версией Никиты."""
    nikita = blob_hash(KIT / "scripts" / "report.py")
    log = git("log", "--format=%H", "--", "scripts/report.py").stdout.split()
    for commit in log:
        if git("rev-parse", f"{commit}:scripts/report.py").stdout.strip() == nikita:
            return commit
    return None


@check.criterion("scope")
def _():
    base = find_baseline()
    if not base:
        return Result(False,
                      fail="Не найден коммит с версией Никиты",
                      hint="закоммитьте скопированные файлы до правок (шаг ❷), чтобы дифф было с чем сравнить.")
    changed = set(git("diff", "--name-only", base).stdout.split())
    changed |= set(git("ls-files", "--others", "--exclude-standard").stdout.split())
    changed = {p for p in changed
               if "__pycache__" not in p and not p.endswith((".pyc", ".DS_Store"))}
    extra = sorted(changed - ALLOWED_CHANGES)
    touched = "scripts/report.py" in changed
    ok = touched and not extra
    if extra:
        hint = ["после версии Никиты изменены лишние файлы: " + ", ".join(extra) + ".",
                "Задача — правка только scripts/report.py. Лишнее верните через git checkout или git restore."]
    else:
        hint = "scripts/report.py не изменён: баги ещё на месте."
    return Result(ok,
                  pass_="После версии Никиты изменён только scripts/report.py",
                  fail="Дифф выходит за scripts/report.py" if extra else "Исправлений нет",
                  hint=hint)


def load_student_module():
    if "module" not in state:
        spec = importlib.util.spec_from_file_location(
            "student_report", PROJECT / "scripts" / "report.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        state["module"] = module
    return state["module"]


def make_row(day, channel, spend, clicks, leads, revenue):
    return {"date": day, "source": "check", "campaign": "check",
            "channel": channel, "spend": spend, "clicks": str(clicks),
            "leads": str(leads), "revenue": str(revenue),
            "sessions": "0", "notes": ""}


def same(actual, expected):
    if expected is None:
        return actual is None
    if actual is None:
        return False
    try:
        return abs(float(actual) - float(expected)) < 0.005
    except (TypeError, ValueError):
        return actual == expected


def run_case(case):
    m = load_student_module()
    if case["kind"] == "in_week":
        got = m.in_week(date.fromisoformat(case["day"]),
                        date.fromisoformat(case["start"]))
        return bool(got) == case["expect"]
    if case["kind"] == "summarize_week":
        rows = [make_row(*r) for r in case["rows"]]
        summary = m.summarize_week(rows, date.fromisoformat(case["start"]))
        by_channel = {item["channel"]: item for item in summary}
        if set(by_channel) != set(case["expect"]):
            return False
        for channel, fields in case["expect"].items():
            item = by_channel[channel]
            for key, value in fields.items():
                if key == "note_nonempty":
                    if bool(str(item.get("note") or "").strip()) != value:
                        return False
                elif not same(item.get(key), value):
                    return False
        return True
    if case["kind"] == "run_script":
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "scripts").mkdir()
            (tmp / "inputs").mkdir()
            shutil.copy(PROJECT / "scripts" / "report.py", tmp / "scripts" / "report.py")
            shutil.copy(KIT / "inputs" / "campaigns-weeks.csv", tmp / "inputs" / "campaigns-weeks.csv")
            run = subprocess.run([sys.executable, "scripts/report.py"], cwd=tmp,
                                 capture_output=True, text=True, timeout=60)
            out = tmp / "outputs" / "weekly-summary.csv"
            if run.returncode != 0 or not out.exists():
                return False
            with open(out, encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
        if len(rows) != case["expect_rows"]:
            return False
        index = {(r.get("week"), r.get("channel")): r for r in rows}
        for week, channel, column, value in case["expect_cells"]:
            cell = (index.get((week, channel)) or {}).get(column)
            if cell is None:
                return False
            if value == "":
                if cell.strip() != "":
                    return False
            elif not same(cell, value):
                return False
        return True
    raise ValueError("неизвестный вид случая " + case["kind"])


CASES = json.loads((KIT / "checks" / "expected" / "hidden_cases.json")
                   .read_text(encoding="utf-8"))["cases"]


def register(case):
    @check.criterion(case["id"])
    def _():
        try:
            ok = run_case(case)
        except Exception as exc:  # падение скрипта студента — непройденный случай
            return Result(False,
                          fail=f"Скрытый случай {case['id']}: {case['title']} — скрипт упал",
                          hint=[case["hint"], f"Ошибка: {exc.__class__.__name__}: {exc}"])
        return Result(ok,
                      pass_=f"Скрытый случай {case['id']}: {case['title']}",
                      fail=f"Скрытый случай {case['id']}: {case['title']}",
                      hint=case["hint"])


for item in CASES:
    register(item)

if __name__ == "__main__":
    check.run()
