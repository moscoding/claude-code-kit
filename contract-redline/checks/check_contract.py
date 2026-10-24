"""Проверка практики «Договор с подрядчиком» (модуль 4).

Запуск из папки launch-kit:
    python3 ../claude-code-kit/contract-redline/checks/check_contract.py

Разбирает outputs/contract-redline.docx как zip с XML: правки режима
рецензирования (w:ins/w:del), текст после принятия и после отклонения
правок, стили заголовков. Сравнивает с исходным договором из набора и
правилами в checks/expected/contract.json. Эталон не печатает: только
«совпало / не совпало» и подсказку. Только стандартная библиотека,
Python 3.9+.
"""
import difflib
import hashlib
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT.parent / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

ROOT = Path.cwd()
COMMAND = "python3 ../claude-code-kit/contract-redline/checks/check_contract.py"
RESULT = Path("outputs") / "contract-redline.docx"
SOURCE = Path("inputs") / "contract.docx"
MEMO = Path("outputs") / "contract-memo.md"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
INS = (W + "ins", W + "moveTo")
DEL = (W + "del", W + "moveFrom")
HEADINGS = ("Title", "Heading1", "Heading2")
NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.")
MEMO_CLAUSES = ["2.3", "3.3", "5.3", "6.1", "7.4", "10.4"]

HINTS = {
    1: "В пункте 2.3 после принятия правок должна остаться формулировка из замечания 1.",
    2: "В пункте 3.3 после принятия правок: предоплата и остаток, как в замечании 2.",
    3: "В пункте 5.3 изменился ли срок мотивированного отказа?",
    4: "В пункте 6.1 после принятия правок права должны переходить к Заказчику.",
    5: "Нужен новый пункт 7.4, вставленный целиком как правка.",
    6: "Пункт 10.4 должен быть удалён правкой, а не стёрт из текста.",
}
FIRST_OPEN = "Сначала добейтесь, чтобы файл открывался."

check = Check("Проверка contract-redline: договор с правками Марины")
state = {}


def each(lines):
    """По «Подсказке:» на каждую строку списка (раннер ставит её только первой)."""
    lines = [line for line in lines if line]
    return lines[:1] + ["Подсказка: " + line for line in lines[1:]]


def norm(text):
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


class Docx:
    """Абзацы документа в двух видах: после принятия и после отклонения правок."""

    def __init__(self, path):
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ValueError("нет частей .docx")
            self.root = ET.fromstring(zf.read("word/document.xml"))
            self.styles = ET.fromstring(zf.read("word/styles.xml")) if "word/styles.xml" in names else None
        body = self.root.find(W + "body")
        if body is None:
            raise ValueError("нет w:body")
        self.parent = {child: par for par in self.root.iter() for child in par}
        self.paragraphs = [self._paragraph(p) for p in body.iter(W + "p")]

    def _inside(self, node, stop, tags):
        node = self.parent.get(node)
        while node is not None and node is not stop:
            if node.tag in tags:
                return True
            node = self.parent.get(node)
        return False

    def _paragraph(self, p):
        accepted, rejected = [], []
        for node in p.iter():
            tag = node.tag
            if tag not in (W + "t", W + "delText", W + "tab", W + "br", W + "cr"):
                continue
            text = (node.text or "") if tag in (W + "t", W + "delText") else " "
            in_del = self._inside(node, p, DEL)
            in_ins = self._inside(node, p, INS)
            if tag == W + "delText":
                rejected.append(text)
                continue
            # w:t внутри w:del — ошибка разметки: Word оставит такой текст видимым.
            if tag == W + "t":
                if not self._inside(node, p, (W + "moveFrom",)):
                    accepted.append(text)
            elif not in_del:
                accepted.append(text)
            if not in_ins:
                rejected.append(text)
        style = p.find(f"{W}pPr/{W}pStyle")
        return {
            "el": p,
            "style": style.get(W + "val") if style is not None else "Normal",
            "accepted": norm("".join(accepted)),
            "rejected": norm("".join(rejected)),
        }

    def view(self, name):
        return [p for p in self.paragraphs if p[name]]

    def style_ids(self):
        if self.styles is None:
            return set()
        return {s.get(W + "styleId") for s in self.styles.iter(W + "style")}


