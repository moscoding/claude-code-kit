import subprocess, sys, textwrap, unittest, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(body: str):
    code = textwrap.dedent(f"""
        import sys; sys.path.insert(0, {str(ROOT / 'kitlib')!r})
        from check import Check, Result, Stop
        check = Check("Проверка")
    """) + textwrap.dedent(body) + "\ncheck.run()\n"
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


class KitlibTest(unittest.TestCase):
    def test_all_pass(self):
        r = run("""
            @check.criterion("a")
            def _(): return True
        """)
        self.assertEqual(r.returncode, 0)
        self.assertIn("✔ a", r.stdout)
        self.assertIn("Итог: 1 из 1. Практика пройдена.", r.stdout)

    def test_fail_with_hint(self):
        r = run("""
            @check.criterion("b")
            def _(): return Result(False, fail="Нет файла", hint="создайте файл")
        """)
        self.assertEqual(r.returncode, 1)
        self.assertIn("✘ Нет файла\n  Подсказка: создайте файл", r.stdout)
        self.assertIn("Итог: 0 из 1. Практика не пройдена.", r.stdout)

    def test_crash_is_fail(self):
        r = run("""
            @check.criterion("c")
            def _(): raise ValueError("boom")
        """)
        self.assertEqual(r.returncode, 1)
        self.assertIn("проверка критерия упала: ValueError: boom", r.stdout)

    def test_stop(self):
        r = run("""
            @check.before
            def _(): raise Stop("Не найдена папка launch-kit.")
            @check.criterion("d")
            def _(): return True
        """)
        self.assertEqual(r.returncode, 2)
        self.assertIn("Не найдена папка launch-kit.", r.stdout)
        self.assertNotIn("Итог", r.stdout)


if __name__ == "__main__":
    unittest.main()
