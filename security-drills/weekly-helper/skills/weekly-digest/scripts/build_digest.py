"""Учебный скрипт скила weekly-digest: печатает изменения за 7 дней по git log."""
import subprocess

log = subprocess.run(["git", "log", "--since=7.days", "--oneline", "--", "outputs/"],
                     capture_output=True, text=True).stdout
print("Дайджест за неделю:")
print(log or "Изменений в outputs/ нет.")