def label(text):
    """Как назвать абзац в подсказке: пункт, раздел или начало строки."""
    m = NUMBER.match(text)
    if m:
        number = m.group(1)
        return ("раздел", number) if "." not in number else ("пункт", number)
    return ("абзац", f"«{text[:12]}…»")


def first_difference(source, result):
    """Первый расходящийся абзац: исходника, а если абзац лишний — результата."""
    matcher = difflib.SequenceMatcher(None, source, result, autojunk=False)
    for tag, i1, _i2, j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        return source[i1] if tag in ("replace", "delete") else result[j1]
    return None


@check.before
def _():
    if not (ROOT / "inputs").is_dir():
        raise Stop(f"Запустите проверку из папки launch-kit: {COMMAND}")
    try:
        state["rules"] = json.loads((KIT / "checks" / "expected" / "contract.json").read_text(encoding="utf-8"))
        state["source"] = Docx(KIT / "inputs" / "contract.docx")
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError):
        raise Stop("Набор повреждён: обновите его командой git -C ../claude-code-kit pull")
    path = ROOT / RESULT
    state["doc"], state["doc_error"] = None, None
    if not path.exists():
        state["doc_error"] = f"Файла нет: сохраните результат в {RESULT.as_posix()}."
        return
    try:
        state["doc"] = Docx(path)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError, EOFError):
        state["doc_error"] = ("Файл не открывается как .docx: попросите Claude пересобрать архив "
                              "из распакованной папки и проверить его.")


def needs_doc(fail):
    def wrap(fn):
        def inner():
            if state["doc"] is None:
                text = fail() if callable(fail) else fail
                return Result(False, fail=text, hint=FIRST_OPEN)
            return fn()
        return inner
    return wrap


@check.criterion("Договор открывается")
def _():
    text = f"Договор открывается: {RESULT.as_posix()}"
    return Result(state["doc"] is not None, pass_=text, fail=text, hint=state["doc_error"])


@check.criterion("Исходный договор не изменён")
def _():
    path = ROOT / SOURCE
    if not path.exists():
        hint = f"{SOURCE.as_posix()} не найден: скопируйте его из набора."
        ok = False
    else:
        ok = hashlib.sha256(path.read_bytes()).hexdigest() == state["rules"]["source_sha256"]
        hint = (f"{SOURCE.as_posix()} изменён: верните его из набора и вносите правки "
                "только в копию в outputs/.")
    return Result(ok, pass_="Исходный договор не изменён", fail="Исходный договор не изменён", hint=hint)


REVIEW = "Правки оформлены в режиме рецензирования, автор — Марина"


@check.criterion(REVIEW)
@needs_doc(REVIEW)
def _():
    doc = state["doc"]
    author = state["rules"]["author"]
    marks = [el for el in doc.root.iter() if el.tag in (W + "ins", W + "del")]
    changes = [el for el in marks if doc.parent.get(el) is None or doc.parent[el].tag != W + "rPr"]
    authors = [el.get(W + "author") for el in doc.root.iter() if el.get(W + "author") is not None]
    wrong = [a for a in authors if a != author]
    undated = [el for el in marks if not el.get(W + "author") or not el.get(W + "date")]
    t_in_del = any(el.tag == W + "del" and el.find(f".//{W}t") is not None for el in marks)
    if not changes:
        hint = "Правок режима рецензирования нет: изменения внесены прямо в текст."
    elif len(changes) < 6:
        hint = "Правок режима рецензирования меньше, чем изменений: часть внесена прямо в текст."
    elif wrong:
        hint = f"У правок автор «{wrong[0]}», а нужен «{author}»."
    elif undated:
        hint = "У части правок нет автора или даты."
    elif t_in_del:
        hint = ("Внутри удаления текст записан как w:t: Word покажет его как обычный текст. "
                "Внутри w:del нужен w:delText.")
    else:
        hint = None
    return Result(hint is None, pass_=REVIEW, fail=REVIEW, hint=hint)


