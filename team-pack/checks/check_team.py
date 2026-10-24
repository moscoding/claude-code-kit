#!/usr/bin/env python3
"""Проверка практики «Командный пакет» (модуль 16).

Запуск из папки launch-kit:
    python3 ../claude-code-kit/team-pack/checks/check_team.py
Путь к проекту можно передать первым аргументом.
Скрипт только читает проект: ничего не меняет и не коммитит.
"""
import csv
import hashlib
import io
import json
import pathlib
import re
import shutil
import subprocess
import sys

KIT_ROOT = pathlib.Path(__file__).resolve().parents[2]
PACK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT_ROOT / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

MEMOS = ["memo-%d" % i for i in range(1, 6)]
SKILL_DIR = ".claude/skills/legal-wording"
SHARED = [
    "CLAUDE.md",
    "CHECKLIST.md",
    ".claude/settings.json",
    SKILL_DIR + "/SKILL.md",
    SKILL_DIR + "/legal-rules.md",
    "work/legal-verdicts.csv",
] + ["inputs/memos/%s.md" % m for m in MEMOS]
SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                    r"(?i:api[_-]?key|password|token)\s*[:=]\s*\S{8,})")
ITEM = re.compile(r"^\s*(?:[-*]\s+\[[ xX]\]|[-*]|\d+[.)])\s+(\S.*)$")
SCALE = re.compile(r"(?i)по\s+шкале|от\s*1\s*до\s*(5|10)|\b[1-5]\s*[–-]\s*(5|10)\b|из\s+(5|10)\b|/\s*(5|10)\b")

check = Check("Проверка практики «Командный пакет»")
ctx = {}


def git(*args):
    res = subprocess.run(["git", "-C", str(ctx["repo"]), *args], capture_output=True, text=True)
    return res.stdout if res.returncode == 0 else None


def tracked(path):
    return bool((git("ls-files", "--", path) or "").strip())


def ignored(path):
    res = subprocess.run(["git", "-C", str(ctx["repo"]), "check-ignore", "-q", "--no-index", path],
                         capture_output=True)
    return res.returncode == 0


def read(rel):
    p = ctx["repo"] / rel
    return p.read_text(encoding="utf-8") if p.is_file() else None


def norm(text):
    return (text or "").strip().lower().replace("ё", "е").strip("«»\"' .")


def frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text or "", re.S)
    if not m:
        return None, text or ""
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip("\"'")
    return fields, (text or "")[m.end():]


@check.before
def _setup():
    if shutil.which("git") is None:
        raise Stop("Git не найден. Установите инструменты разработчика: xcode-select --install")
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    repo = pathlib.Path(args[0]).expanduser().resolve() if args else pathlib.Path.cwd()
    if not (repo / ".git").exists() or not (repo / "CLAUDE.md").exists():
        raise Stop("Проект launch-kit не найден.",
                   "Запустите проверку из папки launch-kit:",
                   "python3 ../claude-code-kit/team-pack/checks/check_team.py")
    ctx["repo"] = repo
    ctx["expected"] = json.loads((PACK / "checks" / "expected" / "team.json").read_text(encoding="utf-8"))


@check.criterion("CLAUDE.md")
def _claude_md():
    text = read("CLAUDE.md") or ""
    lines = text.count("\n") + 1
    if lines > 200:
        return Result(False, fail="CLAUDE.md длиннее 200 строк: %d" % lines,
                      hint="перенесите разовые детали в бриф или хэндоф, длинные процедуры — в скилы.")
    missing = [w for w in ("python3 -m unittest", "legal-wording") if w not in text]
    if missing:
        return Result(False, fail="В CLAUDE.md не хватает: %s" % ", ".join(missing),
                      hint="добавьте разделы «Команды» и «Скилы» из шага ❷.")
    return Result(True, pass_="CLAUDE.md: команды и скилы на месте, %d строк" % lines)


