#!/usr/bin/env python3
"""Проверка практики «Pull request с проверками CI».

Запуск из корня launch-kit после слияния PR и git pull:
    python3 ../claude-code-kit/ci/checks/check_pr.py

Слитый PR ищется по Closes #N в описании, если его нет — по ветке с номером
задачи или по правкам теста и реализации: так порядок коммитов и прогоны CI
оцениваются и у PR без ссылки на задачу.

Скрипт только читает: GitHub через gh (repo view, issue list, pr list, pr view,
run list, api GET) и локальный Git. git fetch обновляет лишь сведения о
состоянии GitHub. Скрипт ничего не создаёт, не пушит и не меняет настройки.
"""
import base64
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys

KIT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KIT_ROOT / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

ISSUES_MD = KIT_ROOT / "ci" / "issues.md"
ORIGINAL_TEST = KIT_ROOT / "ci" / "kit-files" / "tests" / "test_status_date.py"
TEST_PATH = "tests/test_status_date.py"
IMPL_PATH = "scripts/build_status.py"
WORKFLOW_PATH = ".github/workflows/checks.yml"
CLOSING = r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\s+#{n}\b"

check = Check("Проверка практики «Pull request с проверками CI»")
ctx = {}


def gh_json(*args):
    res = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=90)
    if res.returncode != 0:
        return None
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return None


