#!/usr/bin/env python3
"""Автопроверка практики «Сайт-портфолио». Запускается локально и в CI из корня репозитория сайта:

    python3 ../claude-code-kit/portfolio/checks/check_portfolio.py [--site ПАПКА]

Сайт ищется в корне репозитория, затем в docs/ (оба варианта публикации GitHub Pages из ветки).
Скрипт только читает файлы: ничего не меняет и не ходит в сеть.
"""
import pathlib
import re
import sys

KIT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KIT_ROOT / "kitlib"))
from check import Check, Result, Stop  # noqa: E402
import sitecheck as sc  # noqa: E402

EXP = sc.load_expected(__file__, "portfolio.json")
check = Check("Проверка практики «Сайт-портфолио»")
ctx = {}


def short(items, n=5):
    more = len(items) - n
    return items[:n] + ([f"… и ещё {more}"] if more > 0 else [])


@check.before
def _setup():
    args = sys.argv[1:]
    explicit = args[args.index("--site") + 1] if "--site" in args and len(args) > args.index("--site") + 1 else None
    cwd = pathlib.Path.cwd()
    site = sc.Site.find(cwd, explicit)
    if site is None:
        lines = ["Нет index.html ни в корне репозитория, ни в docs/.",
                 "Запускайте проверку из корня репозитория сайта, когда в нём есть главная страница."]
        if (cwd / "scripts" / "build_status.py").exists():
            lines.append("Похоже, это launch-kit: сайт-портфолио живёт в своём репозитории рядом с ним.")
        raise Stop(*lines)
    ctx["site"] = site
    where = "" if site.root == site.repo else site.root.name + "/"
    print(f"Сайт: {where}index.html · страниц: {len(site.pages)} · картинок: {len(site.images())}")
    print()


@check.criterion("Страницы")
def _pages():
    site = ctx["site"]
    cases = [p.rel for p in site.pages if p.rel.lower() not in ("index.html", "404.html")]
    need = EXP["min_case_pages"]
    return Result(len(cases) >= need,
                  pass_=f"Есть index.html и страницы кейсов: {len(cases)}",
                  fail=f"Страниц кейсов {len(cases)}, нужно хотя бы {need}",
                  hint="у каждой работы — своя страница с текстом кейса: на неё можно дать ссылку, "
                       "и поисковик видит её отдельно.")


@check.criterion("Мета-теги")
def _meta():
    bad = sc.meta_problems(ctx["site"])
    return Result(not bad, pass_="У каждой страницы есть title, description, og:title и og:image",
                  fail=f"Не хватает мета-тегов на страницах: {len(bad)}", details=short(bad),
                  hint="без них ссылка в мессенджере приходит без заголовка и картинки. og:image — полный адрес "
                       "картинки на опубликованном сайте, начиная с https://.")


@check.criterion("alt")
def _alt():
    bad = sc.missing_alt(ctx["site"])
    return Result(not bad, pass_="У каждой картинки есть alt", fail=f"Картинки без описания: {len(bad)}",
                  details=short(bad),
                  hint="alt описывает, что на картинке, словами: его читает скринридер и видит поисковик. "
                       "Для чисто декоративной картинки — aria-hidden=\"true\".")


@check.criterion("Вес картинок")
def _weight():
    heavy = sc.heavy_images(ctx["site"], EXP["max_image_kb"])
    return Result(not heavy, pass_=f"Ни одна картинка не тяжелее {EXP['max_image_kb']} КБ",
                  fail=f"Картинки тяжелее {EXP['max_image_kb']} КБ: {len(heavy)}", details=short(heavy),
                  hint="уменьшите по длинной стороне до 1600–2000 px и сожмите (JPEG качества около 80 или WebP). "
                       "Исходники в репозиторий не кладите: GitHub Pages публикует всё, что в нём лежит.")