@check.criterion("CLAUDE.local.md")
def _local_md():
    if read("CLAUDE.local.md") is None:
        return Result(False, fail="Нет CLAUDE.local.md",
                      hint="перенесите в него свои личные строки из CLAUDE.md (шаги ❶–❷).")
    if tracked("CLAUDE.local.md"):
        return Result(False, fail="CLAUDE.local.md лежит в Git",
                      hint="уберите его из индекса: git rm --cached CLAUDE.local.md, и добавьте в .gitignore.")
    if not ignored("CLAUDE.local.md"):
        return Result(False, fail="CLAUDE.local.md не закрыт в .gitignore",
                      hint="добавьте строку CLAUDE.local.md в .gitignore.")
    return Result(True, pass_="CLAUDE.local.md есть и не попадает в Git")


@check.criterion("Настройки")
def _settings():
    raw = read(".claude/settings.json")
    if raw is None:
        return Result(False, fail="Нет .claude/settings.json", hint="он появился в модуле 13: верните его из Git.")
    try:
        shared = json.loads(raw)
    except ValueError as exc:
        return Result(False, fail="В .claude/settings.json ошибка JSON: %s" % exc,
                      hint="попросите Claude показать файл и исправить синтаксис.")
    if "model" in shared:
        return Result(False, fail="В .claude/settings.json задана модель",
                      hint="модель — личный выбор: перенесите ключ model в .claude/settings.local.json.")
    local_raw = read(".claude/settings.local.json")
    if local_raw is None:
        return Result(False, fail="Нет .claude/settings.local.json",
                      hint="запишите в него свой выбор модели (шаг ❷).")
    try:
        local = json.loads(local_raw)
    except ValueError as exc:
        return Result(False, fail="В .claude/settings.local.json ошибка JSON: %s" % exc,
                      hint="попросите Claude показать файл и исправить синтаксис.")
    if tracked(".claude/settings.local.json"):
        return Result(False, fail=".claude/settings.local.json лежит в Git",
                      hint="git rm --cached .claude/settings.local.json и закоммитьте.")
    if not ignored(".claude/settings.local.json"):
        return Result(False, fail=".claude/settings.local.json не закрыт в .gitignore",
                      hint="добавьте строку .claude/settings.local.json в .gitignore: так его не закоммитят случайно.")
    if "model" not in local:
        return Result(False, fail="В .claude/settings.local.json нет ключа model",
                      hint="запишите туда свой выбор модели, например \"model\": \"opus\".")
    return Result(True, pass_="Настройки: модель в личном файле, общий без неё")


@check.criterion("Ворктри")
def _worktrees():
    ok = ignored(".claude/worktrees/x/README.md")
    return Result(ok, pass_=".gitignore закрывает .claude/worktrees/",
                  fail=".claude/worktrees/ не закрыта в .gitignore",
                  hint="добавьте строку .claude/worktrees/ в .gitignore.")


@check.criterion("Скил")
def _skill():
    text = read(SKILL_DIR + "/SKILL.md")
    if text is None:
        return Result(False, fail="Нет %s/SKILL.md" % SKILL_DIR, hint="соберите скил по шагу ❸.")
    fields, body = frontmatter(text)
    if fields is None:
        return Result(False, fail="У SKILL.md нет шапки между строками ---",
                      hint="шапка в начале файла: name и description.")
    if fields.get("name") != "legal-wording":
        return Result(False, fail="В шапке SKILL.md name не legal-wording",
                      hint="имя скила совпадает с именем его папки.")
    if len(fields.get("description", "")) < 40:
        return Result(False, fail="Описание скила слишком короткое",
                      hint="в description: что делает, когда использовать, чего не делает.")
    if "legal-rules.md" not in body:
        return Result(False, fail="SKILL.md не ссылается на legal-rules.md",
                      hint="первый шаг скила — прочитать ${CLAUDE_SKILL_DIR}/legal-rules.md.")
    kit_rules = (PACK / "practice" / "legal-rules.md").read_bytes()
    rules = ctx["repo"] / SKILL_DIR / "legal-rules.md"
    if not rules.is_file() or rules.read_bytes() != kit_rules:
        return Result(False, fail="legal-rules.md в скиле отличается от правил Марины",
                      hint="скопируйте файл из набора без изменений: правила меняет только оунер.")
    return Result(True, pass_="Скил legal-wording: шапка на месте, правила Марины без изменений")


