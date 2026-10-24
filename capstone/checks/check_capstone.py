#!/usr/bin/env python3
"""Проверка кэпстоун-проекта (модуль 19).

Запуск из корня followup-kit после слияния PR и git pull:
    python3 ../claude-code-kit/capstone/checks/check_capstone.py
Своя задача вместо учебной:
    python3 ../claude-code-kit/capstone/checks/check_capstone.py --own

Скрипт читает ветку main: файлы и историю — через git, тесты и скрипт проверки
запускает во временной копии main (git archive), GitHub — через gh
(auth status, repo view, pr list). git fetch обновляет только сведения о
состоянии GitHub. Скрипт ничего не меняет, не коммитит и не пушит, содержимое
найденных секретов не печатает.
"""
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

KIT_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBE = pathlib.Path(__file__).resolve().parent / "probe"
sys.path.insert(0, str(KIT_ROOT / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

OWN = "--own" in sys.argv
STUDY_SCRIPT = "scripts/check_followup.py"
STUDY_INPUTS = ["inputs/notes.md", "inputs/notes-hard.md", "inputs/notes-repeat.md"]
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
SAFE_EMAIL = re.compile(r"@(?:[A-Za-z0-9-]+\.)*example\.(?:com|org|net)$|@users\.noreply\.github\.com$", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)")
TOKEN = re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
                   r"|xox[abp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----")
ENV_FILE = re.compile(r"(^|/)\.env(\.[^/]+)?$")

check = Check("Проверка кэпстоун-проекта" + (" (своя задача)" if OWN else ""))
ctx = {}


def run(cmd, cwd=None, timeout=120, env=None):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 124, "", str(exc))


def git(*args, timeout=60):
    res = run(["git", "-C", str(ctx["repo"]), *args], timeout=timeout)
    return res.stdout if res.returncode == 0 else None


def show(path):
    return git("show", f"{ctx['main']}:{path}")


def first_add(*pathspecs):
    out = git("log", ctx["main"], "--diff-filter=A", "--reverse", "--format=%H", "--", *pathspecs) or ""
    lines = out.split()
    return lines[0] if lines else None


def earlier(a, b):
    if not a or not b or a == b:
        return False
    return run(["git", "-C", str(ctx["repo"]), "merge-base", "--is-ancestor", a, b]).returncode == 0


def subject(sha):
    return (git("log", "-1", "--format=%h «%s»", sha) or sha[:7]).strip()


def gh_json(*args):
    res = run(["gh", *args], timeout=90)
    if res.returncode != 0:
        return None
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return None


def files_in(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts)


def run_script(notes, result):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    res = run([sys.executable, ctx["script"], str(notes), str(result)], cwd=ctx["tmp"], timeout=60, env=env)
    return res.returncode, (res.stdout or "") + (res.stderr or "")


@check.before
def _setup():
    top = run(["git", "rev-parse", "--show-toplevel"])
    if top.returncode != 0:
        raise Stop("Здесь нет Git-репозитория. Запускайте проверку из корня followup-kit:",
                   "python3 ../claude-code-kit/capstone/checks/check_capstone.py")
    ctx["repo"] = pathlib.Path(top.stdout.strip())
    ctx["main"] = next((b for b in ("main", "master") if git("rev-parse", "-q", "--verify", b)), None)
    if not ctx["main"]:
        raise Stop("В репозитории нет ветки main. Первый коммит «Каркас и учебные данные» идёт в main.")
    main = ctx["main"]
    if git("remote", "get-url", "origin"):
        run(["git", "-C", str(ctx["repo"]), "fetch", "-q", "origin"], timeout=90)
        local, remote = git("rev-parse", main), git("rev-parse", "-q", "--verify", f"origin/{main}")
        if remote and local and local.strip() != remote.strip() and earlier(local.strip(), remote.strip()):
            raise Stop(f"На GitHub в {main} есть коммиты, которых нет у вас: PR слит, а git pull не сделан.",
                       f"Выполните git switch {main} и git pull, затем запустите проверку снова.")
    ctx["tracked"] = set((git("ls-tree", "-r", "--name-only", main) or "").splitlines())
    if not OWN and "inputs/notes.md" not in ctx["tracked"]:
        raise Stop(f"В {main} нет inputs/notes.md учебного маршрута.",
                   "Если пакет собран на своей задаче, запустите проверку с флагом --own.")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="capstone-check-"))
    ctx["tmp"] = tmp
    archive = subprocess.run(["git", "-C", str(ctx["repo"]), "archive", main], capture_output=True)
    if archive.returncode != 0:
        raise Stop(f"Не удалось прочитать ветку {main}: git archive завершился с ошибкой.")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(tmp, filter="data")
        else:
            tar.extractall(tmp)
    if OWN:
        scripts = sorted(p for p in ctx["tracked"] if re.fullmatch(r"scripts/check_[^/]+\.py", p)) or \
            sorted(p for p in ctx["tracked"] if re.fullmatch(r"scripts/[^/]+\.py", p))
        ctx["script"] = scripts[0] if scripts else None
    else:
        ctx["script"] = STUDY_SCRIPT if STUDY_SCRIPT in ctx["tracked"] else None
    ctx["tests"] = sorted(p for p in ctx["tracked"] if re.fullmatch(r"tests/(?:[^/]+/)*test[^/]*\.py", p))