@check.criterion("Форматы картинок")
def _formats():
    site = ctx["site"]
    icons = set()
    for page in site.pages:
        for a in page.rel_links("icon") + page.rel_links("apple-touch-icon"):
            target = site.resolve(page, a.get("href", ""))[0]
            if target:
                icons.add(target)
    allowed = set(EXP["allowed_raster"]) | {"svg"}
    bad = []
    for p in site.images():
        if p in icons:
            continue
        real = sc.sniff(p)
        by_ext = sc.EXT_FORMAT.get(p.suffix.lower())
        if by_ext and by_ext != real:
            bad.append(f"{site.rel(p)} — расширение {p.suffix}, а внутри {real.upper()}")
        elif real not in allowed:
            bad.append(f"{site.rel(p)} — {real.upper()}")
    names = ", ".join({"jpeg": "JPEG", "webp": "WebP", "avif": "AVIF"}.get(f, f.upper()) for f in EXP["allowed_raster"])
    return Result(not bad, pass_=f"Картинки в форматах {names} (векторные — SVG)",
                  fail=f"Картинки в неподходящем формате: {len(bad)}", details=short(bad),
                  hint=f"переведите их в {names}, а не просто переименуйте файл: проверка смотрит на содержимое. "
                       "Иконка сайта (favicon) может быть PNG или ICO.")


@check.criterion("Шаблонные строки")
def _placeholders():
    found = sc.placeholders(ctx["site"], EXP["placeholders_ci"], EXP["placeholders_cs"])
    return Result(not found, pass_="Шаблонных строк вроде «YOUR NAME», «Lorem ipsum» и «TODO» нет",
                  fail=f"На сайте остались шаблонные строки: {len(found)}", details=short(found),
                  hint="замените их настоящим текстом или уберите. Комментарии в HTML тоже видны всем: "
                       "«Просмотр кода страницы» их показывает.")


@check.criterion("Внутренние ссылки")
def _links():
    bad = ctx["site"].broken_links()
    return Result(not bad, pass_="Все внутренние ссылки ведут на существующие файлы",
                  fail=f"Битые внутренние ссылки: {len(bad)}", details=short(bad),
                  hint="пути — относительные (images/01.jpg, cases/bank.html) и с тем же регистром букв, "
                       "что у файла: на macOS Photo.jpg и photo.jpg — один файл, на GitHub Pages — разные.")


@check.criterion("Внешние ссылки")
def _external():
    bad = []
    for page in ctx["site"].pages:
        for a, line in page.find("a"):
            href = a.get("href", "")
            external = re.match(r"^(https?:)?//", href)
            if external and a.get("target", "").lower() == "_blank":
                rel = a.get("rel", "").lower().split()
                if "noopener" not in rel and "noreferrer" not in rel:
                    bad.append(f"{page.rel}:{line}: {href}")
    return Result(not bad, pass_="Внешние ссылки в новой вкладке открываются с rel=\"noopener\"",
                  fail=f"Внешние ссылки с target=\"_blank\" без rel=\"noopener\": {len(bad)}", details=short(bad),
                  hint="добавьте rel=\"noopener noreferrer\": открытая страница не получит доступ к вашей вкладке.")


@check.criterion("Телефон")
def _phone():
    site = ctx["site"]
    limit = EXP["max_fixed_width_px"]
    bad = [f"{p.rel}: нет <meta name=\"viewport\" content=\"width=device-width, …\">" for p in site.pages
           if "width=device-width" not in (p.meta("name", "viewport") or "").replace(" ", "").lower()]
    for origin, line, stack, prop, value in site.css_decls():
        if prop not in ("width", "min-width"):
            continue
        m = re.fullmatch(r"(\d+(?:\.\d+)?)px(\s*!important)?", value.lower())
        if not m or float(m.group(1)) <= limit:
            continue
        media = sc.at_media(stack)
        if "min-width" in media or "print" in media:
            continue
        bad.append(f"{origin}:{line}: {prop}: {value}")
    return Result(not bad, pass_=f"Есть viewport, фиксированной ширины больше {limit} px нет",
                  fail=f"Сайт не помещается в телефон шириной {limit} px: {len(bad)}", details=short(bad),
                  hint="вместо width: 1200px — max-width: 1200px и width: 100%; широкие правила кладите в "
                       "@media (min-width: …). Откройте сайт в браузере с шириной окна 375 px.")


