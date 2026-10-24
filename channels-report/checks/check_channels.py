"""Проверка практики «Отчёт по рекламным каналам».

Запуск из папки launch-kit после коммита:
    python3 ../claude-code-kit/channels-report/checks/check_channels.py

Критерии:
1. inputs/campaigns.csv и inputs/period-test.csv совпадают с уроком;
2. есть outputs/channel-summary.csv (если нет — проверка останавливается);
3. в сводке семь каналов;
4. суммы spend и revenue по каналам равны контрольным;
5. CPL пяти каналов с расходом совпадает с контрольным (до 0,01);
6. у organic и unknown CPL не посчитан;
7. outputs/channels.svg подписывает пять каналов с CPL и называет organic и unknown;
8. граница периода: report.py на пробных данных берёт 1 и 3 мая и не берёт 30 апреля и 4 мая;
9. outputs/status.html содержит раздел «Рекламные каналы» с графиком;
10. повторный запуск report.py и build_status.py даёт побайтно те же файлы;
11. чистая копия из Git по командам outputs/method.md даёт те же файлы.

Скрипты студента запускаются только во временных копиях: launch-kit проверка
не меняет. Таймаут на запуск — 60 с. Только стандартная библиотека.
Числа эталона не печатаются.
"""
import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT.parent / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

PROJECT = Path.cwd()
EXP = json.loads((KIT / "checks" / "expected" / "channels.json").read_text(encoding="utf-8"))
RESULTS = ("channel-summary.csv", "channels.svg", "status.html")
TIMEOUT = 60
SKIP = shutil.ignore_patterns(".git", "node_modules", ".venv", "venv", "__pycache__", ".DS_Store")

check = Check("Проверка практики «Отчёт по рекламным каналам»")
state = {}


def norm_text(t):
    lines = [line.rstrip() for line in t.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def num(s):
    s = re.sub(r"[\s  ]", "", s or "")
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def read_summary(path):
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    return [{(k or "").strip().lower(): (v or "") for k, v in r.items() if k is not None} for r in rows]


def run(cmd, cwd):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                             timeout=TIMEOUT, env=env)
        return res.returncode, (res.stdout + res.stderr).strip()
    except subprocess.TimeoutExpired:
        return None, "не завершился за %d с" % TIMEOUT
    except OSError as exc:
        return None, str(exc)


def copy_project(dst):
    shutil.copytree(str(PROJECT), str(dst), ignore=SKIP)


def last_line(out):
    lines = [line for line in (out or "").splitlines() if line.strip()]
    return lines[-1][:200] if lines else "пусто"


def run_scripts(cwd, scripts):
    """Запускает скрипты по порядку; возвращает (успех, подсказка о сбое)."""
    for script in scripts:
        if not (Path(cwd) / script).is_file():
            return False, "нет файла %s" % script
        code, out = run([sys.executable, script], cwd)
        if code != 0:
            return False, "%s упал: %s" % (script, last_line(out))
    return True, ""


def remove_results(root):
    """Результаты удаляются до запуска: каждый файл обязан пересобраться скриптом."""
    for name in RESULTS:
        p = Path(root) / "outputs" / name
        if p.is_file():
            p.unlink()


def differing(a_dir, b_dir):
    out = []
    for name in RESULTS:
        a, b = Path(a_dir) / "outputs" / name, Path(b_dir) / "outputs" / name
        if not a.is_file() or not b.is_file() or a.read_bytes() != b.read_bytes():
            out.append(name)
    return out


@check.before
def _():
    if not (PROJECT / ".git").exists() and not (PROJECT / "inputs").is_dir():
        raise Stop("Не найден Git-репозиторий в текущей папке.",
                   "Запускайте проверку из корня launch-kit.")


@check.criterion("inputs")
def _():
    bad = []
    for name, text in EXP["inputs"].items():
        p = PROJECT / "inputs" / name
        if not p.is_file() or norm_text(p.read_text(encoding="utf-8-sig")) != norm_text(text):
            bad.append("inputs/" + name)
    return Result(not bad,
                  pass_="inputs/campaigns.csv и inputs/period-test.csv совпадают с уроком",
                  fail="Учебные данные отличаются от урока: " + ", ".join(bad),
                  hint="сравните файлы с текстом из подготовки практики; учебные данные не правят.")