@check.after
def _cleanup():
    if ctx.get("tmp"):
        shutil.rmtree(ctx["tmp"], ignore_errors=True)


@check.criterion("Каркас")
def _frame():
    missing = [f for f in ("CLAUDE.md", "brief.md", ".claude/settings.json") if f not in ctx["tracked"]]
    if missing:
        return Result(False, fail=f"В main нет: {', '.join(missing)}",
                      hint="каркас переносят из launch-kit в первом коммите «Каркас и учебные данные».")
    try:
        deny = json.loads(show(".claude/settings.json") or "{}").get("permissions", {}).get("deny", [])
    except (json.JSONDecodeError, AttributeError):
        return Result(False, fail=".claude/settings.json не читается как JSON",
                      hint="попросите Claude показать файл и исправить синтаксис.")
    rules = [r for r in deny if isinstance(r, str) and r.startswith("Edit(")]
    lacks = [d for d in ("inputs", "tests") if not any(d + "/" in r for r in rules)]
    return Result(not lacks, pass_="Каркас на месте: CLAUDE.md, бриф, запреты правок inputs/ и tests/",
                  fail="В deny файла .claude/settings.json нет запрета правок: " + ", ".join(d + "/" for d in lacks),
                  hint="правила вида Edit(/inputs/**) и Edit(/tests/**); tests/ закрывают после коммита теста.")


@check.criterion("Входы")
def _inputs():
    if not OWN:
        absent = [f for f in STUDY_INPUTS if f not in ctx["tracked"]]
        if absent:
            return Result(False, fail="В main нет учебных заметок: " + ", ".join(absent),
                          hint="три файла заметок создают в подготовке и коммитят первым коммитом.")
    commits = (git("log", ctx["main"], "--reverse", "--format=%H", "--", "inputs/") or "").split()
    if not commits:
        return Result(False, fail="В main нет папки inputs/", hint="входы лежат в inputs/ с первого коммита.")
    same = git("rev-parse", f"{commits[0]}:inputs") == git("rev-parse", f"{ctx['main']}:inputs")
    details = [f"История помнит правки входов: {len(commits) - 1}; содержимое вернулось к исходному."] \
        if same and len(commits) > 1 else []
    return Result(same, pass_=f"inputs/ в main такие же, как в коммите {subject(commits[0])}",
                  fail=f"inputs/ изменены после коммита {subject(commits[0])}",
                  hint=["входы не правят под результат. Найдите правку: git log --oneline -- inputs/,",
                        "отмените её через git revert в ветке и PR и опишите случай в review.md."],
                  details=details)


def _first_result():
    if not OWN:
        return first_add("outputs/followup.md")
    out = git("log", ctx["main"], "--diff-filter=A", "--reverse", "--name-only", "--format=@%H", "--", "outputs/") or ""
    sha = None
    for line in out.splitlines():
        if line.startswith("@"):
            sha = line[1:]
        elif line.strip() and not line.strip().endswith("review.md"):
            return sha
    return None


@check.criterion("Критерии раньше результата")
def _criteria_first():
    acc, res = first_add("work/acceptance.md"), _first_result()
    if not acc:
        return Result(False, fail="В main нет work/acceptance.md", hint="критерии приёмки — шаг ❷.")
    if not res:
        return Result(False, fail="В main нет результата в outputs/", hint="первый проход — шаг ❺.")
    return Result(earlier(acc, res),
                  pass_=f"Критерии ({subject(acc)}) закоммичены раньше результата ({subject(res)})",
                  fail="Результат появился раньше критериев приёмки или в одном коммите с ними",
                  hint="критерии коммитят отдельно и до первого прохода: иначе их подгоняют под результат.")


