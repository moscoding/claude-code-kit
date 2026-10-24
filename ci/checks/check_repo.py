#!/usr/bin/env python3
"""Проверки набора для launch-kit. Запускаются в CI и локально из корня launch-kit:

    python3 ../claude-code-kit/ci/checks/check_repo.py

Скрипт ничего не меняет в папке: страницу пересобирает во временной копии.
"""
import fnmatch
import hashlib
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

KIT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KIT_ROOT / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

ACCEPTANCE = "tests/test_status_date.py"
ORIGINAL = KIT_ROOT / "ci" / "kit-files" / ACCEPTANCE
MARKER = re.compile(r"^(<{7}|={7}|>{7}|\|{7})( |$)", re.M)
SECRET_PATTERNS = (".env", ".env.*", "*.pem", "*.key", "id_rsa*", "*.p12")
SECRET_ALLOWED = {".env.example"}

check = Check("Проверки набора для launch-kit")
root = pathlib.Path.cwd()
ctx = {}


def norm_hash(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@check.before
def _setup():
    res = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True)
    if res.returncode != 0:
        raise Stop("Это не Git-репозиторий. Запускайте проверку из корня launch-kit.")
    if not (root / "scripts" / "build_status.py").is_file():
        raise Stop("Нет scripts/build_status.py. Запускайте проверку из корня launch-kit.")
    ctx["tracked"] = [p for p in res.stdout.decode("utf-8", "replace").split("\0") if p]


@check.criterion("Маркеры конфликта")
def _markers():
    found = []
    for f in ctx["tracked"]:
        p = root / f
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        data = p.read_bytes()
        if b"\0" in data[:4096]:
            continue
        text = data.decode("utf-8", "replace")
        m = MARKER.search(text)
        if m:
            found.append(f"{f}:{text[:m.start()].count(chr(10)) + 1}")
    return Result(not found, pass_="Маркеров конфликта нет",
                  fail=f"Маркеры конфликта: {', '.join(found[:5])}",
                  hint="разберите конфликт до конца и закоммитьте файл без маркеров.")


@check.criterion("Секреты")
def _secrets():
    leaked = [f for f in ctx["tracked"] if pathlib.Path(f).name not in SECRET_ALLOWED
              and any(fnmatch.fnmatch(pathlib.Path(f).name, p) for p in SECRET_PATTERNS)]
    return Result(not leaked, pass_="В репозитории нет файлов с секретами",
                  fail=f"Файлы, похожие на секреты: {', '.join(leaked)}",
                  hint="уберите их из Git (git rm --cached), добавьте в .gitignore и отзовите ключи.")


@check.criterion("Страница пересобрана")
def _page():
    page = root / "outputs" / "status.html"
    if not page.is_file():
        return Result(False, fail="Нет outputs/status.html",
                      hint="запустите python3 scripts/build_status.py и закоммитьте страницу.")
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp) / "launch-kit"
        shutil.copytree(root, work, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "venv"))
        run = subprocess.run([sys.executable, "scripts/build_status.py"], cwd=work,
                             capture_output=True, text=True, timeout=120)
        if run.returncode != 0:
            last = (run.stderr.strip().splitlines() or ["без сообщения"])[-1]
            return Result(False, fail=f"scripts/build_status.py завершается с ошибкой: {last}",
                          hint="запустите скрипт локально и прочитайте последнюю строку traceback.")
        rebuilt = work / "outputs" / "status.html"
        same = rebuilt.is_file() and rebuilt.read_bytes() == page.read_bytes()
    return Result(same, pass_="outputs/status.html совпадает с результатом build_status.py",
                  fail="outputs/status.html не совпадает с результатом build_status.py",
                  hint="страницу меняют через скрипт или данные: запустите python3 "
                       "scripts/build_status.py и закоммитьте outputs/status.html.")


@check.criterion("Приёмочный тест")
def _acceptance():
    acc = root / ACCEPTANCE
    if not acc.is_file():
        return Result(True, pass_="Приёмочного теста задачи о дате пока нет, сравнивать нечего")
    if not ORIGINAL.is_file():
        raise Stop("В наборе нет оригинала теста. Обновите набор: git -C ../claude-code-kit pull")
    return Result(norm_hash(acc) == norm_hash(ORIGINAL),
                  pass_=f"{ACCEPTANCE} совпадает с файлом набора",
                  fail=f"{ACCEPTANCE} изменён",
                  hint="приёмочный тест не правят, чтобы он прошёл: верните его из набора "
                       "и чините scripts/build_status.py.")


if __name__ == "__main__":
    check.run()
