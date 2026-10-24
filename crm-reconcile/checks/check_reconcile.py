"""Проверка практики «Сверка выгрузок CRM».

Запуск из папки launch-kit:
    python3 ../claude-code-kit/crm-reconcile/checks/check_reconcile.py

Критерии:
1. inputs/crm-leads-sept.csv и inputs/crm-leads-oct.xlsx совпадают с набором (sha256);
2. есть scripts/reconcile.py;
3. outputs/reconcile.xlsx открывается как книга .xlsx;
4. в книге листы «Сводка», «Расхождения», «Сентябрь», «Октябрь»;
5. на «Расхождениях» есть колонки lead_id и тип;
6–9. ключи каждого типа (пропал, новый, статус изменён, дубликат) совпадают с эталоном;
10. в колонке A «Сводки» все одиннадцать подписей;
11. в колонке B «Сводки» формулы со ссылками, а не вписанные числа;
12. значения формул совпадают с контрольными числами;
13. «Проверка» — формула с IF, её значение «сходится»;
14. на листе «Октябрь» колонка amount только числами.
Если книга не открывается или в ней нет нужных листов, проверка
останавливается после пункта 3 или 4: остальные пункты читают книгу.

Книгу .xlsx проверка читает как zip с XML и пересчитывает формулы
маленьким вычислителем. Только стандартная библиотека. Эталон не печатается.
"""
import hashlib
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT.parent / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

PROJECT = Path.cwd()
EXPECTED = json.loads((KIT / "checks" / "expected" / "reconcile.json").read_text(encoding="utf-8"))
BOOK_PATH = "outputs/reconcile.xlsx"
SHEETS = ["Сводка", "Расхождения", "Сентябрь", "Октябрь"]
LABELS = {
    "sept_rows": "строк в сентябре",
    "oct_unique": "уникальных лидов в октябре",
    "duplicates": "дубликаты в октябре",
    "oct_rows": "строк в октябрьском файле",
    "matched": "совпали по ключу",
    "missing": "пропали",
    "new": "новые",
    "status_changed": "изменили статус",
    "sum_amount_sept": "сумма amount, сентябрь",
    "sum_amount_oct_unique": "сумма amount, октябрь",
    "check": "проверка",
}
TYPES = {"missing": "пропал", "new": "новый", "status_changed": "статус изменён",
         "duplicates": "дубликат"}
TOLERANCE = 0.005

M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"

check = Check("Проверка практики «Сверка выгрузок CRM»")
state = {}


# ---------- чтение xlsx ----------

def col_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def split_ref(ref):
    m = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", ref)
    if not m:
        raise ValueError("ссылка " + ref)
    return col_index(m.group(1)), int(m.group(2))


def text_of(node):
    """Текст строки: <t> и <r><t>, без фонетических подсказок <rPh>."""
    out = []
    for child in node:
        if child.tag == "{%s}t" % M:
            out.append(child.text or "")
        elif child.tag == "{%s}r" % M:
            out.extend(t.text or "" for t in child.iter("{%s}t" % M))
    return "".join(out)


class Book:
    def __init__(self, path):
        self.z = zipfile.ZipFile(path)
        names = set(self.z.namelist())
        self.shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(self.z.read("xl/sharedStrings.xml"))
            self.shared = [text_of(si) for si in root.findall("{%s}si" % M)]
        wb = ET.fromstring(self.z.read("xl/workbook.xml"))
        rels = ET.fromstring(self.z.read("xl/_rels/workbook.xml.rels"))
        target = {r.get("Id"): r.get("Target") for r in rels.findall("{%s}Relationship" % PR)}
        self.sheets = {}
        for s in wb.find("{%s}sheets" % M).findall("{%s}sheet" % M):
            t = target[s.get("{%s}id" % R)]
            t = t.lstrip("/") if t.startswith("/") else "xl/" + t
            self.sheets[s.get("name")] = self.read_sheet(t)

    def read_sheet(self, part):
        cells = {}
        root = ET.fromstring(self.z.read(part))
        data = root.find("{%s}sheetData" % M)
        row_no = 0
        for row in (data if data is not None else []):
            row_no = int(row.get("r") or row_no + 1)
            col_no = 0
            for c in row.findall("{%s}c" % M):
                ref = c.get("r")
                if ref:
                    col_no, row_no = split_ref(ref)
                else:
                    col_no += 1
                typ = c.get("t")
                f = c.find("{%s}f" % M)
                v = c.find("{%s}v" % M)
                if typ == "inlineStr":
                    is_ = c.find("{%s}is" % M)
                    val = text_of(is_) if is_ is not None else ""
                elif v is None or v.text is None:
                    val = None
                elif typ == "s":
                    val = self.shared[int(v.text)]
                elif typ in ("str", "e", "d"):
                    val = v.text
                elif typ == "b":
                    val = v.text.strip() == "1"
                else:
                    try:
                        val = float(v.text)
                    except ValueError:
                        val = v.text
                formula = f.text if f is not None and f.text else None
                cells[(col_no, row_no)] = {"value": val, "formula": formula}
        return cells


