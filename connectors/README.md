# connectors

Модуль 13 «Коннекторы и MCP».

## Что внутри

- `snapshots/` — снимки к задачам в уроках модуля. Их только читают, в `launch-kit` не копируют:
  - `mcp.json` — настройки серверов проекта в формате `.mcp.json` (урок «Что такое MCP и коннекторы»);
  - `mcp-list.txt` — вывод `claude mcp list` на компьютере Оли (урок «Подключить и проверить сервер»);
  - `wiki-tools.txt` — список тулов сервера `wiki` из `/mcp` → `View tools` и `settings.json` — правила разрешений проекта Оли (урок «Google Drive, Slack, Notion и почта»);
  - `dashboard-plan.md` — план дашборда «Пульт запуска» (урок «Живой дашборд из коннектора»).
  Серверы `wiki`, `files`, `reports`, `analytics` и адреса `*.example.com` учебные: таких серверов нет.
- `inputs/` — данные практики «Дайджест из двух источников»: экспорт канала Slack `#launch` и документы запуска из Google Drive в Markdown. Правила отбора и формат дайджеста — в `inputs/README.md`.
- `checks/check_digest.py` — автопроверка практики.

## Что копировать

Перед практикой — всю папку `inputs/` в `launch-kit/inputs/digest/`:

```bash
cp -R ../claude-code-kit/connectors/inputs inputs/digest
```

Данные учебные: люди, сообщения и документы придуманы для курса.

## Проверка

Из корня `launch-kit`, после коммита:

```bash
python3 ../claude-code-kit/connectors/checks/check_digest.py
```

Проверка запускает `scripts/digest.py` только во временных копиях проекта: на данных практики и на данных другой недели из `checks/expected/`. Папку `launch-kit` она не меняет.
