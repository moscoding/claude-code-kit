"""Тесты недельной сводки scripts/report.py.

Запуск из корня проекта: python3 -m unittest
Тесты описывают правила из шапки scripts/report.py.
В задаче «почини отчёт» этот файл не меняется.
"""

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import report  # noqa: E402

MONDAY = date(2026, 5, 4)


def row(day, channel, spend, clicks=100, leads=5, revenue=10000):
    """Одна строка выгрузки в том виде, как её читает csv.DictReader."""
    return {"date": day, "source": "test", "campaign": "test",
            "channel": channel, "spend": spend, "clicks": str(clicks),
            "leads": str(leads), "revenue": str(revenue),
            "sessions": "0", "notes": ""}


class WeekTest(unittest.TestCase):
    def test_week_starts_on_monday(self):
        self.assertEqual(report.week_start(date(2026, 5, 10)), MONDAY,
                         "Воскресенье 10 мая относится к неделе с понедельника 4 мая")

    def test_sunday_is_in_week(self):
        self.assertTrue(report.in_week(date(2026, 5, 10), MONDAY),
                        "Воскресенье 10 мая должно входить в неделю 4–10 мая")

    def test_next_monday_is_not_in_week(self):
        self.assertFalse(report.in_week(date(2026, 5, 11), MONDAY),
                         "Понедельник 11 мая уже следующая неделя")


class ChannelTest(unittest.TestCase):
    def test_labels_ignore_case(self):
        rows = [row("2026-05-04", "search", "1000", leads=4),
                row("2026-05-05", "Search", "1000", leads=4),
                row("2026-05-06", "SEARCH", "1000", leads=2)]
        summary = report.summarize_week(rows, MONDAY)
        self.assertEqual([item["channel"] for item in summary], ["search"],
                         "search, Search и SEARCH — один канал search")
        self.assertEqual(summary[0]["leads"], 10)


class SpendTest(unittest.TestCase):
    def test_empty_spend_is_unknown(self):
        rows = [row("2026-05-06", "organic", "", leads=7)]
        item = report.summarize_week(rows, MONDAY)[0]
        self.assertIsNone(item["spend"], "Пустой spend — расход неизвестен, а не 0")
        self.assertIsNone(item["cpl"], "CPL с неизвестным расходом не считается")
        self.assertNotEqual(item["note"], "", "Нужна причина, почему метрик нет")

    def test_known_spend_metrics(self):
        rows = [row("2026-05-04", "search", "6000", clicks=500, leads=20, revenue=30000),
                row("2026-05-05", "search", "4000", clicks=500, leads=20, revenue=20000)]
        item = report.summarize_week(rows, MONDAY)[0]
        self.assertEqual(item["spend"], 10000)
        self.assertEqual(item["cpc"], 10.0)
        self.assertEqual(item["cpl"], 250.0)
        self.assertEqual(item["roas"], 5.0)


class FileTest(unittest.TestCase):
    def test_week_totals_on_training_file(self):
        rows = report.read_rows(ROOT / "inputs" / "campaigns-weeks.csv")
        summary = report.summarize(rows)
        leads = {}
        for item in summary:
            leads[item["week"]] = leads.get(item["week"], 0) + item["leads"]
        self.assertEqual(leads, {"2026-05-04": 111, "2026-05-11": 122,
                                 "2026-05-18": 110},
                         "Лиды по неделям не сходятся с контрольными числами")
        self.assertEqual(len(summary), 17, "В сводке должно быть 17 строк")


if __name__ == "__main__":
    unittest.main()