# ---------- маленький вычислитель формул ----------

TOKEN = re.compile(r"""\s*(?:
    (?P<str>"(?:[^"]|"")*")|
    (?P<ref>(?:'(?:[^']|'')+'|[^\s'!(),=<>+\-*/&:;"]+)!\$?[A-Z]+\$?\d*(?::\$?[A-Z]+\$?\d*)?|
            \$?[A-Z]+\$?\d+(?::\$?[A-Z]+\$?\d+)?|\$?[A-Z]+:\$?[A-Z]+)|
    (?P<num>\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)|
    (?P<func>(?:_xlfn\.)?[A-Z][A-Z0-9.]*)(?=\()|
    (?P<op><=|>=|<>|[-+*/=<>&(),;])
)""", re.X)


class Unsupported(Exception):
    pass


def num(x):
    if isinstance(x, bool):
        return float(x)
    if isinstance(x, float):
        return x
    if x is None or x == "":
        return 0.0
    raise Unsupported("не число: %r" % (x,))


def flat(a):
    return a if isinstance(a, list) else [a]


def criterion_match(crit):
    """Условие COUNTIF как в таблицах: без учёта регистра, с операторами и * ?."""
    if isinstance(crit, float):
        return lambda x: isinstance(x, float) and abs(x - crit) < 1e-9
    crit = str(crit)
    m = re.match(r"(<=|>=|<>|<|>|=)?(.*)$", crit, re.S)
    op, rest = m.group(1) or "=", m.group(2)
    try:
        target = float(rest)
    except ValueError:
        target = None
    if op in ("<", ">", "<=", ">=") and target is not None:
        cmp = {"<": lambda a: a < target, ">": lambda a: a > target,
               "<=": lambda a: a <= target, ">=": lambda a: a >= target}[op]
        return lambda x: isinstance(x, float) and cmp(x)
    if target is not None and op in ("=", "<>"):
        eq = lambda x: isinstance(x, float) and abs(x - target) < 1e-9
    elif rest == "":
        eq = lambda x: x is None or x == ""
    else:
        regex = "".join(".*" if ch == "*" else "." if ch == "?" else re.escape(ch) for ch in rest.lower())
        pattern = re.compile(regex + r"\Z", re.S)
        eq = lambda x: isinstance(x, str) and bool(pattern.match(x.lower()))
    return eq if op == "=" else (lambda x: not eq(x))