def note_done(doc, note):
    must = note.get("must", [])
    must_not = note.get("must_not", [])
    clause = note["clause"]
    accepted = [p for p in doc.view("accepted") if p["accepted"].startswith(clause)]
    rejected = [p for p in doc.view("rejected") if p["rejected"].startswith(clause)]

    def text_ok(par):
        text = par["accepted"].lower()
        return (all(re.search(rx, text) for rx in must)
                and not any(re.search(rx, text) for rx in must_not))

    if note["kind"] == "replace":
        if len(accepted) != 1 or not text_ok(accepted[0]):
            return False
        el = accepted[0]["el"]
        return any(node.tag in (W + "ins", W + "del") for node in el.iter())
    if note["kind"] == "insert":
        return bool(accepted) and text_ok(accepted[0]) and not rejected
    if note["kind"] == "delete":
        return not accepted and bool(rejected)
    raise ValueError(note["kind"])


@check.criterion("Все замечания Марины внесены")
@needs_doc("Все замечания Марины внесены: 0 из 6")
def _():
    notes = state["rules"]["notes"]
    missing = [note["id"] for note in notes if not note_done(state["doc"], note)]
    text = f"Все замечания Марины внесены: {len(notes) - len(missing)} из {len(notes)}"
    return Result(not missing, pass_=text, fail=text,
                  hint=each([f"Замечание {k}: {HINTS[k]}" for k in missing]))


INVISIBLE = "Невидимых правок нет: без правок текст совпадает с исходным"


@check.criterion(INVISIBLE)
@needs_doc(INVISIBLE)
def _():
    source = [p["rejected"] for p in state["source"].view("rejected")]
    result = [p["rejected"] for p in state["doc"].view("rejected")]
    diff = first_difference(source, result)
    hint = None
    if diff is not None:
        kind, name = label(diff)
        where = {"пункт": "в пункте", "раздел": "в разделе", "абзац": "в абзаце"}[kind]
        hint = (f"Без правок текст отличается от исходного {where} {name}: такое изменение агентство "
                "не увидит. Внесите его правкой или верните исходный текст.")
    return Result(diff is None, pass_=INVISIBLE, fail=INVISIBLE, hint=hint)


OUTSIDE = "Вне замечаний договор не изменился"


@check.criterion(OUTSIDE)
@needs_doc(OUTSIDE)
def _():
    targets = tuple(state["rules"]["target_clauses"])
    source = [p["accepted"] for p in state["source"].view("accepted") if not p["accepted"].startswith(targets)]
    result = [p["accepted"] for p in state["doc"].view("accepted") if not p["accepted"].startswith(targets)]
    diff = first_difference(source, result)
    hint = None
    if diff is not None:
        kind, name = label(diff)
        verb = {"пункт": "Изменён пункт", "раздел": "Изменён раздел", "абзац": "Изменён абзац"}[kind]
        hint = f"{verb} {name}, которого нет в замечаниях. Проверьте места, похожие на замечания."
    return Result(diff is None, pass_=OUTSIDE, fail=OUTSIDE, hint=hint)


STYLES = "Стили заголовков на месте"


@check.criterion(STYLES)
@needs_doc(STYLES)
def _():
    def headings(doc):
        return [(p["style"], p["accepted"]) for p in doc.view("accepted") if p["style"] in HEADINGS]

    doc = state["doc"]
    ok = headings(doc) == headings(state["source"]) and {"Heading1", "Heading2"} <= doc.style_ids()
    return Result(ok, pass_=STYLES, fail=STYLES,
                  hint="Заголовки потеряли стили: попросите не пересобирать документ заново, "
                       "а править копию исходного файла.")


MEMO_LINE = "Памятка на месте и называет все шесть пунктов"


@check.criterion(MEMO_LINE)
def _():
    path = ROOT / MEMO
    if not path.exists():
        return Result(False, fail=MEMO_LINE, hint="Памятки нет: шаг ❺ практики.")
    text = path.read_bytes().decode("utf-8", errors="replace")
    missing = [c for c in MEMO_CLAUSES
               if not re.search(r"(?<![\d.])" + re.escape(c) + r"(?!\d)", text)]
    return Result(not missing, pass_=MEMO_LINE, fail=MEMO_LINE,
                  hint="В памятке не названы пункты: " + ", ".join(missing) + ".")


if __name__ == "__main__":
    check.run()
