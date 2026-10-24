"""Проверка практики «Сверка утверждений с источниками» (модуль 5).

Запуск из папки launch-kit:
    python3 ../claude-code-kit/claims-check/checks/check_claims.py

Читает outputs/claims-check.csv (id,verdict,source,quote,location) и
outputs/first-screen-copy.md. Цитаты ищет в канонических копиях источников
из набора (claims-check/inputs/sources/), текст PDF — в
checks/expected/pdf_pages.json. Эталон не печатает: только «совпало / не
совпало» и подсказку. Только стандартная библиотека, Python 3.9+.
"""
import csv
import hashlib
import io
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT.parent / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

ROOT = Path.cwd()
COMMAND = "python3 ../claude-code-kit/claims-check/checks/check_claims.py"
TABLE = Path("outputs") / "claims-check.csv"
COPY = Path("outputs") / "first-screen-copy.md"
INPUTS = Path("inputs") / "claims"
HEADER = ["id", "verdict", "source", "quote", "location"]
SOURCES = ["product-sheet.md", "changelog.md", "agency-study.pdf", "reportflow-blog.html"]
VERDICTS = ["подтверждено", "искажено", "устарело", "недостаточно данных"]
NEEDS_QUOTE = {"подтверждено", "искажено", "устарело"}
NO_DATA = "недостаточно данных"
IDS = [str(i) for i in range(1, 11)]
MIN_QUOTE = 20

HINTS = {
    "1": "Найдите в источниках фразу о времени сборки отчёта.",
    "2": "Есть ли запись о Google Drive свежее справки от 1 сентября?",
    "3": "Сравните справку о продукте с журналом изменений: что случилось позже?",
    "4": "Найдите, где именно это сказано. Если нигде, какой вердикт остаётся?",
    "5": "Сравните число в утверждении с числом в исследовании.",
    "6": "Сравните цитату в черновике с текстом источника слово в слово.",
    "7": "Кто проводил опрос и кого спрашивали? Годится ли это для утверждения обо всех агентствах?",
    "8": "Найдите в источниках список проверок данных.",
    "9": "Посмотрите ключевые цифры исследования.",
    "10": "Посмотрите журнал изменений за сентябрь.",
}
FIRST_FIX_TABLE = "Сначала исправьте таблицу сверки."

check = Check("Проверка claims-check: сверка утверждений первого экрана")
state = {"rows": {}, "table_ok": False, "table_hint": [], "expected": {}, "texts": {}}


def each(lines):
    """По «Подсказке:» на каждую строку списка (раннер ставит её только первой)."""
    lines = [line for line in lines if line]
    return lines[:1] + ["Подсказка: " + line for line in lines[1:]]


