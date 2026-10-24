"""Проверка практики «Дайджест из двух источников» (модуль 13).

Запуск из папки launch-kit после коммита:
    python3 ../claude-code-kit/connectors/checks/check_digest.py

Критерии:
1. inputs/digest/ совпадает с connectors/inputs/ набора;
2. есть outputs/digest.md с заголовком недели и разделами «Решения» и «Документы»
   (если файла нет — проверка останавливается);
3. в «Решениях» все решения недели: дата, имя автора, текст;
4. в «Решениях» нет лишнего: сообщений вне недели, ботов, других реакций, старого текста правки;
5. в файле нет идентификаторов Slack (U01…, <@…>);
6. в «Документах» ровно документы недели (по полю date в шапке);
7. последняя строка — «Итого решений: N» с верным N;
8. scripts/digest.py есть и воспроизводит outputs/digest.md побайтно (без учёта пробелов в концах строк);
9. scripts/digest.py на данных другой недели даёт верные решения, документы и итог.

Скрипт студента запускается только во временных копиях: launch-kit проверка не меняет.
Таймаут на запуск — 60 с. Только стандартная библиотека. Эталон не печатается.
"""
import hashlib
import json
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
EXP = json.loads((KIT / "checks" / "expected" / "digest.json").read_text(encoding="utf-8"))
TIMEOUT = 60
SKIP = shutil.ignore_patterns(".git", "node_modules", ".venv", "venv", "__pycache__", ".DS_Store")

check = Check("Проверка практики «Дайджест из двух источников»")
state = {}