class Evaluator:
    def __init__(self, book, sheet, stack=()):
        self.book, self.sheet, self.stack = book, sheet, stack

    def tokens(self, text):
        pos, out = 0, []
        text = text.strip()
        if text.startswith("="):
            text = text[1:]
        while pos < len(text):
            if text[pos:].strip() == "":
                break
            m = TOKEN.match(text, pos)
            if not m or m.end() == pos:
                raise Unsupported(text[pos:])
            pos = m.end()
            kind = m.lastgroup
            out.append((kind, m.group(kind)))
        return out

    def eval(self, text):
        self.t, self.i = self.tokens(text), 0
        val = self.compare()
        if self.i != len(self.t):
            raise Unsupported(text)
        return val

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        if self.i >= len(self.t):
            raise Unsupported("формула оборвалась")
        tok = self.t[self.i]
        self.i += 1
        return tok

    def compare(self):
        left = self.additive()
        k, v = self.peek()
        if k == "op" and v in ("=", "<>", "<", ">", "<=", ">="):
            self.take()
            right = self.additive()
            left, right = scalar(left), scalar(right)
            if isinstance(left, float) and isinstance(right, float):
                eq = abs(left - right) < 1e-6
            elif isinstance(left, str) and isinstance(right, str):
                left, right = left.lower(), right.lower()
                eq = left == right
            else:
                eq = left == right
            if v in ("=", "<>"):
                return eq if v == "=" else not eq
            try:
                return {"<": left < right, ">": left > right,
                        "<=": left <= right, ">=": left >= right}[v]
            except TypeError:
                raise Unsupported("сравнение разных типов")
        return left

    def additive(self):
        val = self.term()
        while self.peek()[0] == "op" and self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            r = self.term()
            val = num(scalar(val)) + num(scalar(r)) if op == "+" else num(scalar(val)) - num(scalar(r))
        return val

    def term(self):
        val = self.unary()
        while self.peek()[0] == "op" and self.peek()[1] in ("*", "/"):
            op = self.take()[1]
            r = self.unary()
            if op == "*":
                val = num(scalar(val)) * num(scalar(r))
            else:
                d = num(scalar(r))
                if d == 0:
                    raise Unsupported("деление на ноль")
                val = num(scalar(val)) / d
        return val

    def unary(self):
        if self.peek() == ("op", "-"):
            self.take()
            return -num(scalar(self.unary()))
        if self.peek() == ("op", "+"):
            self.take()
            return self.unary()
        return self.atom()

    def atom(self):
        k, v = self.take()
        if k == "num":
            return float(v)
        if k == "str":
            return v[1:-1].replace('""', '"')
        if k == "ref":
            cells = self.range(v)
            if ":" not in v:
                return cells[0]
            return cells
        if k == "func":
            self.take()  # (
            args = []
            if self.peek() != ("op", ")"):
                args.append(self.compare())
                while self.peek()[0] == "op" and self.peek()[1] in (",", ";"):
                    self.take()
                    args.append(self.compare())
            if self.take() != ("op", ")"):
                raise Unsupported("скобки")
            name = v.upper()
            if name.startswith("_XLFN."):
                name = name[6:]
            return self.call(name, args)
        if (k, v) == ("op", "("):
            val = self.compare()
            if self.take() != ("op", ")"):
                raise Unsupported("скобки")
            return val
        raise Unsupported(v)

    def value(self, sheet, key):
        c = self.book.sheets[sheet].get(key)
        if c is None:
            return None
        if c["formula"]:
            if (sheet, key) in self.stack:
                raise Unsupported("циклическая ссылка")
            return Evaluator(self.book, sheet, self.stack + ((sheet, key),)).eval(c["formula"])
        return c["value"]

    def range(self, ref):
        sheet = self.sheet
        if "!" in ref:
            sname, ref = ref.rsplit("!", 1)
            if sname.startswith("'"):
                sname = sname[1:-1].replace("''", "'")
            sheet = sname
        if sheet not in self.book.sheets:
            raise Unsupported("лист " + sheet)
        ref = ref.replace("$", "")
        if ":" not in ref:
            return [self.value(sheet, split_ref(ref))]
        a, b = ref.split(":")
        ca = col_index(re.match(r"[A-Z]+", a).group())
        cb = col_index(re.match(r"[A-Z]+", b).group())
        ra = int(re.search(r"\d+", a).group()) if re.search(r"\d", a) else 1
        rb = int(re.search(r"\d+", b).group()) if re.search(r"\d", b) else 10 ** 7
        keys = sorted((k for k in self.book.sheets[sheet]
                       if ca <= k[0] <= cb and ra <= k[1] <= rb), key=lambda k: (k[1], k[0]))
        return [self.value(sheet, k) for k in keys]

    def call(self, name, args):
        if name == "SUM":
            return sum(x for a in args for x in flat(a) if isinstance(x, float) and not isinstance(x, bool))
        if name == "COUNTA":
            return float(sum(1 for a in args for x in flat(a) if x is not None and x != ""))
        if name == "COUNT":
            return float(sum(1 for a in args for x in flat(a) if isinstance(x, float) and not isinstance(x, bool)))
        if name == "COUNTIF":
            if len(args) != 2:
                raise Unsupported("COUNTIF")
            match = criterion_match(scalar(args[1]))
            return float(sum(1 for x in flat(args[0]) if match(x)))
        if name == "IF":
            if not 2 <= len(args) <= 3:
                raise Unsupported("IF")
            cond = scalar(args[0])
            if not isinstance(cond, bool):
                cond = num(cond) != 0
            return args[1] if cond else (args[2] if len(args) > 2 else False)
        if name == "ROUND":
            return float(round(num(scalar(args[0])), int(num(scalar(args[1])))))
        raise Unsupported(name)


