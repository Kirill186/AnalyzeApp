# AnalyzeApp MVP (Этап 1)

Этот коммит запускает первый рабочий этап MVP по архитектуре из `docs/architecture_v2_ru.md`.

## Что реализовано

- Импорт репозитория (локальный путь или URL) и сохранение в SQLite.
- Просмотр истории коммитов (`git log`).
- Построение отчёта по коммиту:
  - diff и базовые change metrics;
  - запуск `ruff`;
  - запуск `pytest`;
  - AI-summary через локальный Ollama API.
- Кэш отчётов коммитов в SQLite (`commit_reports`).

## Запуск

```bash
python -m analyze_app.cli import /path/to/repo
python -m analyze_app.cli commits /path/to/repo --limit 15
python -m analyze_app.cli report 1 /path/to/repo <commit_hash>
```

## Ограничения текущего этапа

- UI-слой пока не добавлен (MVP начинается с бэкенд-ядра).
- AI-summary зависит от доступности `http://localhost:11434`.
- Отчёт кэшируется агрегированно; детальные списки проблем и тестов хранятся только в runtime.
