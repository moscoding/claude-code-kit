"""Приёмочный тест задачи «Показать дату обновления на странице статуса».

Файл из набора claude-code-kit. Не меняйте его: проверки набора
сравнивают его с оригиналом.
"""
import html
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_page(date_text):
    """Собирает страницу в копии проекта с заданной датой и возвращает её текст."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "launch-kit"
        shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "venv"))
        (work / "inputs" / "status-date.txt").write_text(date_text + "\n", encoding="utf-8")
        res = subprocess.run([sys.executable, "scripts/build_status.py"], cwd=work,
                             capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            raise AssertionError("scripts/build_status.py завершился с ошибкой:\n" + res.stderr[-2000:])
        page = (work / "outputs" / "status.html").read_text(encoding="utf-8")
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    return " ".join(text.split())


class StatusDateTest(unittest.TestCase):
    longMessage = False

    def test_date_from_file(self):
        """Дата из inputs/status-date.txt видна на странице в формате ДД.ММ.ГГГГ."""
        self.assertIn("Обновлено: 15.05.2026", build_page("2026-05-15"),
                      "на странице нет строки «Обновлено: 15.05.2026» при дате 2026-05-15 в файле")

    def test_date_follows_file(self):
        """Другая дата в файле — другая дата на странице: дата не зашита в скрипт."""
        page = build_page("2026-05-22")
        self.assertIn("Обновлено: 22.05.2026", page,
                      "при дате 2026-05-22 в файле на странице нет «Обновлено: 22.05.2026»")
        self.assertNotIn("Обновлено: 15.05.2026", page,
                         "при дате 2026-05-22 страница всё ещё пишет 15.05.2026: дата зашита в скрипт")


if __name__ == "__main__":
    unittest.main()
