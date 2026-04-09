# AnalyzeApp MVP+ (Этап 2)

Этот коммит продолжает архитектуру из `docs/architecture_v2_ru.md` и закрывает задачи второго этапа.

## Что реализовано

- Все возможности Этапа 1:
  - импорт репозитория (локальный путь или URL) и сохранение в SQLite;
  - просмотр истории коммитов (`git log`);
  - отчёт по коммиту (diff + метрики + Ruff + pytest + AI-summary через Ollama).
- Этап 2:
  - карта проекта (AST graph) + hotspot score по churn из `git log --numstat`;
  - отчёт по Working Tree (`working-tree-report`) для незакоммиченных изменений;
  - flow `stage -> commit -> push` через `commit-push`;
  - фоновые задачи (очередь + воркер) через `enqueue-jobs`;
  - AI-summary с evidence blocks (список файлов с объяснением, почему они включены в резюме).

## Запуск

```bash
python -m analyze_app.cli import /path/to/repo
python -m analyze_app.cli commits /path/to/repo --limit 15
python -m analyze_app.cli report 1 /path/to/repo <commit_hash>
python -m analyze_app.cli working-tree-report 1 /path/to/repo
python -m analyze_app.cli project-map 1 /path/to/repo --top 10
python -m analyze_app.cli commit-push /path/to/repo -m "feat: update" --no-push
python -m analyze_app.cli enqueue-jobs 1 /path/to/repo --commit-hash <commit_hash>
```

## Настройка AI-summary (Ollama)

По умолчанию используется модель `llama3.2:latest`.

AI-summary сначала пробует локальный Python SDK `ollama`, и только потом fallback на HTTP endpoint.

Если видите ошибку вида `404`, обычно это значит, что модель не загружена в Ollama.

```bash
ollama pull llama3.2:latest
```

Переопределить модель и endpoint можно через переменные окружения:

```bash
export ANALYZE_APP_OLLAMA_MODEL="llama3.2:latest"
export ANALYZE_APP_OLLAMA_URL="http://127.0.0.1:11434/api/generate"
python -m analyze_app.cli report 1 /path/to/repo <commit_hash>
```

## Ограничения текущего этапа

- UI-слой пока не добавлен; реализована прикладная и инфраструктурная часть под Этап 2.
- Очередь задач локальная in-process (single worker), без внешнего брокера.
- AI evidence blocks формируются эвристически из diff и упоминаний файлов в summary.