def norm(s):
    s = s.replace(" ", " ").replace("ё", "е").replace("Ё", "Е")
    s = re.sub(r"[“”„\"]", "«", s)
    s = re.sub(r"[‐‑‒–—―]", "—", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def norm_file(t):
    lines = [line.rstrip() for line in t.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def sections(text):
    """Разделы по заголовкам «## …»: {имя: [строки]}."""
    out, cur = {}, None
    for line in text.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            cur = norm(m.group(1))
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return out


def items(lines):
    return [norm(re.sub(r"^\s*[-*]\s+", "", l)) for l in lines if re.match(r"^\s*[-*]\s+\S", l)]


def last_line(text):
    lines = [l.strip() for l in text.replace("\r\n", "\n").split("\n") if l.strip()]
    return lines[-1] if lines else ""


def file_hashes(base):
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(base.rglob("*")) if p.is_file() and p.name != ".DS_Store"}


def judge(text, exp):
    """Сверка дайджеста с ожиданием. Возвращает словарь с найденными расхождениями."""
    sec = sections(text)
    dec = items(sec.get("решения", []))
    docs = items(sec.get("документы", []))
    missing = []
    for date, who, body in exp["decisions"]:
        hit = [i for i in dec if norm(body) in i]
        if not hit:
            missing.append(("нет", date))
        elif not any(date in i and norm(who) in i for i in hit):
            missing.append(("без даты или автора", date))
    extra = [kind for kind, body in exp["forbidden"] if any(norm(body) in i for i in dec)]
    docs_missing = [d for d, t in exp["docs"] if not any(norm(t) in i and d in i for i in docs)]
    docs_extra = [t for t in exp["docs_forbidden"] if any(norm(t) in i for i in docs)]
    total = re.fullmatch(r"Итого решений:\s*(\d+)\.?", last_line(text))
    return {
        "has_sections": "решения" in sec and "документы" in sec,
        "missing": missing, "extra": extra, "count": len(dec), "n_exp": len(exp["decisions"]),
        "docs_missing": docs_missing, "docs_extra": docs_extra, "docs_count": len(docs),
        "total": int(total.group(1)) if total else None,
    }


def run_script(work, frm, to):
    out = work / "outputs" / "digest.md"
    if out.exists():
        out.unlink()
    (work / "outputs").mkdir(exist_ok=True)
    try:
        run = subprocess.run([sys.executable, "scripts/digest.py", "--from", frm, "--to", to], cwd=work,
                             capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, f"скрипт работал дольше {TIMEOUT} с"
    if run.returncode != 0:
        tail = (run.stderr or run.stdout).strip().splitlines()
        return None, f"скрипт завершился с ошибкой: {tail[-1] if tail else run.returncode}"
    if not out.exists():
        return None, "после запуска нет outputs/digest.md"
    return out.read_text(encoding="utf-8"), None


@check.before
def _load():
    inputs = PROJECT / "inputs" / "digest"
    if not inputs.is_dir():
        raise Stop("Нет папки inputs/digest/. Запускайте проверку из корня launch-kit,",
                   "а данные скопируйте из ../claude-code-kit/connectors/inputs/ (шаг 1).")
    state["inputs"] = inputs
    path = PROJECT / "outputs" / "digest.md"
    state["digest"] = path.read_text(encoding="utf-8") if path.is_file() else None


@check.criterion("данные")
def _inputs():
    mine, kit = file_hashes(state["inputs"]), file_hashes(KIT / "inputs")
    changed = sorted(k for k in kit if mine.get(k) != kit[k])
    return Result(not changed, pass_="inputs/digest/ совпадает с данными набора",
                  fail=f"inputs/digest/ отличается от набора: {len(changed)} файл(ов) изменено или нет",
                  hint="скопируйте ../claude-code-kit/connectors/inputs/ заново; входные данные не правят.")


@check.criterion("файл")
def _file():
    text = state["digest"]
    if text is None:
        raise Stop("✘ Нет outputs/digest.md.", "  Подсказка: запустите python3 scripts/digest.py "
                   "--from 2026-09-28 --to 2026-10-04 (шаг 4).", code=1)
    main = EXP["main"]
    head = next((l for l in text.splitlines() if l.startswith("# ")), "")
    ok_head = main["from"] in head and main["to"] in head
    state["main"] = judge(text, main)
    ok = ok_head and state["main"]["has_sections"]
    return Result(ok, pass_="outputs/digest.md: заголовок недели, разделы «Решения» и «Документы»",
                  fail="в outputs/digest.md нет заголовка с датами недели или разделов «## Решения» и «## Документы»",
                  hint="формат — в inputs/digest/README.md, раздел «Формат дайджеста».")


@check.criterion("решения")
def _decisions():
    r = state["main"]
    return Result(not r["missing"], pass_="все решения недели на месте, с датой и автором",
                  fail=f"не хватает решений или у них нет даты и имени: {len(r['missing'])}",
                  hint=["решение — сообщение человека с реакцией white_check_mark за 28.09–04.10;",
                        "текст — дословно, упоминания <@…> заменены именами."])


@check.criterion("лишнее")
def _extra():
    r = state["main"]
    kinds = {"out-of-week": "сообщения вне недели", "bot": "сообщение бота", "old-text": "старый текст правки",
             "other-reaction": "сообщение без ✅ (другая реакция)", "no-reaction": "сообщение без реакции"}
    found = sorted({kinds[k] for k in r["extra"]})
    ok = not found and r["count"] == r["n_exp"]
    fail = "в «Решениях» лишнее: " + ", ".join(found) if found else \
        f"в «Решениях» {r['count']} пунктов, а решений за неделю другое число"
    return Result(ok, pass_="в «Решениях» нет лишних сообщений", fail=fail,
                  hint="сверьте отбор с правилами 1–4 в inputs/digest/README.md.")


@check.criterion("имена")
def _ids():
    bad = re.findall(r"<@[^>]*>|\bU0[0-9A-Z]{3,}\b", state["digest"])
    return Result(not bad, pass_="в дайджесте имена, а не идентификаторы Slack",
                  fail=f"в дайджесте остались идентификаторы Slack: {len(bad)}",
                  hint="замените авторов и упоминания <@U…> на real_name из users.json.")


@check.criterion("документы")
def _docs():
    r = state["main"]
    ok = not r["docs_missing"] and not r["docs_extra"] and r["docs_count"] == len(EXP["main"]["docs"])
    return Result(ok, pass_="в «Документах» ровно документы недели",
                  fail="в «Документах» не те документы: не хватает "
                       f"{len(r['docs_missing'])}, лишних {len(r['docs_extra'])}",
                  hint="неделю документа определяет поле date в шапке файла, а не имя файла; README.md не документ.")


@check.criterion("итог")
def _total():
    r = state["main"]
    return Result(r["total"] == r["n_exp"], pass_="последняя строка «Итого решений» совпадает с числом решений",
                  fail="последняя строка — не «Итого решений: N» или N неверное",
                  hint="итог считает скрипт по отобранным решениям, а не по всем сообщениям с реакциями.")


@check.criterion("воспроизводимость")
def _repro():
    if not (PROJECT / "scripts" / "digest.py").is_file():
        return Result(False, fail="нет scripts/digest.py",
                      hint="дайджест собирает скрипт (шаг 3), а не ответ модели.")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "launch-kit"
        shutil.copytree(PROJECT, work, ignore=SKIP)
        text, err = run_script(work, EXP["main"]["from"], EXP["main"]["to"])
    if err:
        return Result(False, fail=f"scripts/digest.py: {err}",
                      hint="запустите его сами с теми же аргументами и прочитайте вывод.")
    same = norm_file(text) == norm_file(state["digest"])
    return Result(same, pass_="scripts/digest.py заново собирает тот же outputs/digest.md",
                  fail="outputs/digest.md не совпадает с результатом scripts/digest.py",
                  hint="дайджест правили руками или не пересобрали после правки скрипта.")


@check.criterion("другая неделя")
def _variant():
    if not (PROJECT / "scripts" / "digest.py").is_file():
        return Result(False, fail="нет scripts/digest.py — проверка на другой неделе невозможна")
    var = EXP["variant"]
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "launch-kit"
        shutil.copytree(PROJECT, work, ignore=SKIP)
        shutil.rmtree(work / "inputs" / "digest")
        shutil.copytree(KIT / "checks" / "expected" / "variant", work / "inputs" / "digest")
        shutil.copy2(KIT / "inputs" / "README.md", work / "inputs" / "digest" / "README.md")
        text, err = run_script(work, var["from"], var["to"])
    if err:
        return Result(False, fail=f"на данных другой недели {err}",
                      hint="даты недели берутся из аргументов --from и --to, а не записаны в коде.")
    r = judge(text, var)
    ids = re.findall(r"<@[^>]*>|\bU0[0-9A-Z]{3,}\b", text)
    ok = (r["has_sections"] and not r["missing"] and not r["extra"] and r["count"] == r["n_exp"]
          and not r["docs_missing"] and not r["docs_extra"] and r["total"] == r["n_exp"] and not ids)
    return Result(ok, pass_="на данных другой недели скрипт отбирает решения и документы по тем же правилам",
                  fail="на данных другой недели (новые люди, другие даты) скрипт ошибается",
                  hint=["проверьте, что скрипт не опирается на конкретные тексты, имена и даты:",
                        "имена — из users.json, неделя — из аргументов, документы — по полю date."])


if __name__ == "__main__":
    check.run()