@check.criterion("Тест раньше скрипта")
def _test_first():
    if not ctx["tests"]:
        return Result(False, fail="В main нет тестов tests/test_*.py", hint="тест — шаг ❸, до скрипта.")
    if not ctx["script"]:
        return Result(False, fail="В main нет скрипта проверки " + ("scripts/check_*.py" if OWN else STUDY_SCRIPT),
                      hint="скрипт — шаг ❹.")
    t, s = first_add(*ctx["tests"]), first_add(ctx["script"])
    return Result(earlier(t, s), pass_=f"Тест ({subject(t)}) закоммичен раньше скрипта ({subject(s)})",
                  fail="Тест закоммичен вместе со скриптом или после него",
                  hint="тест коммитят первым, пока скрипта нет: красный прогон доказывает, что тест проверяет задачу.")


@check.criterion("Тесты зелёные")
def _tests_green():
    if not ctx["tests"]:
        return Result(False, fail="Тестов нет, запускать нечего", hint="тест — шаг ❸.")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    res = run([sys.executable, "-m", "unittest"], cwd=ctx["tmp"], timeout=180, env=env)
    out = (res.stdout or "") + (res.stderr or "")
    ran = re.findall(r"^Ran (\d+) tests?", out, re.M)
    n = int(ran[-1]) if ran else 0
    ok = res.returncode == 0 and re.search(r"^OK\b", out, re.M)
    if n == 0:
        return Result(False, fail="python3 -m unittest в main не нашёл ни одного теста",
                      hint="нужен пустой tests/__init__.py, а имена файлов тестов начинаются с test.")
    if not ok:
        return Result(False, fail=f"python3 -m unittest в main: Ran {n}, итог не OK",
                      hint="запустите python3 -m unittest -v в main и почините скрипт, а не тест.")
    return Result(n >= 3, pass_=f"python3 -m unittest в main: Ran {n} tests, OK",
                  fail=f"python3 -m unittest в main запускает {n} теста, нужно не меньше трёх",
                  hint="в тесте — случаи из критериев: прямой исполнитель, «возможно», нет в заметках, «уточнить».")


@check.criterion("Скрипт проверки")
def _script():
    if not ctx["script"]:
        return Result(False, fail="Скрипта проверки в main нет", hint="скрипт — шаг ❹.")
    if OWN:
        name = pathlib.Path(ctx["script"]).name
        used = any(name in (show(t) or "") or pathlib.Path(name).stem in (show(t) or "") for t in ctx["tests"])
        return Result(used, pass_=f"Тесты запускают {ctx['script']}",
                      fail=f"Ни один тест не обращается к {ctx['script']}",
                      hint="тест должен проверять сам скрипт проверки, а не отдельную копию правил.")
    followup = ctx["tmp"] / "outputs" / "followup.md"
    if not followup.is_file():
        return Result(False, fail="Нет outputs/followup.md, проверять скрипт не на чем", hint="первый проход — шаг ❺.")
    before = files_in(ctx["tmp"])
    code_ok, out_ok = run_script(ctx["tmp"] / "inputs" / "notes.md", followup)
    code_maybe, out_maybe = run_script(PROBE / "notes-maybe.md", followup)
    code_gone, _ = run_script(PROBE / "notes-missing.md", followup)
    clean = files_in(ctx["tmp"]) == before
    if code_ok != 0 or "OK" not in out_ok:
        return Result(False, fail="На inputs/notes.md и outputs/followup.md скрипт не печатает OK",
                      hint=f"запустите python3 {STUDY_SCRIPT} inputs/notes.md outputs/followup.md и сверьте правила.")
    if code_maybe == 0 or "Илья" not in out_maybe:
        return Result(False, fail="Скрипт пропустил владельца, названного в заметках только с «возможно»",
                      hint=["правило ловит одну формулировку, а не слово «возможно» в строке с владельцем.",
                            "Меняют его вслед за критериями: правило, отдельным коммитом тест, затем скрипт."])
    if code_gone == 0:
        return Result(False, fail="Скрипт пропустил владельца, которого нет в заметках",
                      hint="каждый владелец из итогов должен найтись в заметках как исполнитель.")
    return Result(clean, pass_="Скрипт ловит владельца из «возможно» и владельца, которого нет в заметках; файлов не пишет",
                  fail="Скрипт проверки создаёт или меняет файлы",
                  hint="скрипт только печатает OK или нарушения и выходит с кодом 0 или 1.")


