# capstone

Кэпстоун-проект курса «Основы Claude Code» (модуль 19): проверка репозитория `followup-kit`
и данные для задачи в уроке «Требования к кэпстоун-проекту».

- `lessons/colleague-log.txt` — история чужого кэпстоуна для задачи в уроке. Его только читают.
- `checks/check_capstone.py` — проверка практики «Кэпстоун-проект».
- `checks/probe/` — заметки, на которых проверка испытывает ваш скрипт проверки. Их не копируют в проект.

Проверить кэпстоун, из папки followup-kit, после слияния PR и git pull:

    python3 ../claude-code-kit/capstone/checks/check_capstone.py

Своя задача вместо учебной:

    python3 ../claude-code-kit/capstone/checks/check_capstone.py --own
