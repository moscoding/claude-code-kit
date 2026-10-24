# team-pack

Данные модуля 17 «Claude Code в команде»: задачи из уроков и практика «Командный пакет».

- `lessons/` — файлы для задач в уроках модуля 17. Их только читают.
- `practice/` — правила Марины и пять памяток для практики.
- `checks/check_team.py` — проверка практики.

Скопировать памятки в проект, из папки launch-kit:

    mkdir -p inputs/memos && cp ../claude-code-kit/team-pack/practice/memos/*.md inputs/memos/

Проверить практику, из папки launch-kit:

    python3 ../claude-code-kit/team-pack/checks/check_team.py
