"""Проверка разбора «Четыре фрагмента кода».

Запуск из папки launch-kit:
    python3 ../claude-code-kit/code-reading/checks/check_reading.py

Читает work/code-reading.md: по строке на фрагмент, вида «A: сеть».
Риски: сеть, удаление, установка, секрет; не больше двух на строку.
Эталон — checks/expected/answers.json, скрипт его не печатает.
Только стандартная библиотека.
"""
import json
import re
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT.parent / "kitlib"))
from check import Check, Result, Stop  # noqa: E402

ANSWERS_FILE = Path("work/code-reading.md")
LETTERS = {"A": "A", "B": "B", "C": "C", "D": "D",
           "А": "A", "В": "B", "С": "C", "Д": "D"}  # кириллические двойники
SYNONYMS = {
    "сеть": "сеть", "сетевой": "сеть", "отправка": "сеть", "интернет": "сеть",
    "удаление": "удаление", "удаляет": "удаление",
    "установка": "установка", "пакет": "установка", "pip": "установка",
    "секрет": "секрет", "токен": "секрет", "ключ": "секрет",
}
HINTS = {
    "A": "посмотрите на импорт и константу в начале фрагмента: что они делают за пределами расчёта.",
    "B": "посмотрите, что цикл делает с каждым найденным файлом и в каких папках он ищет.",
    "C": "посмотрите, что выполняется до строки import и откуда берётся этот код.",
    "D": "посмотрите, что лежит в константе в начале фрагмента и что с ней станет после коммита.",
}
EXPECTED = json.loads((KIT / "checks" / "expected" / "answers.json")
                      .read_text(encoding="utf-8"))

check = Check("Проверка разбора «Четыре фрагмента кода»")
parsed = {}


@check.before
def _():
    if not ANSWERS_FILE.exists():
        raise Stop("Нет файла work/code-reading.md.",
                   "Запишите ответы по строке на фрагмент, например «A: сеть»,",
                   "и запускайте проверку из корня launch-kit.")
    for line in ANSWERS_FILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*[-*]?\s*([A-DАВСД])\s*[:：.)]\s*(.+)$", line.strip())
        if not m:
            continue
        words = re.split(r"[,;/]|\s+и\s+", m.group(2).lower())
        risks = set()
        for word in words:
            word = word.strip(" .«»`*")
            if word in SYNONYMS:
                risks.add(SYNONYMS[word])
            elif word:
                risks.add("?" + word)
        parsed[LETTERS[m.group(1)]] = risks


@check.criterion("format")
def _():
    missing = [x for x in "ABCD" if x not in parsed]
    unknown = sorted({r[1:] for risks in parsed.values() for r in risks if r.startswith("?")})
    too_many = [x for x, risks in parsed.items() if len(risks) > 2]
    problems = []
    if missing:
        problems.append("нет строк для фрагментов: " + ", ".join(missing))
    if unknown:
        problems.append("слова не из списка: " + ", ".join(unknown))
    if too_many:
        problems.append("больше двух рисков в строках: " + ", ".join(too_many))
    return Result(not problems,
                  pass_="Ответы записаны для всех четырёх фрагментов",
                  fail="Файл ответов заполнен не по формату",
                  hint=problems + ["Формат: «A: сеть», риски — сеть, удаление, установка, секрет."])


def register(letter):
    @check.criterion(letter)
    def _():
        ok = EXPECTED[letter]["risk"] in parsed.get(letter, set())
        return Result(ok,
                      pass_=f"Фрагмент {letter}: главный риск назван",
                      fail=f"Фрагмент {letter}: главный риск не назван",
                      hint=HINTS[letter])


for item in "ABCD":
    register(item)

if __name__ == "__main__":
    check.run()