@check.criterion("Результаты")
def _results():
    if OWN:
        outs = [p for p in ctx["tracked"] if p.startswith("outputs/") and not p.endswith("review.md")]
        return Result(bool(outs), pass_=f"Результаты в outputs/: {len(outs)}",
                      fail="В outputs/ нет результата", hint="результат процедуры коммитят в outputs/.")
    f, h = show("outputs/followup.md") or "", show("outputs/followup-hard.md")
    lacks = [w for w in ("Марина", "Илья", "18 июля") if w not in f]
    if lacks or "Никит" in f:
        return Result(False, fail="outputs/followup.md не сходится с заметками",
                      hint="сверьте каждый пункт с inputs/notes.md: владельцы, дата, ничего сверх заметок.")
    if h is None:
        return Result(False, fail="В main нет outputs/followup-hard.md", hint="спорное место — шаг ❻.")
    if re.search(r"владел\w*\W{0,3}\s*Никит", h, re.I) or "уточн" not in h.lower():
        return Result(False, fail="В outputs/followup-hard.md владельцем баннеров стоит не «уточнить»",
                      hint="предположение «возможно, возьмёт» не делает человека владельцем: правьте критерии и повторите проход.")
    code, _ = run_script(ctx["tmp"] / "inputs" / "notes-hard.md", ctx["tmp"] / "outputs" / "followup-hard.md")
    return Result(code == 0, pass_="Итоги по notes.md и notes-hard.md сходятся с заметками, проверка печатает OK",
                  fail="Скрипт проверки находит нарушения в outputs/followup-hard.md",
                  hint=f"запустите python3 {STUDY_SCRIPT} inputs/notes-hard.md outputs/followup-hard.md.")


@check.criterion("Разбор")
def _review():
    path = next((p for p in ("outputs/review.md", "review.md", "work/review.md") if p in ctx["tracked"]), None)
    if not path:
        return Result(False, fail="В main нет outputs/review.md", hint="разбор в четыре строки — шаг ❻.")
    text = (show(path) or "").lower()
    need = {"спорное место или сбой": ("спорн", "сбой"), "что ожидали": ("ожидал",), "что получили": ("получил",),
            "что исправили": ("исправил", "исправлен"), "какая проверка остаётся": ("проверк",)}
    lacks = [k for k, keys in need.items() if not any(x in text for x in keys)]
    return Result(not lacks, pass_=f"Разбор спорного места в {path}",
                  fail=f"В {path} не хватает частей разбора: " + ", ".join(lacks),
                  hint="четыре строки: спорное место, что ожидали и что получили, что исправили, какая проверка остаётся.")


@check.criterion("Автоматизация")
def _automation():
    script = pathlib.Path(ctx["script"] or STUDY_SCRIPT).name
    skills = sorted(p for p in ctx["tracked"] if re.fullmatch(r"\.claude/skills/[^/]+/SKILL\.md", p))
    weak = None
    for path in skills:
        text = show(path) or ""
        head = text.split("---")[1] if text.startswith("---") and text.count("---") >= 2 else ""
        if not (re.search(r"^name:\s*\S", head, re.M) and re.search(r"^description:\s*\S", head, re.M)):
            weak = weak or f"{path}: в шапке нет name или description"
            continue
        if script not in text:
            weak = weak or f"{path}: скил не запускает {script}"
            continue
        if not re.search(r"^disable-model-invocation:\s*true\b", head, re.M):
            weak = weak or f"{path}: нет disable-model-invocation: true"
            continue
        name = re.search(r"^name:\s*(\S+)", head, re.M).group(1)
        return Result(True, pass_=f"Скил /{name}: ручной вызов, запускает {script}")
    tasks = pathlib.Path.home() / ".claude" / "scheduled-tasks"
    for task in sorted(tasks.glob("*/SKILL.md")) if tasks.is_dir() else []:
        text = task.read_text(encoding="utf-8", errors="replace")
        if script in text or ctx["repo"].name in text:
            return Result(True, pass_=f"Задача по расписанию «{task.parent.name}» запускает {script}")
    return Result(False, fail=weak or "Нет ни скила в .claude/skills/, ни задачи по расписанию с этой процедурой",
                  hint=["скил: name, description, disable-model-invocation: true и запуск скрипта проверки — шаг ❼;",
                        "или локальная задача на странице Routines, чья инструкция запускает скрипт проверки."])


