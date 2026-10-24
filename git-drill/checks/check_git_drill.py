#!/usr/bin/env python3
"""Проверка практики «Ветка, конфликт и откат».

Запуск из папки git-drill-work:
    python3 ../claude-code-kit/git-drill/checks/check_git_drill.py
Путь к репозиторию можно передать первым аргументом.
Скрипт только читает репозиторий: ничего не меняет и не коммитит.
"""
import json
import pathlib
import re
import shutil
import subprocess
import sys

KIT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KIT_ROOT / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

STATE_NAME = "kit-drill.json"
MARKER = re.compile(r"^(<{7}|={7}|>{7}|\|{7})( |$)", re.M)
OWNER_OLD = "Финальный текст первого экрана — ответственный не назначен"
OWNER_NEW = "Финальный текст первого экрана — Оля"
ORIGINAL = ("c1", "c2", "c3", "c4", "c5")

check = Check("Проверка практики «Ветка, конфликт и откат»")
ctx = {}


def git(*args):
    res = subprocess.run(["git", "-C", str(ctx["repo"]), *args], capture_output=True, text=True)
    return res.stdout if res.returncode == 0 else None


def is_ancestor(a, b="main"):
    res = subprocess.run(["git", "-C", str(ctx["repo"]), "merge-base", "--is-ancestor", a, b],
                         capture_output=True)
    return res.returncode == 0


@check.before
def _setup():
    if shutil.which("git") is None:
        raise Stop("Git не найден. Установите инструменты разработчика: xcode-select --install")
    candidates = [pathlib.Path(a).expanduser() for a in sys.argv[1:2] if not a.startswith("-")]
    candidates += [pathlib.Path.cwd(), KIT_ROOT.parent / "git-drill-work"]
    repo = next((c.resolve() for c in candidates if (c / ".git" / STATE_NAME).is_file()), None)
    if repo is None:
        raise Stop("Учебный репозиторий не найден.",
                   "Запустите проверку из папки git-drill-work или соберите её:",
                   "python3 ../claude-code-kit/git-drill/setup.py")
    ctx["repo"] = repo
    ctx["state"] = json.loads((repo / ".git" / STATE_NAME).read_text(encoding="utf-8"))
    if git("rev-parse", "--verify", "-q", "refs/heads/main") is None:
        raise Stop("В репозитории нет ветки main. Соберите папку заново: setup.py --fresh")
    ctx["log"] = (git("rev-list", "main") or "").split()
    ctx["page"] = git("show", "main:status.html") or ""
    merges = (git("rev-list", "--merges", "--parents", "main") or "").splitlines()
    ctx["merged_ola"] = any(ctx["state"]["o1"] in line.split()[1:] for line in merges)


@check.criterion("Состояние")
def _state():
    gitdir = ctx["repo"] / ".git"
    busy = [name for name, f in (("слияние", "MERGE_HEAD"), ("откат", "REVERT_HEAD"),
                                 ("cherry-pick", "CHERRY_PICK_HEAD")) if (gitdir / f).exists()]
    if (gitdir / "rebase-merge").exists() or (gitdir / "rebase-apply").exists():
        busy.append("rebase")
    if busy:
        return Result(False, fail=f"Не завершено: {', '.join(busy)}",
                      hint="доведите операцию до коммита или отмените её: git merge --abort, git revert --abort.")
    head = (git("symbolic-ref", "-q", "--short", "HEAD") or "").strip()
    return Result(head == "main", pass_="Ветка main, слияние и откат не идут",
                  fail=f"Текущая ветка {head or '(нет ветки)'}, а не main",
                  hint="переключитесь: git switch main.")


@check.criterion("История")
def _history():
    lost = [k for k in ORIGINAL if ctx["state"][k] not in set(ctx["log"])]
    return Result(not lost, pass_="История main не переписана: исходные коммиты на месте",
                  fail="Из истории main пропали исходные коммиты",
                  hint="похоже, использовали git reset или rebase. Соберите папку заново: setup.py --fresh.")


