"""claude-code-kit · общий раннер автопроверок.

Источник — kitlib/check.py в корне набора. Контрольные скрипты практик
импортируют его так:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "kitlib"))
    from check import Check, Result

Только стандартная библиотека, Python 3.9 или новее.

Пример:
    check = Check("Проверка практики «Пример»")

    @check.criterion("README.md")
    def _():
        return Result(Path("README.md").exists(),
                      pass_="Есть README.md", fail="Нет README.md",
                      hint="попросите Claude описать проект в README.md.")

    check.run()

Вывод:
    ✔ критерий выполнен
    ✘ критерий не выполнен
      Подсказка: куда смотреть.

    Итог: N из M. Практика пройдена.   (или «не пройдена»)

Коды выхода: 0 — все критерии пройдены, 1 — есть непройденные,
2 — проверку нельзя провести (нет файла, проект не найден).
Скрипт печатает только «совпало / не совпало» и подсказку: эталон не
раскрывается.
"""
from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass, field
from typing import Callable, Iterable

PASSED, FAILED, NOT_READY = 0, 1, 2


@dataclass
class Result:
    ok: bool
    pass_: str | None = None
    fail: str | None = None
    hint: str | Iterable[str] | None = None
    details: list[str] = field(default_factory=list)


class Stop(Exception):
    """Проверку нельзя продолжить: печатает строки и выходит с кодом 2."""

    def __init__(self, *lines: str, code: int = NOT_READY):
        super().__init__("check stopped")
        self.lines = lines
        self.code = code


def _lines(value) -> list[str]:
    if value is None or value is False:
        return []
    if isinstance(value, str):
        return value.split("\n")
    return [line for item in value for line in _lines(item)]


class Check:
    def __init__(self, heading: str):
        self.heading = heading
        self._before: list[Callable[[], None]] = []
        self._criteria: list[tuple[str, Callable[[], Result | bool]]] = []
        self._after: list[Callable[[], None]] = []

    def before(self, fn):
        self._before.append(fn)
        return fn

    def after(self, fn):
        self._after.append(fn)
        return fn

    def criterion(self, name: str):
        def wrap(fn):
            self._criteria.append((name, fn))
            return fn
        return wrap

    def _render(self, name: str, res: Result) -> list[str]:
        text = (res.pass_ if res.ok else res.fail) or name
        out = [f"{'✔' if res.ok else '✘'} {text}"]
        out += [f"  {line}" for line in _lines(res.details)]
        if not res.ok:
            hint = _lines(res.hint)
            out += [f"  {'Подсказка: ' if i == 0 else ''}{line}" for i, line in enumerate(hint)]
        return out

    def run(self) -> int:
        print(self.heading)
        print()
        code = NOT_READY
        try:
            for fn in self._before:
                fn()
            passed = 0
            for name, fn in self._criteria:
                try:
                    res = fn()
                except Stop:
                    raise
                except Exception as exc:  # критерий упал — считаем непройденным
                    res = Result(False, hint=f"проверка критерия упала: {exc.__class__.__name__}: {exc}")
                    if "--debug" in sys.argv:
                        traceback.print_exc()
                if isinstance(res, bool):
                    res = Result(res)
                passed += res.ok
                for line in self._render(name, res):
                    print(line)
            total = len(self._criteria)
            print()
            print(f"Итог: {passed} из {total}. Практика {'пройдена' if passed == total else 'не пройдена'}.")
            code = PASSED if passed == total else FAILED
        except Stop as stop:
            for line in stop.lines:
                print(line)
            code = stop.code
        except KeyboardInterrupt:
            print("\nПроверка прервана.")
            code = NOT_READY
        finally:
            for fn in self._after:
                try:
                    fn()
                except Exception:
                    pass
        sys.exit(code)