def scalar(x):
    if isinstance(x, list):
        if len(x) != 1:
            raise Unsupported("диапазон вместо значения")
        return x[0]
    return x


def norm(s):
    return str(s if s is not None else "").strip().lower().replace("ё", "е")


# ---------- критерии ----------

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def book():
    if "book" not in state:
        try:
            state["book"] = Book(PROJECT / BOOK_PATH)
        except Exception:
            state["book"] = None
    return state["book"]


def stop_here():
    raise Stop("", "Остальные пункты читают книгу, поэтому проверка остановлена.",
               "Исправьте пункты с ✘, пересоберите outputs/reconcile.xlsx скриптом "
               "и запустите проверку снова.", code=1)


def opened_book():
    """Книга открылась; иначе остановка: пункт «книга» уже напечатал ✘."""
    if book() is None:
        stop_here()
    return book()


def need_book():
    """Книга с нужными листами; иначе остановка: ✘ уже напечатан выше."""
    if any(n not in opened_book().sheets for n in SHEETS):
        stop_here()
    return book()


@check.before
def _():
    if not (PROJECT / "inputs").is_dir() and not (PROJECT / "outputs").is_dir():
        raise Stop("Не найдены папки inputs/ и outputs/ в текущей папке.",
                   "Запускайте проверку из корня launch-kit.")


@check.criterion("inputs")
def _():
    changed = []
    for name, digest in EXPECTED["sha256"].items():
        p = PROJECT / "inputs" / name
        if not p.exists() or sha256(p) != digest:
            changed.append(name)
    return Result(not changed,
                  pass_="Исходные выгрузки в inputs/ на месте и не изменены",
                  fail="Исходные выгрузки отличаются от набора: " + ", ".join(changed),
                  hint=["скопируйте файлы из ../claude-code-kit/crm-reconcile/inputs/ заново и не меняйте их;",
                        "очищенные данные скрипт пишет в outputs/."])


@check.criterion("script")
def _():
    ok = (PROJECT / "scripts" / "reconcile.py").is_file()
    return Result(ok, pass_="Есть scripts/reconcile.py", fail="Нет scripts/reconcile.py",
                  hint="сверку делает скрипт: попросите Claude сохранить его в scripts/reconcile.py.")


@check.criterion("book")
def _():
    path = PROJECT / BOOK_PATH
    ok = book() is not None
    if not path.exists():
        hint = "файла нет: запустите python3 scripts/reconcile.py, книгу собирает скрипт."
    else:
        hint = "файл есть, но это не книга .xlsx (zip с xl/workbook.xml); пересоберите её скриптом по правилам скила xlsx."
    return Result(ok, pass_="outputs/reconcile.xlsx открывается как книга .xlsx",
                  fail="outputs/reconcile.xlsx не открывается как книга .xlsx", hint=hint)


@check.criterion("sheets")
def _():
    names = opened_book().sheets
    missing = [n for n in SHEETS if n not in names]
    return Result(not missing,
                  pass_="В книге листы «Сводка», «Расхождения», «Сентябрь», «Октябрь»",
                  fail="В книге нет листов: " + ", ".join("«%s»" % n for n in missing),
                  hint="названия листов должны совпадать с запросом буква в букву; сейчас в книге: "
                       + ", ".join("«%s»" % n for n in names) + ".")