@check.criterion("Звук")
def _autoplay():
    bad = []
    for page in ctx["site"].pages:
        for tag in ("video", "audio"):
            for a, line in page.find(tag):
                if "autoplay" in a and "muted" not in a:
                    bad.append(f"{page.rel}:{line}: <{tag} autoplay> без muted")
    return Result(not bad, pass_="Медиа с autoplay запускаются без звука", fail="Автозапуск со звуком",
                  details=short(bad),
                  hint="добавьте muted (и playsinline для iPhone) или уберите autoplay: звук включает посетитель.")


@check.criterion("Движение")
def _motion():
    site = ctx["site"]
    decls = site.css_decls()
    anim = [d for d in decls if d[3] in ("animation", "animation-name") and d[4].lower() not in ("none", "initial")
            and "prefers-reduced-motion" not in sc.at_media(d[2])]
    keyframes = any(re.search(r"@(-webkit-)?keyframes\b", text) for _, text in site.css_texts())
    unguarded = [d for d in anim if "no-preference" not in sc.at_media(d[2])]
    reduce_block = any("prefers-reduced-motion" in sc.at_media(d[2]) and "reduce" in sc.at_media(d[2])
                       and d[3].startswith(("animation", "transition")) for d in decls)
    js = site.js_sources()
    js_motion = [o for o, t in js if re.search(r"requestAnimationFrame|\.animate\(", t)]
    js_guard = any("prefers-reduced-motion" in t for _, t in js)
    bad = []
    if unguarded and not reduce_block:
        bad += [f"{o}:{line}: {p}: {v}" for o, line, _, p, v in unguarded]
    if js_motion and not js_guard:
        bad += [f"{o}: анимация в JS без проверки prefers-reduced-motion" for o in sorted(set(js_motion))]
    if not (anim or keyframes or js_motion):
        return Result(True, pass_="Анимаций нет, учитывать prefers-reduced-motion не нужно")
    return Result(not bad, pass_="Анимации учитывают prefers-reduced-motion",
                  fail="Анимации не учитывают «уменьшить движение»", details=short(bad),
                  hint="заверните анимации в @media (prefers-reduced-motion: no-preference) или отключите их в "
                       "@media (prefers-reduced-motion: reduce); в JS — проверка "
                       "matchMedia('(prefers-reduced-motion: reduce)').")


@check.criterion("Текст в HTML")
def _text():
    site = ctx["site"]
    bad = []
    for page in site.pages:
        if page.rel.lower() == "404.html":
            continue
        need = EXP["min_index_words"] if page.rel.lower() == "index.html" else EXP["min_case_words"]
        if len(page.words) < need:
            canvas = " (есть <canvas>)" if page.find("canvas") else ""
            bad.append(f"{page.rel}: {len(page.words)} слов в HTML, нужно {need}{canvas}")
    return Result(not bad, pass_="Основной текст лежит в HTML", fail="Текста в HTML мало", details=short(bad),
                  hint="поисковик, превью ссылки и скринридер читают HTML без запуска JS. Тексты о себе и кейсов "
                       "пишите в разметку, а canvas и анимацию кладите поверх.")


@check.criterion("CI")
def _workflow():
    site = ctx["site"]
    folder = site.repo / ".github" / "workflows"
    files = sorted(list(folder.glob("*.yml")) + list(folder.glob("*.yaml"))) if folder.is_dir() else []
    script = EXP["check_script"]
    good, seen = [], []
    for f in files:
        lines = [l for l in f.read_text(encoding="utf-8", errors="replace").splitlines() if not l.strip().startswith("#")]
        text = "\n".join(lines)
        if script in text:
            seen.append(f.name)
            if re.search(r"(^|[\s\[,{])pull_request(?!_target)\b", text, re.M):
                good.append(f.name)
    if good:
        return Result(True, pass_=f"Воркфлоу {good[0]} запускает проверку на каждый pull request")
    if seen:
        return Result(False, fail=f"Воркфлоу {seen[0]} запускает проверку, но не на pull_request",
                      hint="в разделе on: нужен pull_request, иначе PR сливают без проверки.")
    return Result(False, fail="В .github/workflows/ нет воркфлоу с проверкой сайта",
                  hint="скопируйте шаблон: ../claude-code-kit/portfolio/workflow/portfolio-check.yml → "
                       ".github/workflows/portfolio-check.yml.")


if __name__ == "__main__":
    check.run()
