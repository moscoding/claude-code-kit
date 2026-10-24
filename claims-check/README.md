# claims-check · Сверка утверждений с источниками

Модуль 5, практика «Сверка утверждений с источниками». В `inputs/` — черновик первого экрана `first-screen-draft.md` с десятью помеченными утверждениями и четыре источника в `sources/`: справка о продукте, журнал изменений, исследование `agency-study.pdf` (четыре страницы; на обложке номера нет, напечатанная «1» стоит на второй странице файла) и статья из блога ReportFlow. Скопируйте папку `inputs` в `launch-kit/inputs/claims`.

Проверка — из папки `launch-kit`:

    python3 ../claude-code-kit/claims-check/checks/check_claims.py

Скрипт читает `outputs/claims-check.csv` и `outputs/first-screen-copy.md`, цитаты ищет в копиях источников из набора. В `checks/expected/` лежит эталон проверки: не открывайте его в сессии с Claude.
