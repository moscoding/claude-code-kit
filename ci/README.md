# ci

Практика модуля 11 «Pull request с проверками CI».

## Что внутри

- `issues.md` — три задачи для GitHub Issues: заголовок задачи — строка после `## `, описание — текст до следующего `## `;
- `kit-files/.github/workflows/checks.yml` — воркфлоу для `launch-kit`: на каждый пуш ставит Python 3.12, запускает `python -m unittest -v`, клонирует этот набор рядом с проектом и запускает `checks/check_repo.py`;
- `kit-files/inputs/status-date.txt` — дата данных страницы статуса, `2026-05-15`;
- `kit-files/tests/test_status_date.py` — приёмочный тест задачи «Показать дату обновления на странице статуса»;
- `checks/check_repo.py` — проверки набора: маркеры конфликта, файлы с секретами, страница совпадает с результатом `scripts/build_status.py`, приёмочный тест не изменён;
- `checks/check_pr.py` — автопроверка практики через GitHub CLI.

## Что копировать

В `launch-kit`, по тем же путям:

- до публикации — `.github/workflows/checks.yml` и `inputs/status-date.txt`;
- в ветке задачи, до реализации — `tests/test_status_date.py`. Тест копируют командой `cp ../claude-code-kit/ci/kit-files/tests/test_status_date.py tests/` и не правят: правило `"deny": ["Edit(/tests/**)"]` из модуля 10 остаётся на месте.

## Проверки

Из корня `launch-kit`:

```bash
python3 ../claude-code-kit/ci/checks/check_repo.py
python3 ../claude-code-kit/ci/checks/check_pr.py
```

`check_repo.py` работает и локально, и в CI: страницу он пересобирает во временной копии и ничего в папке не меняет. `check_pr.py` запускают после слияния PR и `git pull`. Он только читает: `gh repo view`, `gh issue list`, `gh pr list`, `gh pr view`, `gh run list`, запросы `gh api` на чтение и `git fetch`.

Нужны GitHub CLI и вход через `gh auth login`. Поля JSON, которые читает `check_pr.py`, проверены на gh 2.87.3; если `gh --version` старше, обновите его: `brew upgrade gh`.
