# claude-code-kit

Учебный набор курса Moscow Coding School «Основы Claude Code»: входные файлы практик и контрольные скрипты.

## Как поставить

Набор лежит рядом с вашим проектом `launch-kit`, а не внутри него. Так Claude не правит проверку вместе с решением. Из папки `launch-kit`:

```bash
git clone https://github.com/moscoding/claude-code-kit ../claude-code-kit
```

Получится две соседние папки:

```text
launch-kit/          ваш проект, здесь работает Claude
claude-code-kit/     набор: входные файлы и проверки
```

Перед каждой новой практикой обновите набор:

```bash
git -C ../claude-code-kit pull
```

Свои файлы в наборе не меняйте: `pull` тогда проходит без конфликтов. Всё, что делаете в практике, остаётся в `launch-kit`.

## Практики

Команды проверки запускаются из папки `launch-kit`.

| Папка | Модуль | Практика | Проверка |
| --- | --- | --- | --- |
| `contract-redline/` | 4. Документы: Google Docs, Word и PDF | Договор с подрядчиком | `python3 ../claude-code-kit/contract-redline/checks/check_contract.py` |
| `claims-check/` | 5. Исследование и проверка фактов | Сверка утверждений с источниками | `python3 ../claude-code-kit/claims-check/checks/check_claims.py` |
| `crm-reconcile/` | 6. Таблицы: Google Sheets и Excel | Сверка выгрузок CRM | `python3 ../claude-code-kit/crm-reconcile/checks/check_reconcile.py` |
| `table-traps/` | 6. Таблицы: Google Sheets и Excel | Ловушки таблиц | разбор: ответы сверяются с уроком, скрипта нет |
| `ab-test/` | 7. Анализ данных и статистика | Решение по A/B-тесту первого экрана | `python3 ../claude-code-kit/ab-test/checks/check_ab.py` |
| `channels-report/` | 8. Скрипты и графики | Отчёт по рекламным каналам | `python3 ../claude-code-kit/channels-report/checks/check_channels.py` |
| `charts/` | 8. Скрипты и графики | Шесть графиков | разбор: ответы сверяются с уроком, скрипта нет |
| `code-reading/` | 10. Код: чтение, запуск, отладка | Четыре фрагмента кода | `python3 ../claude-code-kit/code-reading/checks/check_reading.py` |
| `buggy-report/` | 10. Код: чтение, запуск, отладка | Три бага в недельном отчёте | `python3 ../claude-code-kit/buggy-report/checks/check_bugs.py` |
| `git-drill/` | 11. Git и GitHub в команде | Ветка, конфликт и откат | `python3 ../claude-code-kit/git-drill/checks/check_git_drill.py` |
| `ci/` | 11. Git и GitHub в команде | Pull request с проверками CI | `python3 ../claude-code-kit/ci/checks/check_repo.py`, после слияния PR — `python3 ../claude-code-kit/ci/checks/check_pr.py` |
| `portfolio/` | 12. Сайты: портфолио, питч, лендинг | Сайт-портфолио | из папки `portfolio`: `python3 ../claude-code-kit/portfolio/checks/check_portfolio.py` |
| `pitch/` | 12. Сайты: портфолио, питч, лендинг | Веб-питч для заказчика | из папки `orbidesk-pitch`: `python3 ../claude-code-kit/pitch/checks/check_pitch.py` |
| `connectors/` | 14. Коннекторы и MCP | Дайджест из двух источников | `python3 ../claude-code-kit/connectors/checks/check_digest.py` |
| `repo-digest/` | 15. Расписания и фоновые запуски | Ежедневный дайджест репозитория | из папки `digest-work`: `python3 ../claude-code-kit/repo-digest/checks/check_digest.py` |
| `poisoned-doc/` | 16. Безопасность | Отравленный документ | из папки `inbox-sandbox`: `python3 ../claude-code-kit/poisoned-doc/checks/check_poisoned.py` |
| `team-pack/` | 17. Claude Code в команде | Командный пакет | `python3 ../claude-code-kit/team-pack/checks/check_team.py` |
| `reels/` | 18. Ролики для соцсетей | Ролик из отчёта по каналам | из папки `reel-01`: `python3 ../claude-code-kit/reels/checks/check_reel.py` |
| `capstone/` | 19. Кэпстоун | Кэпстоун-проект | из папки `followup-kit` после слияния PR: `python3 ../claude-code-kit/capstone/checks/check_capstone.py` |

