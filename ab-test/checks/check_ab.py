#!/usr/bin/env python3
"""claude-code-kit · ab-test · проверка практики «Решение по A/B-тесту первого экрана».

Запуск из папки launch-kit:
    python3 ../claude-code-kit/ab-test/checks/check_ab.py

Проверка пересчитывает конверсии по копии данных из набора, ищет числа в
outputs/ab-decision.md и сверяет решение с эталоном. Эталон не печатается.
Только стандартная библиотека, Python 3.9+.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT.parent / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

PROJECT = Path.cwd()
DATA = Path("inputs/ab-first-screen.csv")
PLAN = Path("inputs/ab-plan.md")
DECISION = Path("outputs/ab-decision.md")
SALT = "claude-code-kit/ab-test:"
OPTIONS = {
    "внедрить b": "внедрить B",
    "оставить a": "оставить A",
    "перезапустить тест": "перезапустить тест",
}
CONSTANTS = [0, 1, 5, 10, 20, 50, 80, 90, 95, 99, 100]

check = Check("Проверка практики «Решение по A/B-тесту первого экрана»")
state: dict = {}


# --- пересчёт -----------------------------------------------------------------

def load_rows() -> list[dict]:
    with open(KIT / DATA, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def tally(rows: list[dict]) -> dict:
    """{срез: {вариант: [визиты, заявки]}} для срезов, которые бывают в решении."""
    t: dict = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        day = int(r["date"][-2:])
        period = "d1-2" if day <= 2 else "d3-14"
        week = "w1" if day <= 7 else "w2"
        keys = [
            ("all",), ("device", r["device"]), ("channel", r["channel"]), ("day", day),
            ("period", period), ("week", week), ("device-period", r["device"], period),
        ]
        for k in keys:
            cell = t[k][r["variant"]]
            cell[0] += 1
            cell[1] += int(r["converted"])
    return t


def allowed_percents(t: dict) -> list[float]:
    """Проценты, которые честно получаются из данных: конверсии, доли, разницы и приросты."""
    vals: list[float] = list(map(float, CONSTANTS))
    total_n = sum(v[0] for v in t[("all",)].values())
    for key, by_var in t.items():
        a, b = by_var["A"], by_var["B"]
        n, c = a[0] + b[0], a[1] + b[1]
        pa, pb = a[1] / a[0], b[1] / b[0]
        vals += [100 * pa, 100 * pb]                      # конверсия каждого варианта
        if key[0] == "day":
            continue                                       # по дням — только конверсии
        vals.append(100 * c / n)                          # конверсия среза в целом
        vals += [100 * abs(pb - pa), 100 * abs(pb / pa - 1), 100 * abs(pa / pb - 1)]
        ra, rb = round(100 * pa, 1), round(100 * pb, 1)   # прирост, посчитанный по округлённым долям
        vals += [abs(rb - ra), 100 * abs(rb / ra - 1), 100 * abs(ra / rb - 1)]
        if key[0] in ("all", "device"):
            vals += [100 * a[0] / n, 100 * b[0] / n, 100 * n / total_n]          # доли визитов
            vals += [100 * abs(b[0] / a[0] - 1), 100 * abs(a[0] / b[0] - 1)]     # нехватка визитов
            se = math.sqrt(pa * (1 - pa) / a[0] + pb * (1 - pb) / b[0])
            vals += [100 * abs(pb - pa - 1.96 * se), 100 * abs(pb - pa + 1.96 * se), 100 * 1.96 * se]
    for var in ("A", "B"):                                # состав варианта по устройствам
        nv = t[("all",)][var][0]
        vals += [100 * t[("device", dev)][var][0] / nv for dev in ("mobile", "desktop")]
    return vals


# --- разбор решения -------------------------------------------------------------

DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")
PCT_RE = re.compile(r"(?<![\w.,])[+\-−–]?\s?(\d+(?:[.,]\d+)?)\s?%")
PP_RE = re.compile(r"(?<![\w.,])[+\-−–]?\s?(\d+(?:[.,]\d+)?)\s?п\.\s?п\.")
DECISION_RE = re.compile(r"^[\s>*_#\-]*решение[\s*_]*:\s*(.+)$", re.I)


def tolerance(token: str) -> float:
    token = token.replace(",", ".")
    decimals = len(token.split(".")[1]) if "." in token else 0
    return 0.5 * 10 ** (-decimals) + 1e-6


def matches(token: str, targets: list[float]) -> bool:
    value = float(token.replace(",", "."))
    tol = tolerance(token)
    return any(abs(value - t) <= tol for t in targets)


def normalize_decision(raw: str) -> str | None:
    text = raw.strip().lower().replace("ё", "е")
    text = re.sub(r"[*_`«»\"']", "", text)
    text = re.split(r"[.;:,(—–]| - ", text)[0].strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\b([вb])$", "b", text) if text.startswith("внедрить") else text
    text = re.sub(r"\b([аa])$", "a", text) if text.startswith("оставить") else text
    text = text.replace("внедрить в", "внедрить b").replace("оставить а", "оставить a")
    return OPTIONS.get(text)


def decision_text() -> str:
    return state["text"]


@check.before
def _prepare():
    if not (PROJECT / "inputs").is_dir():
        raise Stop("Не найдена папка inputs/. Запустите проверку из папки launch-kit.")
    if not (PROJECT / DATA).exists():
        raise Stop(f"Нет файла {DATA}. Скопируйте его из ../claude-code-kit/ab-test/inputs/ и запустите проверку снова.")
    if not (PROJECT / DECISION).exists():
        raise Stop(f"Нет файла {DECISION}. Запишите решение по шагу 5 практики и запустите проверку снова.")
    state["text"] = (PROJECT / DECISION).read_text(encoding="utf-8")
    state["tally"] = tally(load_rows())
    state["allowed"] = allowed_percents(state["tally"])
    clean = DATE_RE.sub(" ", state["text"])
    state["pcts"] = PCT_RE.findall(clean)
    state["pps"] = PP_RE.findall(clean)


def rate(key: tuple, var: str) -> float:
    n, c = state["tally"][key][var]
    return 100 * c / n


def mentioned(value: float) -> bool:
    """Число названо в решении: целое процентное значение засчитывается, только если совпадает до 0,05."""
    return any(abs(float(tok.replace(",", ".")) - value) <= min(tolerance(tok), 0.051) for tok in state["pcts"])


@check.criterion("Исходные файлы не изменены")
def _inputs():
    changed = []
    for rel in (DATA, PLAN):
        mine = PROJECT / rel
        if not mine.exists():
            changed.append(f"{rel} (нет файла)")
        elif mine.read_bytes() != (KIT / rel).read_bytes():
            changed.append(str(rel))
    return Result(not changed,
                  pass_="Исходные файлы в inputs/ совпадают с набором",
                  fail="Исходные файлы отличаются от набора: " + ", ".join(changed),
                  hint="верните файлы из ../claude-code-kit/ab-test/inputs/: данные теста не правят, расчёт идёт по копии в памяти скрипта.")


@check.criterion("Расчёт сделан скриптом")
def _script():
    scripts = [p for p in (PROJECT / "scripts").glob("*.py")] if (PROJECT / "scripts").is_dir() else []
    found = [p for p in scripts if "ab-first-screen.csv" in p.read_text(encoding="utf-8", errors="ignore")]
    return Result(bool(found),
                  pass_=f"Расчёт в скрипте: scripts/{found[0].name}" if found else None,
                  fail="В scripts/ нет скрипта, который читает inputs/ab-first-screen.csv",
                  hint="попросите Claude сохранить расчёт в scripts/ab_check.py и запускать его, а не считать в ответе.")


@check.criterion("Строка решения")
def _decision_line():
    found = [DECISION_RE.match(line) for line in decision_text().splitlines()]
    lines = [m.group(1) for m in found if m]
    if len(lines) != 1:
        return Result(False, fail=f"Строк «Решение: …» в файле: {len(lines)}, нужна одна",
                      hint="одна строка вида «Решение: внедрить B», «Решение: оставить A» или «Решение: перезапустить тест».")
    value = normalize_decision(lines[0])
    state["decision"] = value
    return Result(value is not None,
                  pass_=f"Решение записано: {value}",
                  fail=f"Решение не из списка плана: «{lines[0].strip()}»",
                  hint="план допускает три варианта: «внедрить B», «оставить A», «перезапустить тест».")


@check.criterion("Три довода с числами")
def _arguments():
    text = decision_text()
    m = re.search(r"^#+[^\n]*довод[^\n]*\n(.*?)(?=^#|\Z)", text, flags=re.I | re.M | re.S)
    body = m.group(1) if m else ""
    items = [l for l in body.splitlines() if re.match(r"^\s*(\d+[.)]|[-*•])\s+", l)]
    with_numbers = [l for l in items if re.search(r"\d", re.sub(r"^\s*\d+[.)]", "", l))]
    ok = bool(m) and len(with_numbers) >= 3
    return Result(ok,
                  pass_=f"Доводов с числами: {len(with_numbers)}",
                  fail="Нет раздела «Доводы» с тремя пунктами, в каждом из которых есть число" if not m
                  else f"В разделе «Доводы» пунктов с числами: {len(with_numbers)}, нужно три",
                  hint="раздел «## Доводы» и три пункта списка; в каждом — число из вывода скрипта.")


@check.criterion("Распределение визитов проверено")
def _split():
    a, b = state["tally"][("all",)]["A"][0], state["tally"][("all",)]["B"][0]
    digits = re.sub(r"(?<=\d)[   ](?=\d{3}\b)", "", decision_text())
    counts = re.search(rf"(?<!\d){a}(?!\d)", digits) and re.search(rf"(?<!\d){b}(?!\d)", digits)
    shares = mentioned(100 * a / (a + b)) and mentioned(100 * b / (a + b))
    return Result(bool(counts or shares),
                  pass_="Фактическое распределение визитов A и B в решении есть",
                  fail="В решении нет фактического распределения визитов между A и B",
                  hint="план требует проверить сплит до чтения результата: приведите число визитов каждого варианта или долю с одним знаком после запятой.")


@check.criterion("Сегменты по устройствам")
def _devices():
    missing = [f"{dev} {var}" for dev in ("mobile", "desktop") for var in ("A", "B")
               if not mentioned(rate(("device", dev), var))]
    return Result(not missing,
                  pass_="Конверсии A и B по мобильным и десктопу в решении есть",
                  fail="Не найдены конверсии по устройствам: " + ", ".join(missing),
                  hint="устройство — сегмент из плана: приведите конверсию A и B отдельно для mobile и desktop с одним знаком после запятой.")


@check.criterion("Динамика по дням")
def _novelty():
    pairs = [
        (("period", "d1-2"), "B", ("period", "d3-14"), "B"),
        (("week", "w1"), "B", ("week", "w2"), "B"),
        (("period", "d3-14"), "A", ("period", "d3-14"), "B"),
    ]
    ok = any(mentioned(rate(k1, v1)) and mentioned(rate(k2, v2)) for k1, v1, k2, v2 in pairs)
    return Result(ok,
                  pass_="Динамика по дням в решении есть",
                  fail="В решении не видно, как конверсия менялась по дням теста",
                  hint="сравните первые два дня с остальными двенадцатью или первую неделю со второй.")


@check.criterion("Числа сходятся с пересчётом")
def _numbers():
    allowed = state["allowed"]
    bad = [tok + "%" for tok in state["pcts"] if not matches(tok, allowed)]
    bad += [tok + " п.п." for tok in state["pps"] if not matches(tok, allowed)]
    total = len(state["pcts"]) + len(state["pps"])
    return Result(total > 0 and not bad,
                  pass_=f"Все проценты в решении найдены в пересчёте ({total})",
                  fail="В решении нет процентов" if total == 0
                  else "Проценты, которых нет в пересчёте: " + ", ".join(dict.fromkeys(bad)),
                  hint="попросите Claude показать, из какой строки вывода скрипта взято каждое число, и исправить или убрать остальные.")


@check.criterion("Решение совпало с эталоном")
def _expected():
    expected = json.loads((KIT / "checks" / "expected" / "ab-decision.json").read_text(encoding="utf-8"))
    value = state.get("decision")
    ok = value is not None and hashlib.sha256((SALT + value).encode("utf-8")).hexdigest() == expected["decision_sha256"]
    return Result(ok,
                  pass_="Решение совпало с эталоном",
                  fail="Решение не совпало с эталоном",
                  hint="перечитайте в ab-plan.md раздел «Проверки до чтения результата» и сверьте с ним первый довод.")


if __name__ == "__main__":
    check.run()