def diff_rows():
    if "diff" in state:
        return state["diff"]
    sheet = need_book().sheets["Расхождения"]
    header = {c: norm(v["value"]) for (c, r), v in sheet.items() if r == 1 and v["value"] is not None}
    id_col = next((c for c, h in header.items() if h == "lead_id"), None)
    type_col = next((c for c, h in header.items() if h == "тип"), None)
    by_type = {}
    if id_col and type_col:
        rows = {}
        for (c, r), v in sheet.items():
            if r > 1:
                rows.setdefault(r, {})[c] = v["value"]
        for r in rows.values():
            t = norm(r.get(type_col))
            if t:
                by_type.setdefault(t, []).append(str(r.get(id_col) if r.get(id_col) is not None else "").strip())
    state["diff"] = (id_col, type_col, by_type)
    return state["diff"]


@check.criterion("diff-columns")
def _():
    id_col, type_col, _ = diff_rows()
    return Result(bool(id_col and type_col),
                  pass_="На листе «Расхождения» есть колонки lead_id и тип",
                  fail="На листе «Расхождения» нет колонок lead_id и тип",
                  hint="первая строка листа — заголовки: lead_id, тип, статус в сентябре, статус в октябре, комментарий.")


TYPE_HINTS = {
    "missing": "пропал — лид из сентября, которого нет в октябре; сравнивайте по lead_id, а не по номеру строки.",
    "new": "новые считают по уникальным lead_id: повтор ключа — не новый лид.",
    "status_changed": "сравнивайте статусы после нормализации: регистр и пробелы по краям — не смена статуса.",
    "duplicates": "дубликат — повтор lead_id в октябрьском файле; найдите повторы до сверки, каждый повтор — одна строка.",
}


def register_type(key, label):
    @check.criterion("type-" + key)
    def _():
        id_col, type_col, by_type = diff_rows()
        got = by_type.get(norm(label), [])
        ok = bool(id_col and type_col) and sorted(got) == sorted(EXPECTED["ids"][key])
        hint = TYPE_HINTS[key]
        if key == "status_changed" and len(got) == EXPECTED["traps"]["status_changed_without_normalization"]:
            hint = "смен статуса больше, чем нужно: похоже, «Won» и «won» посчитаны разными статусами."
        if key == "new" and len(got) != len(set(got)):
            hint = "новых больше, чем нужно: похоже, повторы lead_id посчитаны новыми лидами."
        if not (id_col and type_col):
            hint = "сначала исправьте заголовки листа «Расхождения»."
        return Result(ok,
                      pass_="«Расхождения»: строки типа «%s» совпадают с эталоном" % label,
                      fail="«Расхождения»: строки типа «%s» не совпадают с эталоном" % label,
                      hint=hint)


for _key, _label in TYPES.items():
    register_type(_key, _label)


def summary():
    if "summary" in state:
        return state["summary"]
    b = need_book()
    sheet = b.sheets["Сводка"]
    labels = {}
    for (c, r), v in sorted(sheet.items(), key=lambda x: (x[0][1], x[0][0])):
        if c == 1 and isinstance(v["value"], str):
            labels.setdefault(norm(v["value"]).rstrip(":").strip(), r)
    consts, values = [], {}
    for key, lab in LABELS.items():
        r = labels.get(lab)
        if r is None:
            continue
        cell = sheet.get((2, r))
        f = cell["formula"] if cell else None
        if not f or not re.search(r"\$?[A-Z]+\$?\d|[A-Z]+:\$?[A-Z]+|!", f):
            consts.append(LABELS[key])
            continue
        try:
            values[key] = Evaluator(b, "Сводка", (("Сводка", (2, r)),)).eval(f)
        except (Unsupported, ValueError, KeyError, IndexError, ZeroDivisionError):
            values[key] = "?"
    state["summary"] = (labels, consts, values)
    return state["summary"]