def norm_hash(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def remote_file(path):
    data = gh_json("api", f"repos/{ctx['repo']}/contents/{path}?ref={ctx['default']}")
    if not data or "content" not in data:
        return None
    return base64.b64decode(data["content"])


def conclusions(sha):
    data = gh_json("api", f"repos/{ctx['repo']}/commits/{sha}/check-runs") or {}
    return [c.get("conclusion") for c in data.get("check_runs") or []]


@check.before
def _setup():
    if shutil.which("gh") is None:
        raise Stop("GitHub CLI не найден. Установите его: brew install gh или пакет с cli.github.com.")
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
        raise Stop("GitHub CLI не вошёл в аккаунт. Выполните в терминале: gh auth login")
    info = gh_json("repo", "view", "--json", "nameWithOwner,visibility,defaultBranchRef")
    if not info:
        raise Stop("Репозиторий на GitHub не найден. Запускайте проверку из корня launch-kit",
                   "после публикации: gh repo create launch-kit --private --source=. --remote=origin --push")
    ctx["info"] = info
    ctx["repo"] = info["nameWithOwner"]
    ctx["default"] = (info.get("defaultBranchRef") or {}).get("name") or "main"
    ctx["titles"] = [t.strip() for t in re.findall(r"^## (.+)$", ISSUES_MD.read_text(encoding="utf-8"), re.M)]

    issues = gh_json("issue", "list", "--state", "all", "--limit", "200",
                     "--json", "number,title,state") or []
    ctx["by_title"] = {}
    for it in sorted(issues, key=lambda x: x["number"]):
        ctx["by_title"].setdefault(it["title"].strip(), it)
    issue = ctx["by_title"].get(ctx["titles"][0])
    ctx["issue"] = issue

    prs = gh_json("pr", "list", "--state", "merged", "--limit", "100", "--json",
                  "number,body,baseRefName,headRefName,closingIssuesReferences,files") or []
    pr, closes = None, False
    if issue:
        n = issue["number"]
        for p in prs:
            refs = [c.get("number") for c in p.get("closingIssuesReferences") or []]
            if n in refs or re.search(CLOSING.format(n=n), p.get("body") or "", re.I):
                pr, closes = p, True
                break
    if pr is None:
        # PR без Closes: критерии 5 и 6 всё равно оценивают его по существу.
        # Сначала ветка с номером задачи (issue-1-status-date), затем последний
        # слитый в основную ветку PR, который меняет тест или реализацию.
        merged = [p for p in prs if p.get("baseRefName") == ctx["default"]]
        if issue:
            branch = re.compile(rf"(?:^|[-_/#])(?:issue-?)?{issue['number']}(?:$|[-_/])", re.I)
            pr = next((p for p in merged if branch.search(p.get("headRefName") or "")), None)
        if pr is None:
            pr = next((p for p in merged
                       if {TEST_PATH, IMPL_PATH} & {f.get("path") for f in p.get("files") or []}), None)
    ctx["pr"], ctx["closes"] = pr, closes

    commits, files = [], {}
    if pr:
        view = gh_json("pr", "view", str(pr["number"]), "--json", "commits") or {}
        commits = [c["oid"] for c in view.get("commits") or []]
        for sha in commits:
            data = gh_json("api", f"repos/{ctx['repo']}/commits/{sha}") or {}
            files[sha] = {f["filename"] for f in data.get("files") or []}
    ctx["commits"] = commits
    ctx["test_idx"] = next((i for i, s in enumerate(commits) if TEST_PATH in files[s]), None)
    ctx["impl_idx"] = next((i for i, s in enumerate(commits) if IMPL_PATH in files[s]), None)
    ctx["test_alone"] = ctx["test_idx"] is not None and IMPL_PATH not in files[commits[ctx["test_idx"]]]


@check.criterion("Закрытый репозиторий")
def _private():
    return Result(ctx["info"].get("visibility") == "PRIVATE",
                  pass_=f"Репозиторий {ctx['repo']} закрытый",
                  fail=f"Репозиторий {ctx['repo']} открыт всем",
                  hint="сделайте его закрытым в Settings репозитория на GitHub, раздел Danger Zone.")


@check.criterion("Воркфлоу")
def _workflow():
    text = (remote_file(WORKFLOW_PATH) or b"").decode("utf-8", "replace")
    if not text:
        return Result(False, fail=f"В ветке {ctx['default']} нет {WORKFLOW_PATH}",
                      hint="скопируйте воркфлоу из ../claude-code-kit/ci/kit-files/ и запушьте. Шаг ❷.")
    return Result("unittest" in text and "check_repo.py" in text,
                  pass_="Воркфлоу запускает тесты и проверки набора",
                  fail="Воркфлоу не запускает unittest или check_repo.py",
                  hint="верните шаги «Тесты» и «Проверки набора» из файла набора.")


@check.criterion("Задачи")
def _issues():
    missing = [t for t in ctx["titles"] if t not in ctx["by_title"]]
    return Result(not missing, pass_=f"Задачи из issues.md заведены: {len(ctx['titles'])}",
                  fail=f"Не найдены задачи: {'; '.join(missing)}",
                  hint="создайте их через gh issue create с заголовками точно как в issues.md.")


@check.criterion("PR закрыл задачу")
def _closed():
    issue, pr, default = ctx["issue"], ctx["pr"], ctx["default"]
    if not issue:
        return Result(False, fail="Задача про дату не проверялась: её нет на GitHub", hint="сначала шаг ❸.")
    n = issue["number"]
    if not pr:
        return Result(False, fail=f"Нет слитого PR, который закрывает #{n}",
                      hint=f"в описании PR напишите Closes #{n} и слейте PR в {default}.")
    if not ctx["closes"]:
        return Result(False, fail=f"PR #{pr['number']} слит в {default}, но не закрывает задачу #{n}",
                      hint=[f"в описании PR нет Closes #{n}, поэтому GitHub не закрыл задачу при слиянии.",
                            f"Допишите Closes #{n} в описание PR #{pr['number']} и закройте задачу: gh issue close {n}."])
    if pr.get("baseRefName") != default:
        return Result(False, fail=f"PR #{pr['number']} слит не в {default}",
                      hint=f"Closes закрывает задачу только при слиянии в {default}.")
    return Result(issue.get("state") == "CLOSED",
                  pass_=f"PR #{pr['number']} слит в {default} и закрыл задачу #{n}",
                  fail=f"PR #{pr['number']} слит, но задача #{n} открыта",
                  hint=f"проверьте, что в описании PR есть Closes #{n}.")


@check.criterion("Порядок коммитов")
def _order():
    if not ctx["pr"]:
        return Result(False, fail="Порядок коммитов не проверялся: нет слитого PR", hint="сначала шаги ❹–❼.")
    t, i = ctx["test_idx"], ctx["impl_idx"]
    if t is None or i is None:
        return Result(False, fail="В PR нет коммита с тестом или коммита с реализацией",
                      hint=f"первым коммитом добавьте {TEST_PATH}, следующим — правку {IMPL_PATH}.")
    return Result(t < i and ctx["test_alone"], pass_="Приёмочный тест закоммичен раньше реализации",
                  fail="Приёмочный тест закоммичен не отдельно и не первым",
                  hint="тест коммитят отдельно и первым: так CI показывает, что задача ещё не сделана.")


@check.criterion("Красный, затем зелёный")
def _red_green():
    t, i = ctx["test_idx"], ctx["impl_idx"]
    if not ctx["pr"] or t is None or i is None or t >= i:
        return Result(False, fail="Прогоны CI не проверялись: нет пары «тест, затем реализация»",
                      hint="сначала шаги ❹–❻.")
    if "failure" not in conclusions(ctx["commits"][t]):
        return Result(False, fail="CI не краснел на коммите с тестом",
                      hint="запушьте коммит с тестом отдельно, до реализации, и дождитесь красного прогона.")
    green = conclusions(ctx["commits"][-1])
    return Result(bool(green) and all(c == "success" for c in green),
                  pass_="CI краснел на коммите с тестом и зеленел на последнем коммите PR",
                  fail="CI на последнем коммите PR не зелёный",
                  hint="gh pr checks покажет, какая проверка упала.")


@check.criterion("Тест не изменён")
def _test_same():
    data = remote_file(TEST_PATH)
    if data is None:
        return Result(False, fail=f"В {ctx['default']} нет {TEST_PATH}",
                      hint="тест входит в PR вместе с реализацией.")
    return Result(norm_hash(data) == norm_hash(ORIGINAL_TEST.read_bytes()),
                  pass_=f"{TEST_PATH} совпадает с файлом набора",
                  fail=f"{TEST_PATH} в {ctx['default']} изменён",
                  hint="приёмочный тест не правят: верните файл из набора отдельным PR.")


@check.criterion("CI в main")
def _main_green():
    runs = gh_json("run", "list", "--branch", ctx["default"], "--limit", "20",
                   "--json", "conclusion,status") or []
    done = [x for x in runs if x.get("status") == "completed"]
    return Result(bool(done) and done[0].get("conclusion") == "success",
                  pass_=f"Последний прогон CI в {ctx['default']} зелёный",
                  fail=f"Последний прогон CI в {ctx['default']} не зелёный или его нет",
                  hint=f"gh run list --branch {ctx['default']} и gh run view --log-failed покажут причину.")


@check.criterion("Локальная копия")
def _local():
    d = ctx["default"]
    subprocess.run(["git", "fetch", "-q", "origin"], capture_output=True, timeout=60)
    rev = lambda ref: subprocess.run(["git", "rev-parse", "-q", "--verify", ref],
                                     capture_output=True, text=True).stdout.strip()
    local, remote = rev(d), rev(f"origin/{d}")
    return Result(bool(local) and local == remote,
                  pass_=f"Локальная {d} совпадает с GitHub",
                  fail=f"Локальная {d} не совпадает с GitHub",
                  hint=f"git switch {d} и git pull.")


if __name__ == "__main__":
    check.run()
