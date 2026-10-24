# contract-redline · Договор с подрядчиком

Модуль 4, практика «Договор с подрядчиком». В `inputs/` — договор агентства «Сигнал» `contract.docx` (учебный пример, заголовки стилями Word) и шесть замечаний юриста Марины `legal-notes.md`. Скопируйте оба файла в `launch-kit/inputs/`.

Проверка — из папки `launch-kit`:

    python3 ../claude-code-kit/contract-redline/checks/check_contract.py

Скрипт разбирает `outputs/contract-redline.docx` как zip с XML: правки режима рецензирования, текст после принятия и после отклонения правок, стили заголовков. В `checks/expected/` лежит эталон проверки: не открывайте его в сессии с Claude.
