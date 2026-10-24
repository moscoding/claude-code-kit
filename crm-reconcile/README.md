# crm-reconcile

Данные практики «Сверка выгрузок CRM» курса «Основы Claude Code». На эти же
файлы опираются уроки модуля 6 «CSV и XLSX», «Очистка данных и сводные
таблицы» и «Excel: формулы, листы и сводные таблицы».

- `inputs/` — `crm-leads-sept.csv`, `crm-leads-oct.xlsx` и словарь полей
  `crm-dictionary.md`. Копируйте их в `inputs/` своего `launch-kit` и не меняйте.
- `checks/check_reconcile.py` — проверка практики. Запуск из папки `launch-kit`:

  ```bash
  python3 ../claude-code-kit/crm-reconcile/checks/check_reconcile.py
  ```

- `checks/expected/` — эталон для проверки. Claude его не открывает.

Данные синтетические, без имён, телефонов и email. Пересборка входов и эталона
из корня набора: `python3 tools/build_crm_reconcile.py crm-reconcile`.