def summary_rows():
    path = PROJECT / "outputs" / "channel-summary.csv"
    if not path.is_file():
        raise Stop("", "Остальные пункты читают сводку, поэтому проверка остановлена.",
                   "Соберите сводку командой python3 scripts/report.py и запустите проверку снова.", code=1)
    if "rows" not in state:
        state["rows"] = read_summary(path)
    return state["rows"]


@check.criterion("summary")
def _():
    ok = (PROJECT / "outputs" / "channel-summary.csv").is_file()
    return Result(ok, pass_="Есть outputs/channel-summary.csv",
                  fail="Нет outputs/channel-summary.csv",
                  hint="сводку пишет скрипт: запустите python3 scripts/report.py.")


def by_channel():
    return {(r.get("channel") or "").strip(): r for r in summary_rows()}


@check.criterion("channels")
def _():
    got = sorted(by_channel())
    return Result(got == sorted(EXP["channels"]),
                  pass_="В сводке семь каналов",
                  fail="В сводке не те каналы",
                  hint=["каналы в сводке: " + (", ".join(c or "(пусто)" for c in got) or "нет") + ".",
                        "Строки не теряют и не объединяют: по строке на каждый channel из inputs/campaigns.csv за период."])


@check.criterion("totals")
def _():
    rows = summary_rows()
    spend = sum(num(r.get("spend")) or 0 for r in rows)
    revenue = sum(num(r.get("revenue")) or 0 for r in rows)
    ok = abs(spend - EXP["spend"]) < 0.01 and abs(revenue - EXP["revenue"]) < 0.01
    return Result(ok,
                  pass_="Суммы spend и revenue по каналам равны контрольным числам",
                  fail="Суммы spend и revenue по каналам не сходятся с контрольными числами",
                  hint="сверьте их с контрольными числами из шага ❶; проверьте фильтр периода и пустые spend.")


@check.criterion("cpl")
def _():
    rows = by_channel()
    bad = [ch for ch, cpl in EXP["cpl"].items()
           if num((rows.get(ch) or {}).get("cpl")) is None
           or abs(num(rows[ch].get("cpl")) - cpl) > 0.01]
    return Result(not bad,
                  pass_="CPL каналов с расходом совпадает с контрольными значениями",
                  fail="CPL не сходится: " + ", ".join(bad),
                  hint="CPL = spend / leads за период, с округлением до двух знаков; колонка называется cpl.")


@check.criterion("no-spend")
def _():
    rows = by_channel()
    zeros = [ch for ch in EXP["no_spend"] if num((rows.get(ch) or {}).get("cpl")) is not None]
    return Result(not zeros,
                  pass_="У каналов без spend CPL не посчитан",
                  fail="У каналов без spend посчитан CPL: " + ", ".join(zeros),
                  hint="пустой spend значит «неизвестно», а не «ноль»: оставьте cpl пустым и напишите причину в note.")


@check.criterion("svg")
def _():
    svg = PROJECT / "outputs" / "channels.svg"
    text = svg.read_text(encoding="utf-8", errors="replace") if svg.is_file() else ""
    missing = [ch for ch in list(EXP["cpl"]) + EXP["no_spend"] if ch not in text]
    ok = svg.is_file() and "<svg" in text and not missing
    if not svg.is_file():
        hint = "графика нет: добавьте его в scripts/report.py (шаг ❹) и запустите скрипт."
    else:
        hint = "в графике не найдены подписи: " + ", ".join(missing) + \
               ". Столбцы подписывают каналом и CPL, каналы без CPL перечисляют под графиком."
    return Result(ok,
                  pass_="В outputs/channels.svg пять столбцов с подписями и два канала под графиком",
                  fail="outputs/channels.svg не показывает все каналы",
                  hint=hint)