def norm(text):
    text = text.replace(" ", " ")
    text = re.sub(r"[«»“”„\"']", "", text)
    text = text.replace("–", "—").replace("ё", "е").replace("Ё", "Е")
    text = re.sub(r"\s*—\s*", " — ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def norm_quote(text):
    return re.sub(r"[.;:,\s]+$", "", norm(text))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Sections(HTMLParser):
    """Текст каждого section[id] без тегов."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.parts = {}

    def handle_starttag(self, tag, attrs):
        if tag == "section":
            sid = dict(attrs).get("id")
            self.stack.append(sid)
            if sid:
                self.parts.setdefault(sid, [])

    def handle_endtag(self, tag):
        if tag == "section" and self.stack:
            self.stack.pop()

    def handle_data(self, data):
        for sid in self.stack:
            if sid:
                self.parts[sid].append(data)


def load_kit():
    expected_dir = KIT / "checks" / "expected"
    try:
        expected = json.loads((expected_dir / "verdicts.json").read_text(encoding="utf-8"))
        pages = json.loads((expected_dir / "pdf_pages.json").read_text(encoding="utf-8"))
        src = KIT / "inputs" / "sources"
        texts = {}
        for name in ("product-sheet.md", "changelog.md"):
            texts[name] = src.joinpath(name).read_text(encoding="utf-8").split("\n")
        texts["agency-study.pdf"] = pages["agency-study.pdf"]
        parser = Sections()
        parser.feed(src.joinpath("reportflow-blog.html").read_text(encoding="utf-8"))
        texts["reportflow-blog.html"] = {k: " ".join(v) for k, v in parser.parts.items()}
    except (OSError, ValueError, KeyError):
        raise Stop("Набор повреждён: обновите его командой git -C ../claude-code-kit pull")
    state["expected"] = expected
    state["texts"] = texts


def read_table():
    path = ROOT / TABLE
    if not path.exists():
        return [f"Файла {TABLE.as_posix()} нет: шаг ❷ практики."]
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError:
        return ["Таблица не в UTF-8: попросите Claude пересохранить её в кодировке UTF-8."]
    broken = "Таблица не читается как CSV: фразы с запятыми должны быть в кавычках."
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        fields = [(name or "").strip() for name in (reader.fieldnames or [])]
        if fields != HEADER:
            return ["Заголовок должен быть id,verdict,source,quote,location."]
        raw_rows = list(reader)
    except csv.Error:
        return [broken]
    rows, problems, seen, extra = {}, [], [], []
    for raw in raw_rows:
        if None in raw or any(value is None for value in raw.values()):
            return [broken]
        row = {key.strip(): value.strip() for key, value in raw.items()}
        if not any(row.values()):
            continue
        rid = row["id"]
        if rid not in IDS:
            extra.append(rid)
            continue
        if rid in rows and rid not in seen:
            seen.append(rid)
        rows[rid] = row
    for rid in extra:
        problems.append(f"Строка с id «{rid}»: id — номер утверждения от 1 до 10.")
    missing = [rid for rid in IDS if rid not in rows]
    if missing:
        problems.append("Нет строк для утверждений: " + ", ".join(missing) + ".")
    for rid in seen:
        problems.append(f"Утверждение {rid} встречается дважды.")
    if not problems:
        for row in rows.values():
            row["verdict_n"] = re.sub(r"\s+", " ", row["verdict"]).lower()
            row["source_n"] = re.split(r"[\\/]", row["source"])[-1].strip()
        state["rows"] = rows
    return problems


@check.before
def _():
    if not (ROOT / "inputs").is_dir():
        raise Stop(f"Запустите проверку из папки launch-kit: {COMMAND}")
    load_kit()
    problems = read_table()
    state["table_ok"] = not problems
    state["table_hint"] = problems


def needs_table(name_fail):
    """Если таблица не прочиталась, критерий сразу не пройден."""
    def wrap(fn):
        def inner():
            if not state["table_ok"]:
                return Result(False, fail=name_fail, hint=FIRST_FIX_TABLE)
            return fn()
        return inner
    return wrap


@check.criterion("Исходники не изменены")
def _():
    if not (ROOT / INPUTS).is_dir():
        return Result(False, fail="Исходники не изменены",
                      hint="Нет inputs/claims/: скопируйте в неё папку claims-check/inputs из набора.")
    problems = []
    missing = []
    previous = state["expected"].get("sha256_previous", {})
    for rel, digest in state["expected"]["sha256"].items():
        path = ROOT / INPUTS / rel
        if not path.exists():
            missing.append((INPUTS / rel).as_posix())
        elif sha256(path) not in [digest] + previous.get(rel, []):
            problems.append(f"Изменён {(INPUTS / rel).as_posix()}: верните его из набора.")
    if missing:
        problems.insert(0, "Нет " + ", ".join(missing) + ": скопируйте папку из набора.")
    return Result(not problems, pass_="Исходники не изменены", fail="Исходники не изменены",
                  hint=each(problems))


@check.criterion("Таблица сверки на месте: 10 утверждений")
def _():
    return Result(state["table_ok"], pass_="Таблица сверки на месте: 10 утверждений",
                  fail="Таблица сверки на месте: 10 утверждений", hint=each(state["table_hint"]))


@check.criterion("Вердикты из списка")
@needs_table("Вердикты из списка")
def _():
    bad = [f"Утверждение {rid}: вердикт «{row['verdict']}» не из списка."
           for rid, row in sorted(state["rows"].items(), key=lambda kv: int(kv[0]))
           if row["verdict_n"] not in VERDICTS]
    if bad:
        bad.append("Список: " + ", ".join(VERDICTS) + ".")
    return Result(not bad, pass_="Вердикты из списка", fail="Вердикты из списка", hint=each(bad))


def place_text(source, location):
    """Текст по месту или None, если место не распознано."""
    texts = state["texts"]
    if source.endswith(".md"):
        m = re.search(r"\d+", location)
        lines = texts[source]
        if m and 1 <= int(m.group()) <= len(lines):
            return lines[int(m.group()) - 1]
        return None
    if source.endswith(".pdf"):
        m = re.search(r"\d+", location)
        return texts[source].get(m.group().lstrip("0") or "0") if m else None
    m = re.search(r"#([\w-]+)", location)
    return texts[source].get(m.group(1)) if m else None


@check.criterion("Цитаты дословно есть в источниках по указанному месту")
@needs_table("Цитаты дословно есть в источниках по указанному месту")
def _():
    problems = []
    for rid in IDS:
        row = state["rows"][rid]
        if not row["quote"]:
            continue
        source = row["source_n"]
        if not source:
            problems.append(f"Утверждение {rid}: у цитаты не указан источник.")
            continue
        if source not in SOURCES:
            problems.append(f"Утверждение {rid}: источник «{row['source']}» не найден среди четырёх файлов.")
            continue
        text = place_text(source, row["location"])
        if text is None:
            problems.append(f"Утверждение {rid}: место «{row['location']}» не распознано: строка N, с. N или #id.")
            continue
        quote = norm_quote(row["quote"])
        if len(quote) < MIN_QUOTE:
            problems.append(f"Утверждение {rid}: цитата слишком короткая, нужна фраза целиком.")
            continue
        if quote not in norm(text):
            problems.append(f"Утверждение {rid}: цитаты нет дословно по указанному месту. "
                            "Найдите её в источнике поиском.")
    return Result(not problems, pass_="Цитаты дословно есть в источниках по указанному месту",
                  fail="Цитаты дословно есть в источниках по указанному месту", hint=each(problems))


@check.criterion("У подтверждённых, искажённых и устаревших есть источник, цитата и место")
@needs_table("У подтверждённых, искажённых и устаревших есть источник, цитата и место")
def _():
    problems = [f"Утверждение {rid}: для такого вердикта нужны источник, цитата и место."
                for rid in IDS
                for row in [state["rows"][rid]]
                if row["verdict_n"] in NEEDS_QUOTE
                and not (row["source"] and row["quote"] and row["location"])]
    text = "У подтверждённых, искажённых и устаревших есть источник, цитата и место"
    return Result(not problems, pass_=text, fail=text, hint=each(problems))


@check.criterion("Есть хотя бы один вердикт «недостаточно данных»")
@needs_table("Есть хотя бы один вердикт «недостаточно данных»")
def _():
    ok = any(row["verdict_n"] == NO_DATA for row in state["rows"].values())
    return Result(ok, pass_="Есть хотя бы один вердикт «недостаточно данных»",
                  fail="Есть хотя бы один вердикт «недостаточно данных»",
                  hint="Если для утверждения нет источника или источник не годится, "
                       "это «недостаточно данных», а не «подтверждено».")


def matched_ids():
    claims = state["expected"]["claims"]
    return [rid for rid in IDS if state["rows"][rid]["verdict_n"] == claims[rid]["verdict"]]


@check.criterion("Вердикты совпадают с эталоном")
def _():
    if not state["table_ok"]:
        return Result(False, fail="Вердикты совпадают с эталоном: 0 из 10", hint=FIRST_FIX_TABLE)
    good = matched_ids()
    text = f"Вердикты совпадают с эталоном: {len(good)} из 10"
    wrong = [f"Утверждение {rid}: {HINTS[rid]}" for rid in IDS if rid not in good]
    return Result(not wrong, pass_=text, fail=text, hint=each(wrong))


@check.criterion("Источники совпадают с эталоном")
@needs_table("Источники совпадают с эталоном")
def _():
    claims = state["expected"]["claims"]
    target = [rid for rid in matched_ids() if claims[rid]["source"]]
    if not target:
        return Result(False, fail="Источники совпадают с эталоном",
                      hint="Сначала добейтесь совпадения вердиктов.")
    wrong = [f"Утверждение {rid}: источник не тот. Если подходящих источников несколько, нужен самый свежий."
             for rid in target if state["rows"][rid]["source_n"] != claims[rid]["source"]]
    return Result(not wrong, pass_="Источники совпадают с эталоном",
                  fail="Источники совпадают с эталоном", hint=each(wrong))


@check.criterion("Исправленный текст не содержит неподтверждённого")
def _():
    name = "Исправленный текст не содержит неподтверждённого"
    path = ROOT / COPY
    if not path.exists():
        return Result(False, fail=name, hint="Файла нет: шаг ❺ практики.")
    text = path.read_bytes().decode("utf-8-sig", errors="replace").replace(" ", " ")
    m = re.search(r"^\s*(#+\s*)?Убрано", text, re.M)
    if not m:
        return Result(False, fail=name, hint="Нет раздела «Убрано» с убранными утверждениями и причинами.")
    head = text[:m.start()].lower()
    problems = []
    if any(re.search(pattern, head) for pattern in state["expected"]["copy_banned"]):
        problems.append("В тексте осталось неподтверждённое или устаревшее утверждение: сверьте текст с таблицей.")
    if not all(any(re.search(v, head) for v in group) for group in state["expected"]["copy_required"]):
        problems.append("Из текста пропали подтверждённые факты: верните их в формулировке источника.")
    return Result(not problems, pass_=name, fail=name, hint=each(problems))


if __name__ == "__main__":
    check.run()