## Файлы для задач в уроках

Эти файлы читают, чтобы ответить на задачу в уроке. Копировать их в `launch-kit` не нужно, автопроверки у них нет: ответ вводят в уроке.

| Папка | Модуль | Уроки |
| --- | --- | --- |
| `usage-limits/` | 1. Введение в Claude Code | «Модель, усилие и расход» |
| `session-rewind/` | 1. Введение в Claude Code | «Сессии и команды» |
| `portfolio/heroes/`, `portfolio/site-costs.csv` | 12. Сайты: портфолио, питч, лендинг | «Сайт без конструктора», «Проверки перед показом» |
| `plugin-cost/` | 13. Скилы, хуки и автономность | «Плагины» |
| `mod-review/` | 13. Скилы, хуки и автономность | «Моды» |
| `connectors/snapshots/` | 14. Коннекторы и MCP | «Что такое MCP и коннекторы», «Подключить и проверить сервер», «Google Drive, Slack, Notion и почта: чтение и запись», «Живой дашборд из коннектора» |
| `repo-digest/samples/` | 15. Расписания и фоновые запуски | «Запуск без диалога: claude -p», «GitHub Actions и @claude» |
| `security-drills/` | 16. Безопасность | «Секреты и мок-данные», «Доверие к расширениям» |
| `team-pack/lessons/` | 17. Claude Code в команде | «Общий CLAUDE.md и личные настройки», «Командные скилы и плагины», «Параллельная работа», «Хэндоф между людьми», «Оценка результата» |
| `capstone/lessons/` | 19. Кэпстоун | «Требования к кэпстоун-проекту» |

## Как устроена практика

- `<папка>/inputs/` — файлы, которые практика просит скопировать в `launch-kit/inputs/`.
- `<папка>/checks/check_<имя>.py` — автопроверка.
- `<папка>/README.md` — что скопировать и куда.

Некоторые папки устроены иначе. В разборах `table-traps/` и `charts/` лежат только файлы для просмотра. В `channels-report/` нет `inputs/`: данные практика создаёт текстом из урока. `git-drill/` собирает учебный репозиторий скриптом `setup.py`, а `ci/kit-files/` повторяет пути проекта. Практики `portfolio/` и `pitch/` работают в своих открытых репозиториях рядом с `launch-kit` (`portfolio` и `orbidesk-pitch`) и запускают проверку оттуда; `portfolio/workflow/` — воркфлоу GitHub Actions для репозитория сайта. Отдельную рабочую папку рядом с `launch-kit` собирают и `setup.py` других практик: `repo-digest/` — репозиторий `digest-work`, `poisoned-doc/` — песочницу `inbox-sandbox`, `security-drills/leaked-key/` — репозиторий `leaked-key-drill`. Проверку `repo-digest/` и `poisoned-doc/` запускают из собранной папки. Практика `reels/` работает в своём проекте Remotion `reel-01` рядом с `launch-kit`, проверку запускают оттуда после рендера. Кэпстоун `capstone/` проверяет ваш закрытый репозиторий `followup-kit` на GitHub: проверку запускают из него после слияния PR, а заметки из `capstone/checks/probe/` проверка подаёт вашему скрипту сама, копировать их не нужно. Что копировать, написано в README папки.

Проверка печатает по строке на критерий: `✔` — выполнен, `✘` — нет, с подсказкой, куда смотреть. Последняя строка — «Итог: N из M». Код выхода 0 — всё пройдено, 1 — есть непройденные критерии, 2 — проверку нельзя провести.

Проверки написаны на стандартной библиотеке Python 3.9+ (подходит системный `python3` macOS): ставить пакеты не нужно.

## Эталоны

Эталонных решений в наборе нет: ни готовых документов, ни скриптов, ни таблиц. Проверка сверяет ваш результат с правилами и контрольными значениями из `checks/expected/` и печатает только «совпало или нет» и подсказку. Контрольные значения раскрывают ответы, поэтому не открывайте эту папку до проверки. Если Claude просит её открыть, откажите: сравнение — работа проверки, а не модели.

Все данные синтетические: имена из сюжета курса, ссылки вида `mock://`.

## Для авторов набора

Тесты общего раннера `kitlib/check.py`: `python3 -m unittest discover -s tests`. Генераторы файлов и приёмка набора живут в отдельном закрытом репозитории.

Лицензия MIT.
