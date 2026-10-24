"""Недельная сводка по рекламным каналам.

Вход:  inputs/campaigns-weeks.csv
Выход: outputs/weekly-summary.csv

Правила:
1. Неделя начинается в понедельник и заканчивается в воскресенье
   включительно.
2. Метки каналов сравниваются без учёта регистра и пробелов по краям:
   «Search», «SEARCH» и « search » — один канал search.
3. Пустой spend значит «расход неизвестен», а не ноль. Если у канала
   за неделю хотя бы один spend пустой, расход канала за эту неделю
   неизвестен: CPC, CPL и ROAS не считаются, в note пишется причина.
4. CPC = spend / clicks, CPL = spend / leads, ROAS = revenue / spend —
   только если знаменатель известен и больше нуля. Округление до 2 знаков.

Запуск из корня проекта: python3 scripts/report.py
"""

import csv
from datetime import date, timedelta
from pathlib import Path

INPUT = Path("inputs/campaigns-weeks.csv")
OUTPUT = Path("outputs/weekly-summary.csv")
FIELDS = ["week", "channel", "spend", "clicks", "leads", "revenue",
          "cpc", "cpl", "roas", "note"]
NO_SPEND_NOTE = "spend не указан: CPC, CPL и ROAS не считаются"


def read_rows(path):
    """Читает CSV и возвращает список строк-словарей."""
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def parse_date(text):
    """'2026-05-04' -> date(2026, 5, 4)."""
    return date.fromisoformat(text.strip())


def week_start(day):
    """Понедельник той недели, в которую попадает день."""
    return day - timedelta(days=day.weekday())


def in_week(day, start):
    """Входит ли день в неделю, которая начинается в понедельник start."""
    end = start + timedelta(days=6)
    return start <= day < end


def channel_key(label):
    """Метка канала для группировки."""
    return label


def parse_spend(text):
    """Расход из ячейки; None, если расход неизвестен."""
    return float(text or 0)


def ratio(numerator, denominator):
    """Деление с округлением; None, если считать нельзя."""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round(numerator / denominator, 2)


def summarize_week(rows, start):
    """Сводка по каналам за неделю, которая начинается в понедельник start."""
    totals = {}
    for row in rows:
        day = parse_date(row["date"])
        if not in_week(day, start):
            continue
        key = channel_key(row["channel"])
        t = totals.setdefault(key, {"spend": 0.0, "spend_known": True,
                                    "clicks": 0, "leads": 0, "revenue": 0.0})
        spend = parse_spend(row["spend"])
        if spend is None:
            t["spend_known"] = False
        else:
            t["spend"] += spend
        t["clicks"] += int(row["clicks"])
        t["leads"] += int(row["leads"])
        t["revenue"] += float(row["revenue"] or 0)

    result = []
    for key in sorted(totals):
        t = totals[key]
        spend = t["spend"] if t["spend_known"] else None
        result.append({
            "week": start.isoformat(),
            "channel": key,
            "spend": spend,
            "clicks": t["clicks"],
            "leads": t["leads"],
            "revenue": t["revenue"],
            "cpc": ratio(spend, t["clicks"]),
            "cpl": ratio(spend, t["leads"]),
            "roas": ratio(t["revenue"], spend),
            "note": "" if spend is not None else NO_SPEND_NOTE,
        })
    return result


def summarize(rows):
    """Сводки по всем неделям, которые встречаются в данных."""
    weeks = sorted({week_start(parse_date(r["date"])) for r in rows})
    summary = []
    for start in weeks:
        summary.extend(summarize_week(rows, start))
    return summary


def write_summary(summary, path):
    """Пишет сводку в CSV; неизвестные значения — пустые ячейки."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for item in summary:
            writer.writerow({k: ("" if item[k] is None else item[k])
                             for k in FIELDS})


def main():
    rows = read_rows(INPUT)
    summary = summarize(rows)
    write_summary(summary, OUTPUT)
    print(f"Строк во входе: {len(rows)}. Строк в сводке: {len(summary)}.")
    print(f"Сводка записана в {OUTPUT}")


if __name__ == "__main__":
    main()