@check.criterion("period")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "launch-kit"
        copy_project(work)
        (work / "inputs" / "campaigns.csv").write_text(EXP["period_probe"], encoding="utf-8")
        summary = work / "outputs" / "channel-summary.csv"
        if summary.exists():
            summary.unlink()
        ok_run, why = run_scripts(work, ["scripts/report.py"])
        got = set()
        if ok_run and summary.is_file():
            got = {(r.get("channel") or "").strip() for r in read_summary(summary)}
    ok = got == set(EXP["period_inside"])
    if not ok_run:
        hint = "на пробных данных скрипт не отработал: " + why + "."
    else:
        hint = ["на пробных данных за 30 апреля, 1, 3 и 4 мая в сводку попали: "
                + (", ".join(sorted(got)) or "ничего") + ".",
                "Период — с 1 по 3 мая включительно: проверьте условие «по 3 мая включительно» и дату со временем."]
    return Result(ok,
                  pass_="Фильтр периода берёт 1 и 3 мая и не берёт 30 апреля и 4 мая",
                  fail="Фильтр периода ошибается на границе",
                  hint=hint)


@check.criterion("status-page")
def _():
    html = PROJECT / "outputs" / "status.html"
    page = html.read_text(encoding="utf-8", errors="replace") if html.is_file() else ""
    ok = "Рекламные каналы" in page and ("channels.svg" in page or "<svg" in page)
    return Result(ok,
                  pass_="На странице статуса есть раздел «Рекламные каналы» с графиком",
                  fail="На странице статуса нет раздела «Рекламные каналы» с графиком",
                  hint="добавьте раздел через scripts/build_status.py (шаг ❺) и пересоберите страницу; status.html руками не правят.")


@check.criterion("repeat")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "launch-kit"
        copy_project(work)
        remove_results(work)
        ok_run, why = run_scripts(work, ["scripts/report.py", "scripts/build_status.py"])
        diff = differing(work, PROJECT) if ok_run else list(RESULTS)
    ok = ok_run and not diff
    if not ok_run:
        hint = "повторный запуск не прошёл: " + why + "."
    else:
        hint = ["после повторного запуска отличаются или не пересобрались: " + ", ".join(diff) + ".",
                "Результат правили руками, его пишет не скрипт или скрипт пишет что-то меняющееся: "
                "текущее время, случайный порядок, файл от прошлого запуска. Исправьте скрипт, а не результат."]
    return Result(ok,
                  pass_="Повторный запуск report.py и build_status.py даёт те же файлы в outputs/",
                  fail="Повторный запуск даёт другие файлы",
                  hint=hint)


def method_commands():
    path = PROJECT / "outputs" / "method.md"
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    cmds = re.findall(r"python3\s+(scripts/[\w./-]+\.py)", text)
    has_total = "34700" in re.sub(r"[\s  ]", "", text)
    return path.is_file(), cmds, has_total


@check.criterion("clean-copy")
def _():
    exists, cmds, has_total = method_commands()
    if not exists or not cmds or not has_total:
        if not exists:
            hint = "нет outputs/method.md: запишите его по шагу ❻ и закоммитьте."
        elif not cmds:
            hint = "в outputs/method.md нет команд запуска вида python3 scripts/report.py."
        else:
            hint = "в outputs/method.md нет контрольной суммы spend входа: запишите контрольные числа."
        return Result(False, fail="outputs/method.md не описывает повтор расчёта", hint=hint)
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "clean"
        code, out = run(["git", "clone", "--quiet", str(PROJECT), str(clone)], tmp)
        if code != 0:
            return Result(False, fail="Чистая копия из Git не создалась",
                          hint="git clone не прошёл: " + last_line(out) + ".")
        remove_results(clone)
        ok_run, why = run_scripts(clone, cmds)
        diff = differing(clone, PROJECT) if ok_run else list(RESULTS)
    ok = ok_run and not diff
    if not ok_run:
        hint = ["в чистой копии команды из method.md не прошли: " + why + ".",
                "Закоммитьте скрипты и входы; в method.md — все команды по порядку."]
    else:
        hint = ["в чистой копии отличаются или не пересобрались: " + ", ".join(diff) + ".",
                "Закоммитьте последние версии скриптов, входов и outputs/; в method.md — все команды по порядку."]
    return Result(ok,
                  pass_="Чистая копия из Git по командам method.md даёт те же файлы",
                  fail="Чистая копия из Git даёт другие файлы",
                  hint=hint)


if __name__ == "__main__":
    check.run()