@check.criterion("Хэндоф и повтор")
def _handoff():
    text = show("handoff.md")
    if text is None:
        return Result(False, fail="В main нет handoff.md", hint="хэндоф — шаг ❽.")
    low = text.lower()
    if "как продолжить" not in low or not any(x in low for x in ("unittest", "check_", "/")):
        return Result(False, fail="В handoff.md нет раздела «Как продолжить» с командой проверки",
                      hint="ветка, python3 -m unittest, вызов автоматизации и где записаны решения.")
    if OWN:
        rev = (show("outputs/review.md") or show("review.md") or "").lower()
        return Result("повтор" in rev or "повтор" in low, pass_="Хэндоф с разделом «Как продолжить», малый повтор записан",
                      fail="Нигде не записан итог малого повтора", hint="ожидание и итог повтора — в review.md.")
    rep = show("outputs/repeat.md")
    return Result(rep is not None and "25 июля" in rep,
                  pass_="Хэндоф с разделом «Как продолжить»; малый повтор: в repeat.md новая дата 25 июля",
                  fail="Малого повтора нет или в outputs/repeat.md нет новой даты 25 июля",
                  hint="повтор — шаг ❾: новая сессия, хэндоф и /followup inputs/notes-repeat.md outputs/repeat.md.")


@check.criterion("PR")
def _pr():
    if shutil.which("gh") is None:
        return Result(False, fail="GitHub CLI не найден", hint="brew install gh, затем gh auth login.")
    if run(["gh", "auth", "status"]).returncode != 0:
        return Result(False, fail="GitHub CLI не вошёл в аккаунт", hint="gh auth login во встроенном терминале.")
    info = gh_json("repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef")
    if not info:
        return Result(False, fail="Репозиторий на GitHub не найден",
                      hint="gh repo create followup-kit --private --source=. --remote=origin --push — подготовка.")
    if info.get("visibility") != "PRIVATE":
        return Result(False, fail=f"Репозиторий {info['nameWithOwner']} открыт всем",
                      hint="сделайте его закрытым: Settings репозитория на GitHub, раздел Danger Zone.")
    default = (info.get("defaultBranchRef") or {}).get("name") or ctx["main"]
    prs = gh_json("pr", "list", "--state", "merged", "--limit", "100",
                  "--json", "number,body,baseRefName,files") or []
    work = [p for p in prs if p.get("baseRefName") == default and any(
        (f.get("path") or "").startswith(("outputs/", "scripts/", "tests/")) for f in p.get("files") or [])]
    if not work:
        return Result(False, fail=f"Нет слитого в {default} PR с работой кэпстоуна",
                      hint="шаг ❿: ветка followup-v1, gh pr create, ревью, gh pr merge.")
    pr = work[0]
    return Result(bool(re.search(r"проверк", pr.get("body") or "", re.I)),
                  pass_=f"PR #{pr['number']} слит в {default}, в описании есть проверка; репозиторий закрытый",
                  fail=f"В описании PR #{pr['number']} нет строки о проверке",
                  hint=f"допишите «Проверка: команды и их итог»: gh pr edit {pr['number']} --body-file <файл>.")


@check.criterion("Секреты")
def _secrets():
    env_files = sorted(p for p in ctx["tracked"] if ENV_FILE.search(p) and not p.endswith(".env.example"))
    if env_files:
        return Result(False, fail="В репозитории файл с секретами: " + ", ".join(env_files),
                      hint="удалите его из Git, добавьте в .gitignore и отзовите ключ: история его помнит.")
    found = []
    for rel in sorted(ctx["tracked"]):
        p = ctx["tmp"] / rel
        if not p.is_file() or p.stat().st_size > 1_000_000:
            continue
        text = p.read_bytes().decode("utf-8", "ignore")
        kinds = []
        if any(not SAFE_EMAIL.search(m.group(0)) for m in EMAIL.finditer(text)):
            kinds.append("email")
        if PHONE.search(text):
            kinds.append("телефон")
        if TOKEN.search(text):
            kinds.append("похоже на ключ")
        if kinds:
            found.append(f"{rel} ({', '.join(kinds)})")
    return Result(not found, pass_="Секретов и контактов в репозитории не найдено",
                  fail="Найдены данные, которым не место в пакете", details=found[:10],
                  hint="замените на мок-данные (email на example.com); ключ, попавший в коммит, отзывают.")


if __name__ == "__main__":
    check.run()