@check.criterion("Чеклист")
def _checklist():
    text = read("CHECKLIST.md")
    if text is None:
        return Result(False, fail="Нет CHECKLIST.md", hint="напишите чеклист по шагу ❹.")
    items = [m.group(1) for m in map(ITEM.match, text.splitlines()) if m]
    if not 5 <= len(items) <= 7:
        return Result(False, fail="Пунктов в CHECKLIST.md: %d" % len(items),
                      hint="нужно от 5 до 7 пунктов списком.")
    no_q = [i for i in items if "?" not in i]
    if no_q:
        return Result(False, fail="Не все пункты — вопросы «да/нет»: %d без знака вопроса" % len(no_q),
                      hint="каждый пункт — вопрос, на который отвечают «да» или «нет».")
    if SCALE.search(text):
        return Result(False, fail="В CHECKLIST.md есть оценка по шкале",
                      hint="замените оценку вопросами «да/нет».")
    if not any("срок" in i.lower() for i in items):
        return Result(False, fail="В чеклисте нет вопроса об обещании сроков",
                      hint="обязательный вопрос Марины должен быть и в чеклисте.")
    return Result(True, pass_="Чеклист: %d вопросов «да/нет», есть вопрос о сроках" % len(items))


@check.criterion("Git")
def _committed():
    missing = [p for p in SHARED if not tracked(p)]
    if missing:
        return Result(False, fail="Не закоммичены: %s" % ", ".join(missing),
                      hint="закоммитьте общие файлы и сделайте git pull после шага ❻.")
    dirty = (git("status", "--porcelain", "--", *SHARED) or "").strip()
    if dirty:
        return Result(False, fail="Есть незакоммиченные правки в общих файлах",
                      hint="посмотрите git status и закоммитьте их.")
    leaks = []
    for p in SHARED:
        if p.startswith(("CLAUDE.md", "CHECKLIST.md", ".claude/")) and SECRET.search(read(p) or ""):
            leaks.append(p)
    if leaks:
        return Result(False, fail="Похоже на секрет в общих файлах: %s" % ", ".join(leaks),
                      hint="ключи не кладут в репозиторий: уберите строку и смените ключ.")
    return Result(True, pass_="Общие файлы закоммичены, секретов в них нет")


@check.criterion("Вердикты")
def _verdicts():
    copy = "mkdir -p inputs/memos && cp ../claude-code-kit/team-pack/practice/memos/*.md inputs/memos/"
    absent = [m for m in MEMOS if read("inputs/memos/%s.md" % m) is None]
    if absent:
        return Result(False, fail="Нет памяток в inputs/memos/: %s" % ", ".join(absent),
                      hint="скопируйте их из набора: " + copy)
    changed = [m for m in MEMOS if (ctx["repo"] / "inputs" / "memos" / ("%s.md" % m)).read_bytes()
               != (PACK / "practice" / "memos" / ("%s.md" % m)).read_bytes()]
    if changed:
        return Result(False, fail="Памятки отличаются от набора: %s" % ", ".join(changed),
                      hint="памятки — входные данные, их не правят. Скопируйте заново: " + copy)
    text = read("work/legal-verdicts.csv")
    if text is None:
        return Result(False, fail="Нет work/legal-verdicts.csv",
                      hint="его пишет сессия коллеги в шаге ❻; затем git pull в launch-kit.")
    got = {}
    for row in csv.DictReader(io.StringIO(text)):
        row = {norm(k): v for k, v in row.items() if k}
        m = re.search(r"(\d)", row.get("case") or "")
        if m:
            got["memo-" + m.group(1)] = norm(row.get("verdict"))
    exp = ctx["expected"]
    wrong = []
    for m in MEMOS:
        h = hashlib.sha256(("%s:%s:%s" % (exp["salt"], m, got.get(m, ""))).encode("utf-8")).hexdigest()
        if h != exp["verdicts"][m]:
            wrong.append(m)
    n = len(MEMOS) - len(wrong)
    return Result(not wrong, pass_="Вердикты коллеги совпали с эталоном: %d из %d" % (n, len(MEMOS)),
                  fail="Вердикты совпали с эталоном: %d из %d. Расходятся: %s" % (n, len(MEMOS), ", ".join(wrong)),
                  hint="сверьте эти памятки с legal-rules.md и найдите шаг скила или пункт чеклиста, "
                       "который дал неверный вердикт. Поправьте его, запушьте и повторите шаг ❻.")


if __name__ == "__main__":
    check.run()
