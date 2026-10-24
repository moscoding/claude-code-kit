"""claude-code-kit · разбор статичного сайта для проверок practice portfolio/ и pitch/.

Только стандартная библиотека, Python 3.9+. Ничего не меняет на диске.

    from sitecheck import Site
    site = Site.find(Path.cwd())          # index.html в корне или в docs/
    site.pages, site.images(), site.css_decls(), site.js_sources(), site.broken_links()
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".github"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".bmp", ".tif", ".tiff", ".heic",
             ".heif", ".ico"}
TEXT_EXT = {".html", ".htm", ".js", ".mjs", ".json", ".xml", ".txt", ".webmanifest", ".css"}
RAW_TEXT = {"script", "style"}
HIDDEN = {"script", "style", "template", "head"}
WORD = re.compile(r"[^\W_]{2,}")


def load_expected(check_file: str, name: str) -> dict:
    return json.loads((Path(check_file).resolve().parent / "expected" / name).read_text(encoding="utf-8"))


def fmt_kb(size: int) -> str:
    return f"{size / 1024:.0f} КБ"


# --- HTML -------------------------------------------------------------------------------------

class Page(HTMLParser):
    def __init__(self, path: Path, rel: str):
        super().__init__(convert_charrefs=True)
        self.path, self.rel = path, rel
        self.source = path.read_text(encoding="utf-8", errors="replace")
        self.tags: list[tuple[str, dict, int]] = []
        self.title = ""
        self.words: list[str] = []
        self.styles: list[tuple[str, int]] = []
        self.scripts: list[tuple[str, int]] = []
        self.sections: list[dict] = []
        self._stack: list[str] = []
        self._section_depth = 0
        self._buf: list[str] = []
        self.feed(self.source)
        self.close()

    # разбор
    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v if v is not None else "") for k, v in attrs}
        self.tags.append((tag, a, self.getpos()[0]))
        if tag == "section" and not self._section_depth:
            self.sections.append({"line": self.getpos()[0], "headings": 0, "words": 0, "attrs": a})
        if tag == "section":
            self._section_depth += 1
        if tag in ("h1", "h2", "h3") and self._section_depth and self.sections:
            self.sections[-1]["headings"] += 1
        if tag in RAW_TEXT or tag in ("title", "template", "head"):
            self._stack.append(tag)
            self._buf = []

    def handle_startendtag(self, tag, attrs):
        a = {k.lower(): (v if v is not None else "") for k, v in attrs}
        self.tags.append((tag, a, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag == "section" and self._section_depth:
            self._section_depth -= 1
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
            text = "".join(self._buf)
            if tag == "title":
                self.title = " ".join(text.split())
            elif tag == "style":
                self.styles.append((text, self.getpos()[0]))
            elif tag == "script":
                self.scripts.append((text, self.getpos()[0]))
            self._buf = []

    def handle_data(self, data):
        if self._stack:
            self._buf.append(data)
            if any(t in HIDDEN for t in self._stack):
                return
        found = WORD.findall(data)
        self.words += found
        if self._section_depth and self.sections:
            self.sections[-1]["words"] += len(found)

    # доступ
    def find(self, tag):
        return [(a, line) for t, a, line in self.tags if t == tag]

    def meta(self, key, value):
        for a, _ in self.find("meta"):
            if a.get(key, "").strip().lower() == value:
                return a.get("content", "").strip()
        return None

    def rel_links(self, rel):
        return [a for a, _ in self.find("link") if rel in a.get("rel", "").lower().split()]

    def line_of(self, offset: int) -> int:
        return self.source.count("\n", 0, offset) + 1


# --- CSS ----------------------------------------------------------------------------------------

COMMENT = re.compile(r"/\*.*?\*/", re.S)


def css_decls(css: str, origin: str, base_line: int = 1, context=()):
    """Объявления CSS: (origin, строка, контекст @-правил, свойство, значение)."""
    out = []
    text = COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), css)
    stack = list(context)
    start = 0
    for i, ch in enumerate(text):
        if ch == "{":
            stack.append(" ".join(text[start:i].split()))
            start = i + 1
        elif ch in ";}":
            chunk = text[start:i]
            if ":" in chunk and stack and not stack[-1].startswith("@"):
                prop, _, value = chunk.partition(":")
                line = base_line + text.count("\n", 0, start + len(chunk) - len(chunk.lstrip()))
                out.append((origin, line, tuple(stack), prop.strip().lower(), " ".join(value.split())))
            if ch == "}" and stack:
                stack.pop()
            start = i + 1
    return out


def at_media(ctx) -> str:
    return " ".join(p.lower() for p in ctx if p.lower().startswith("@media"))


# --- сайт ---------------------------------------------------------------------------------------

class Site:
    def __init__(self, root: Path, repo: Path):
        self.root, self.repo = root, repo
        self._ls: dict[Path, set] = {}
        self.files = sorted(p for p in self._walk(root))
        self.pages = [Page(p, self.rel(p)) for p in self.files if p.suffix.lower() in (".html", ".htm")]

    @staticmethod
    def find(cwd: Path, explicit: str | None = None):
        repo = cwd
        res = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            repo = Path(res.stdout.strip())
        if explicit:
            root = (cwd / explicit).resolve()
            return Site(root, repo) if (root / "index.html").is_file() else None
        for cand in (repo, repo / "docs", cwd):
            if (cand / "index.html").is_file():
                return Site(cand.resolve(), repo)
        return None

    def _walk(self, d: Path):
        for entry in sorted(os.scandir(d), key=lambda e: e.name):
            if entry.is_dir(follow_symlinks=False):
                if entry.name not in SKIP_DIRS:
                    yield from self._walk(Path(entry.path))
            elif entry.is_file():
                yield Path(entry.path)

    def rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    def page(self, rel):
        return next((p for p in self.pages if p.rel == rel), None)

    def images(self):
        return [p for p in self.files if p.suffix.lower() in IMAGE_EXT]

    def text_files(self, exts=TEXT_EXT):
        return [p for p in self.files if p.suffix.lower() in exts]

    # CSS и JS
    def css_decls(self):
        decls = []
        for p in self.files:
            if p.suffix.lower() == ".css":
                decls += css_decls(p.read_text(encoding="utf-8", errors="replace"), self.rel(p))
        for page in self.pages:
            for text, line in page.styles:
                decls += css_decls(text, page.rel, line)
            for t, a, line in page.tags:
                if a.get("style"):
                    decls += css_decls(a["style"] + ";", f"{page.rel} (style у <{t}>)", line, context=("style",))
        return decls

    def css_media_links(self):
        """Таблицы стилей, подключённые с атрибутом media: {путь: media}."""
        out = {}
        for page in self.pages:
            for a, _ in page.find("link"):
                if "stylesheet" in a.get("rel", "").lower() and a.get("media") and a.get("href"):
                    target = self.resolve(page, a["href"])[0]
                    if target:
                        out[self.rel(target)] = a["media"].lower()
        return out

    def css_texts(self):
        out = [(self.rel(p), p.read_text(encoding="utf-8", errors="replace"))
               for p in self.files if p.suffix.lower() == ".css"]
        for page in self.pages:
            out += [(page.rel, text) for text, _ in page.styles]
        return out

    def js_sources(self):
        out = [(self.rel(p), p.read_text(encoding="utf-8", errors="replace"))
               for p in self.files if p.suffix.lower() in (".js", ".mjs")]
        for page in self.pages:
            out += [(page.rel, text) for text, _ in page.scripts]
            for t, a, line in page.tags:
                for k, v in a.items():
                    if k.startswith("on") and v:
                        out.append((f"{page.rel} ({k} у <{t}>)", f"{k}: {v}"))
        return out

    # ссылки
    def project_site(self) -> bool:
        """True, если сайт откроется по адресу вида user.github.io/repo/ (корень сайта не равен корню домена)."""
        if (self.root / "CNAME").is_file():
            return False
        res = subprocess.run(["git", "-C", str(self.repo), "remote", "get-url", "origin"], capture_output=True,
                             text=True)
        url = res.stdout.strip().rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]
        return not url.lower().endswith(".github.io")

    def _exact(self, path: Path) -> bool:
        """Путь существует с точным регистром букв (GitHub Pages различает регистр, macOS — нет)."""
        try:
            rel = path.relative_to(self.root)
        except ValueError:
            return False
        cur = self.root
        for part in rel.parts:
            if cur not in self._ls:
                try:
                    self._ls[cur] = set(os.listdir(cur))
                except OSError:
                    return False
            if part not in self._ls[cur]:
                return False
            cur = cur / part
        return True

    def resolve(self, page, url: str, base: Path | None = None):
        """(файл или None, причина) для внутренней ссылки; (None, None) — ссылка не внутренняя."""
        url = url.strip()
        if not url or url.startswith("#"):
            return None, None
        parts = urlsplit(url)
        if parts.scheme or url.startswith("//"):
            return None, None
        path = unquote(parts.path)
        if not path:
            return None, None
        if path.startswith("/"):
            if self.project_site():
                return None, "ведёт от корня домена: на адресе user.github.io/<репозиторий>/ это мимо сайта"
            target = self.root / path.lstrip("/")
        else:
            target = ((base or page.path.parent) / path)
        target = Path(os.path.normpath(str(target)))
        if path.endswith("/") or (target.is_dir() and self._exact(target)):
            target = target / "index.html"
        if not self._exact(target):
            if target.exists():
                return None, "регистр букв в имени файла не совпадает (на GitHub Pages это 404)"
            return None, "файла нет"
        return target, None

    def link_refs(self):
        """(страница, строка, url, база) для всех внутренних ссылок HTML и url() в CSS."""
        refs = []
        for page in self.pages:
            for t, a, line in page.tags:
                attrs = []
                if t == "a" or t == "area":
                    attrs = ["href"]
                elif t == "link" and not {"canonical", "alternate", "preconnect", "dns-prefetch"} & set(
                        a.get("rel", "").lower().split()):
                    attrs = ["href"]
                elif t in ("img", "script", "iframe", "embed", "track", "audio"):
                    attrs = ["src"]
                elif t == "source":
                    attrs = ["src", "srcset"]
                elif t == "video":
                    attrs = ["src", "poster"]
                elif t == "object":
                    attrs = ["data"]
                if t == "img":
                    attrs.append("srcset")
                for k in attrs:
                    v = a.get(k)
                    if not v:
                        continue
                    urls = [s.strip().split()[0] for s in v.split(",") if s.strip()] if k == "srcset" else [v]
                    refs += [(page, page.rel, line, u, None) for u in urls]
        for origin, text in self.css_texts():
            base = (self.root / origin).parent
            for m in re.finditer(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", COMMENT.sub("", text)):
                u = m.group(1)
                if not u.startswith("data:"):
                    refs.append((None, origin, None, u, base))
        return refs

    def broken_links(self):
        bad = []
        for page, origin, line, url, base in self.link_refs():
            if url.split(":", 1)[0].lower() in ("mailto", "tel", "javascript", "data", "sms"):
                continue
            target, why = self.resolve(page, url, base or (page.path.parent if page else self.root))
            if why:
                bad.append(f"{origin}{':' + str(line) if line else ''}: {url} — {why}")
        return bad


# --- форматы картинок --------------------------------------------------------------------------

def sniff(path: Path) -> str:
    head = path.read_bytes()[:64]
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis"):
        return "avif"
    if head[4:8] == b"ftyp" and head[8:12] in (b"heic", b"heix", b"mif1", b"msf1"):
        return "heic"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:2] == b"BM":
        return "bmp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if head[:4] == b"\x00\x00\x01\x00":
        return "ico"
    text = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if text.startswith(b"<svg") or text.startswith(b"<?xml"):
        return "svg"
    return "unknown"


EXT_FORMAT = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp", ".avif": "avif", ".svg": "svg",
              ".gif": "gif", ".bmp": "bmp", ".tif": "tiff", ".tiff": "tiff", ".heic": "heic", ".heif": "heic",
              ".ico": "ico"}


# --- общие критерии обеих практик --------------------------------------------------------------

def heavy_images(site: Site, max_kb: int):
    heavy = [(p.stat().st_size, site.rel(p)) for p in site.images() if p.stat().st_size > max_kb * 1024]
    return [f"{rel} — {fmt_kb(size)}" for size, rel in sorted(heavy, reverse=True)]


def missing_alt(site: Site):
    bad = []
    for page in site.pages:
        for a, line in page.find("img"):
            if a.get("aria-hidden", "").lower() == "true" or a.get("role", "").lower() in ("presentation", "none"):
                continue
            if not a.get("alt", "").strip():
                bad.append(f"{page.rel}:{line}: <img src=\"{a.get('src', '')}\">" +
                           (" alt пустой" if "alt" in a else " без alt"))
    return bad


def placeholders(site: Site, ci: list, cs: list):
    found = []
    rx_ci = [re.compile(re.escape(s), re.I) for s in ci]
    rx_cs = [re.compile(r"\b" + re.escape(s) + r"\b") for s in cs]
    for p in site.text_files(TEXT_EXT - {".css"}):
        text = p.read_text(encoding="utf-8", errors="replace")
        for rx in rx_ci + rx_cs:
            for m in rx.finditer(text):
                found.append(f"{site.rel(p)}:{text.count(chr(10), 0, m.start()) + 1}: «{m.group(0)}»")
    return found


def meta_problems(site: Site, need_description=True):
    bad = []
    for page in site.pages:
        miss = []
        if not page.title:
            miss.append("<title>")
        if page.rel.lower() != "404.html":
            if need_description and not page.meta("name", "description"):
                miss.append("meta description")
            if not page.meta("property", "og:title"):
                miss.append("og:title")
            og = page.meta("property", "og:image")
            if not og:
                miss.append("og:image")
            elif not re.match(r"^https?://", og):
                miss.append(f"og:image с полным адресом (сейчас «{og}»)")
        if miss:
            bad.append(f"{page.rel}: нет {', '.join(miss)}")
    return bad
