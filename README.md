# AnalyzeApp MVP (Этап 1)

Этот коммит запускает первый рабочий этап MVP по архитектуре из `docs/architecture_v2_ru.md`.

## Что реализовано

- Импорт репозитория (локальный путь или URL) и сохранение в SQLite.
- Просмотр истории коммитов (`git log`).
- Построение отчёта по коммиту:
  - diff и базовые change metrics;
  - запуск `ruff`;
  - запуск `pytest`;
  - AI-summary через Ollama API.
- Кэш отчётов коммитов в SQLite (`commit_reports`).

## Запуск

```bash
python -m analyze_app.cli import /path/to/repo
python -m analyze_app.cli commits /path/to/repo --limit 15
python -m analyze_app.cli report 1 /path/to/repo <commit_hash>
```

## Настройка AI-summary (Ollama)

По умолчанию используется `http://localhost:11434/api/generate`.

Это означает, что для генерации AI-summary должен быть запущен локальный сервер Ollama на вашей машине
(порт `11434`), иначе приложение вернёт fallback-сообщение вида `AI summary unavailable: ...`.

Можно переопределить адрес и модель через переменные окружения:

```bash
export ANALYZE_APP_OLLAMA_URL="http://127.0.0.1:11434/api/generate"
export ANALYZE_APP_OLLAMA_MODEL="llama3.1"
python -m analyze_app.cli report 1 /path/to/repo <commit_hash>
```

## Ограничения текущего этапа

- UI-слой пока не добавлен (MVP начинается с бэкенд-ядра).
- Отчёт кэшируется агрегированно; детальные списки проблем и тестов хранятся только в runtime.

- Для Windows вывод subprocess декодируется в несколько кодировок (`utf-8`, `cp1251`, `cp866`) для предотвращения `UnicodeDecodeError` при `git/ruff/pytest`.