@check.criterion("Ветка fix-owner")
def _fix_owner():
    st = ctx["state"]
    known = {st[k] for k in (*ORIGINAL, "o1")}
    owner_commit = None
    for sha in reversed(ctx["log"]):
        if sha in known:
            continue
        parents = (git("rev-list", "--parents", "-n", "1", sha) or "").split()[1:]
        if len(parents) != 1:
            continue
        lines = (git("diff", parents[0], sha, "--", "status.html") or "").splitlines()
        if any(l.startswith("-") and OWNER_OLD in l for l in lines) and \
                any(l.startswith("+") and OWNER_NEW in l for l in lines):
            owner_commit = sha
            break
    if owner_commit is None:
        return Result(False, fail="Правки ответственного в main нет",
                      hint="в ветке fix-owner замените «ответственный не назначен» на «Оля», "
                           "закоммитьте и влейте ветку в main.")
    if git("rev-parse", "--verify", "-q", "refs/heads/fix-owner") and not is_ancestor("fix-owner"):
        return Result(False, fail="Ветка fix-owner не влита в main",
                      hint="git switch main, затем git merge fix-owner.")
    branch, current = None, None
    for line in reversed((git("reflog", "show", "--format=%H %gs", "HEAD") or "").splitlines()):
        sha, _, subject = line.partition(" ")
        m = re.match(r"checkout: moving from (\S+) to (\S+)", subject)
        if m:
            current = m.group(2)
        elif sha == owner_commit and subject.startswith("commit"):
            branch = current
    if branch not in (None, "fix-owner"):
        return Result(False, fail=f"Правка ответственного закоммичена в ветке {branch}, а не в fix-owner",
                      hint="задачу начинают в своей ветке: git switch -c fix-owner. "
                           "Соберите папку заново через setup.py --fresh и повторите шаг ❷.")
    return Result(True, pass_="Правка ответственного сделана в ветке fix-owner и влита в main")


@check.criterion("Ветка copy-ola")
def _copy_ola():
    return Result(ctx["merged_ola"], pass_="Ветка copy-ola влита в main merge-коммитом",
                  fail="Ветка copy-ola не влита в main merge-коммитом",
                  hint="git merge copy-ola, разберите конфликт, затем git add status.html и git commit --no-edit.")


@check.criterion("Маркеры")
def _markers():
    found = []
    for f in dict.fromkeys(filter(None, (git("ls-files") or "").split("\n"))):
        p = ctx["repo"] / f
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            m = MARKER.search(text)
            if m:
                found.append(f"{f}:{text[:m.start()].count(chr(10)) + 1}")
    return Result(not found, pass_="Маркеров конфликта нет",
                  fail=f"Остались маркеры конфликта: {', '.join(found)}",
                  hint="удалите маркеры, оставив итоговую строку; проверьте git diff --check.")


@check.criterion("Подзаголовок")
def _subtitle():
    if not ctx["merged_ola"]:
        return Result(False, fail="Подзаголовок не проверялся: ветка copy-ola ещё не влита",
                      hint="сначала влейте copy-ola и разберите конфликт.")
    subs = re.findall(r'<p class="subtitle">(.*?)</p>', ctx["page"])
    if len(subs) != 1:
        return Result(False, fail=f"Строк подзаголовка на странице: {len(subs)}",
                      hint="подзаголовок должен остаться одной строкой; лишнюю версию удалите.")
    s = subs[0]
    if "Отчёт за 5 минут" not in s:
        return Result(False, fail="Подзаголовок потерял правку ветки copy-ola",
                      hint="сравните итог с версией copy-ola: что она меняла в строке?")
    if "22 мая" not in s or "20 мая" in s:
        return Result(False, fail="Подзаголовок потерял правку main",
                      hint="сравните итог с версией main: что изменилось в строке после ветвления?")
    return Result(True, pass_="Подзаголовок сохраняет обе правки")


@check.criterion("Revert")
def _revert():
    bad = ctx["state"]["c3"]
    reverted = any(f"This reverts commit {bad}" in (git("log", "-1", "--format=%B", sha) or "")
                   for sha in ctx["log"])
    if not reverted:
        return Result(False, fail="Коммит с неверным выводом не отменён через git revert",
                      hint="найдите коммит, после которого страница пишет «Запуск по плану», "
                           "и отмените его: git revert <хеш> --no-edit.")
    verdicts = re.findall(r'<p class="verdict">(.*?)</p>', ctx["page"])
    return Result(verdicts == ["Запуск под риском"],
                  pass_="Коммит с неверным выводом отменён через git revert",
                  fail="Revert есть, но вывод на странице не «Запуск под риском»",
                  hint="сравните вывод с данными: блокер A/B-теста ещё открыт.")


@check.criterion("Рабочая папка")
def _clean():
    if (git("status", "--porcelain") or "").strip():
        return Result(False, fail="В рабочей папке есть незакоммиченные изменения",
                      hint="посмотрите git status: закоммитьте нужное или верните файл через git restore.")
    return Result(True, pass_="Рабочая папка чистая")


if __name__ == "__main__":
    check.run()