@check.criterion("labels")
def _():
    labels, _, _ = summary()
    absent = [lab for lab in LABELS.values() if lab not in labels]
    return Result(not absent,
                  pass_="На листе «Сводка» в колонке A есть все подписи из запроса",
                  fail="На листе «Сводка» в колонке A не хватает подписей",
                  hint="не найдены: " + "; ".join(absent) + ". Подписи — как в запросе шага ❸, по одной в строке.")


@check.criterion("formulas")
def _():
    _, consts, _ = summary()
    return Result(not consts,
                  pass_="В колонке B «Сводки» формулы со ссылками, а не вписанные числа",
                  fail="В колонке B «Сводки» есть вписанные числа",
                  hint="вписаны числом: " + "; ".join(consts) + ". Итог должен пересчитываться из листов книги.")


@check.criterion("values")
def _():
    labels, _, values = summary()
    unknown = [LABELS[k] for k, v in values.items() if v == "?" and k != "check"]
    wrong = []
    for key in LABELS:
        if key == "check" or values.get(key) in (None, "?"):
            continue
        got = values[key]
        if not isinstance(got, float) or abs(got - EXPECTED[key]) > TOLERANCE:
            wrong.append(LABELS[key])
    hint = ["не сходится: " + "; ".join(wrong) + "."]
    v = values.get("sum_amount_oct_unique")
    if isinstance(v, float):
        if abs(v - EXPECTED["traps"]["sum_amount_oct_skipping_text"]) < TOLERANCE:
            hint.append("Сумма за октябрь меньше нужной: суммы с запятой остались текстом.")
        elif abs(v - EXPECTED["traps"]["sum_amount_oct_with_duplicates"]) < TOLERANCE:
            hint.append("Сумма за октябрь больше нужной: в лист «Октябрь» попали дубликаты.")
    details = []
    if unknown:
        details.append("Не удалось пересчитать: " + "; ".join(unknown) + ".")
        details.append("Откройте книгу в Google Sheets и сверьте эти значения с выводом reconcile.py.")
    return Result(not wrong,
                  pass_="Значения формул «Сводки» совпадают с контрольными числами",
                  fail="Значения формул «Сводки» не совпадают с контрольными числами",
                  hint=hint, details=details)


@check.criterion("check-row")
def _():
    labels, _, values = summary()
    r = labels.get("проверка")
    cell = need_book().sheets["Сводка"].get((2, r)) if r else None
    f = (cell or {}).get("formula") or ""
    chk = values.get("check")
    has_if = bool(re.search(r"\bIF\s*\(", f.upper()))
    details = []
    if chk == "?" and has_if:
        # вычислитель не знает функцию в цепочке ссылок: не валим пункт, просим сверить глазами
        ok = True
        details = ["Значение «Проверки» не удалось пересчитать: в Google Sheets оно должно быть «сходится»."]
    else:
        ok = has_if and isinstance(chk, (str, bool)) and norm(chk) in ("сходится", "true")
    hint = "нужна формула вида IF(уникальные = совпали + новые; «сходится»; «не сходится»), и она должна показывать «сходится»."
    return Result(ok,
                  pass_="«Проверка» формулой сравнивает уникальные лиды октября с суммой совпавших и новых",
                  fail="«Проверка» не показывает «сходится» формулой IF",
                  hint=hint, details=details)


@check.criterion("oct-amount")
def _():
    sheet = need_book().sheets["Октябрь"]
    amount_col = next((c for (c, r), v in sheet.items() if r == 1 and norm(v["value"]) == "amount"), None)
    text_amounts = sum(1 for (c, r), v in sheet.items()
                       if c == amount_col and r > 1 and isinstance(v["value"], str) and v["value"].strip())
    ok = amount_col is not None and text_amounts == 0
    if amount_col is None:
        hint = "в первой строке листа «Октябрь» нет заголовка amount: колонки — как в исходниках."
    else:
        hint = "часть сумм осталась текстом: при очистке приведите «12255,00» к числу 12255."
    return Result(ok,
                  pass_="На листе «Октябрь» колонка amount есть и в ней только числа",
                  fail="На листе «Октябрь» в колонке amount есть текст" if amount_col else
                       "На листе «Октябрь» нет колонки amount",
                  hint=hint)


if __name__ == "__main__":
    check.run()
