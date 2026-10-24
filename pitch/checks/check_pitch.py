#!/usr/bin/env python3
"""Автопроверка практики «Веб-питч для заказчика». Запуск из корня репозитория питча:

    python3 ../claude-code-kit/pitch/checks/check_pitch.py [--site ПАПКА]

Питч — одна страница index.html (в корне репозитория или в docs/), слайды — элементы <section>.
Скрипт только читает файлы: ничего не меняет и не ходит в сеть.
"""
import pathlib
import re
import sys

KIT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KIT_ROOT / "kitlib"))
from check import Check, Result, Stop  # noqa: E402
import sitecheck as sc  # noqa: E402

EXP = sc.load_expected(__file__, "pitch.json")
check = Check("Проверка практики «Веб-питч для заказчика»")
ctx = {}
BREAK = re.compile(r"^(page-)?break-(before|after)$")
BREAK_VALUES = {"page", "always", "left", "right", "recto", "verso"}


def short(items, n=5):
    more = len(items) - n
    return items[:n] + ([f"… и ещё {more}"] if more > 0 else [])


@check.before
def _setup():
    args = sys.argv[1:]
    explicit = args[args.index("--site") + 1] if "--site" in args and len(args) > args.index("--site") + 1 else None
    site = sc.Site.find(pathlib.Path.cwd(), explicit)
    if site is None:
        raise Stop("Нет index.html ни в корне репозитория, ни в docs/.",
                   "Запускайте проверку из корня репозитория питча, когда в нём есть страница со слайдами.")
    ctx["site"] = site
    ctx["page"] = site.page("index.html")
    print(f"Питч: {'' if site.root == site.repo else site.root.name + '/'}index.html · "
          f"слайдов: {len(ctx['page'].sections)} · картинок: {len(site.images())}")
    print()


@check.criterion("Слайды")
def _slides():
    page = ctx["page"]
    n, need = len(page.sections), EXP["min_slides"]
    no_head = [f"слайд {i} (строка {s['line']})" for i, s in enumerate(page.sections, 1) if not s["headings"]]
    others = [p.rel for p in ctx["site"].pages if p.rel.lower() not in ("index.html", "404.html")]
    if n < need:
        return Result(False, fail=f"Слайдов-секций в index.html: {n}, нужно хотя бы {need}",
                      details=[f"другие страницы: {', '.join(others)}"] if others else [],
                      hint="питч — одна страница, каждый слайд — <section> с заголовком. Одна ссылка открывает весь "
                           "питч, и он печатается в PDF целиком.")
    return Result(not no_head, pass_=f"Питч — одна страница, слайдов: {n}, у каждого заголовок",
                  fail=f"Слайды без заголовка h1–h3: {len(no_head)}", details=short(no_head),
                  hint="заголовок — главная мысль слайда. По заголовкам питч читают скринридер и PDF-закладки.")


@check.criterion("Клавиши")
def _keys():
    js = ctx["site"].js_sources()
    listener = [o for o, t in js if re.search(r"""addEventListener\(\s*['"]key(down|up)['"]|onkey(down|up)""", t)]
    keys = [o for o, t in js if re.search(r"Arrow(Right|Left|Down|Up)|PageDown|PageUp|keyCode\s*===?\s*3[79]", t)]
    ok = bool(listener) and bool(keys)
    fail = "Нет обработчика клавиш" if not listener else "Обработчик клавиш не знает стрелок и PageUp/PageDown"
    return Result(ok, pass_="Слайды листаются с клавиатуры", fail=fail,
                  hint="на встрече питч листают стрелками или пультом-кликером (он шлёт PageUp/PageDown): "
                       "нужен обработчик keydown для ArrowRight/ArrowLeft и PageDown/PageUp.")


@check.criterion("Печать")
def _print():
    site = ctx["site"]
    media_links = site.css_media_links()
    decls = site.css_decls()
    in_print = [d for d in decls if "print" in sc.at_media(d[2]) or "print" in media_links.get(d[0], "")]
    breaks = [d for d in in_print if BREAK.match(d[3]) and d[4].lower().split("!")[0].strip() in BREAK_VALUES]
    if not in_print:
        return Result(False, fail="Нет стилей для печати (@media print)",
                      hint="без них браузер режет слайды посередине страницы PDF. Нужен блок @media print, "
                           "где у каждого слайда break-after: page.")
    return Result(bool(breaks), pass_="Стили печати делят питч по одному слайду на страницу",
                  fail="В @media print нет разрыва страницы после слайда",
                  hint="добавьте в @media print для section: break-after: page (и page-break-after: always "
                       "для старых браузеров). Проверьте: Cmd+P → «Сохранить как PDF», страниц столько же, "
                       "сколько слайдов.")


@check.criterion("Вес картинок")
def _weight():
    heavy = sc.heavy_images(ctx["site"], EXP["max_image_kb"])
    return Result(not heavy, pass_=f"Ни одна картинка не тяжелее {EXP['max_image_kb']} КБ",
                  fail=f"Картинки тяжелее {EXP['max_image_kb']} КБ: {len(heavy)}", details=short(heavy),
                  hint="скриншот с Retina-экрана весит мегабайты: уменьшите до ширины слайда (около 1600 px) и "
                       "сохраните в JPEG или WebP. Питч откроют и с телефона в дороге.")


@check.criterion("alt")
def _alt():
    bad = sc.missing_alt(ctx["site"])
    return Result(not bad, pass_="У каждой картинки есть alt", fail=f"Картинки без описания: {len(bad)}",
                  details=short(bad),
                  hint="alt скриншота говорит, что на нём важно: «инбокс: обращения из чата и почты в одном "
                       "списке». Логотип — alt с названием компании.")


@check.criterion("Шаблонные строки")
def _placeholders():
    found = sc.placeholders(ctx["site"], EXP["placeholders_ci"], EXP["placeholders_cs"])
    return Result(not found, pass_="Шаблонных строк вроде «Lorem ipsum» и «TODO» нет",
                  fail=f"В питче остались шаблонные строки: {len(found)}", details=short(found),
                  hint="заказчик видит всё, включая комментарии в коде страницы: замените или уберите.")


@check.criterion("Мета-теги")
def _meta():
    bad = sc.meta_problems(ctx["site"], need_description=False)
    return Result(not bad, pass_="Есть title, og:title и og:image", fail="Не хватает мета-тегов",
                  details=short(bad),
                  hint="ссылку на питч пересылают в мессенджере: без og:title и og:image превью пустое. "
                       "og:image — полный адрес картинки на опубликованном сайте, начиная с https://.")


if __name__ == "__main__":
    check.run()
