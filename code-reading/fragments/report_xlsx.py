# Фрагмент C. Учебный файл курса «Основы Claude Code»: только для чтения.
raise SystemExit("Учебный фрагмент для чтения. Не запускайте его.")

import subprocess
import sys

subprocess.run([sys.executable, "-m", "pip", "install", "xlsx-report-helper"])

import xlsx_report_helper

xlsx_report_helper.build("outputs/weekly-summary.csv", "outputs/weekly.xlsx")
