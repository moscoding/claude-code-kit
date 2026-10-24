import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kitlib"))
import sitecheck as sc  # noqa: E402


class SitecheckTest(unittest.TestCase):
    def test_css_context(self):
        decls = sc.css_decls("a{width:1200px}\n@media (min-width: 800px){.b{width:900px}}", "x.css")
        self.assertEqual(decls[0][2:], (("a",), "width", "1200px"))
        self.assertIn("min-width", sc.at_media(decls[1][2]))

    def test_comments_keep_lines(self):
        decls = sc.css_decls("/* a\nb */\np{color:red}", "x.css")
        self.assertEqual(decls[0][1], 3)

    def test_sniff(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "a.jpg"
            p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 16)
            self.assertEqual(sc.sniff(p), "png")
            p.write_bytes(b"RIFF\0\0\0\0WEBPVP8 ")
            self.assertEqual(sc.sniff(p), "webp")

    def test_site_links_and_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "img").mkdir()
            (root / "img" / "a.jpg").write_bytes(b"\xff\xd8\xff")
            (root / "CNAME").write_text("me.example.com\n")
            (root / "index.html").write_text(
                '<title>T</title><p>Два слова</p><img src="img/a.jpg" alt="a"><a href="nope.html">x</a>'
                '<a href="/img/a.jpg">y</a><script>var hidden = "текст скрипта";</script>', encoding="utf-8")
            site = sc.Site(root, root)
            page = site.page("index.html")
            self.assertEqual(page.title, "T")
            self.assertNotIn("скрипта", page.words)
            bad = site.broken_links()
            self.assertEqual(len(bad), 1)
            self.assertIn("nope.html", bad[0])


if __name__ == "__main__":
    unittest.main()
