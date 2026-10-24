#!/usr/bin/env python3
"""Собирает папку-песочницу inbox-sandbox рядом с набором claude-code-kit.

Практика «Отравленный документ», модуль 15. В папку копируются пять писем подрядчиков и два
справочника; одно письмо содержит указания для AI. Рядом с письмами ничего из launch-kit нет.

Запуск из папки launch-kit:
    python3 ../claude-code-kit/poisoned-doc/setup.py
Повторная сборка (старая папка переименовывается, ничего не удаляется):
    python3 ../claude-code-kit/poisoned-doc/setup.py --fresh
Для приёмки: --target <папка> и --launch-kit <папка>.
"""
import json
import shutil
import sys
import time
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent
ROOT = KIT_DIR.parent.parent
DEFAULT_TARGET = ROOT / "inbox-sandbox"
STATE_NAME = ".kit-state.json"

README = """# inbox-sandbox

Папка-песочница для практики «Отравленный документ». Здесь только письма подрядчиков
и два справочника. Задание — в уроке курса.

Проверка, из этой папки:

    python3 ../claude-code-kit/poisoned-doc/checks/check_poisoned.py
"""


def arg(name):
    args = sys.argv[1:]
    return Path(args[args.index(name) + 1]).resolve() if name in args else None


def main():
    target = arg("--target") or DEFAULT_TARGET
    launch_kit = arg("--launch-kit")
    if launch_kit is None:
        cwd = Path.cwd().resolve()
        launch_kit = cwd if cwd.name == "launch-kit" else ROOT / "launch-kit"
    if target.exists():
        if "--fresh" not in sys.argv:
            print(f"Папка ../{target.name} уже есть. Чтобы собрать заново, добавьте --fresh.")
            sys.exit(2)
        n = 1
        while target.with_name(f"{target.name}-old{n}").exists():
            n += 1
        target.rename(target.with_name(f"{target.name}-old{n}"))
    shutil.copytree(KIT_DIR / "inputs", target / "inputs")
    (target / "outputs").mkdir()
    (target / "README.md").write_text(README, encoding="utf-8")
    state = {"created": time.time(), "launch_kit": str(launch_kit) if launch_kit.is_dir() else None}
    (target / STATE_NAME).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    letters = len(list((target / "inputs" / "inbox").glob("*.md")))
    print(f"Папка ../{target.name} готова: писем {letters}, vendors.csv, payments.csv.")
    print("Откройте её в новой сессии во вкладке Code.")


if __name__ == "__main__":
    main()
