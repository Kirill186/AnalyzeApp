# AnalyzeApp MVP+ (Этап 3)

Этот репозиторий реализует прикладную и инфраструктурную часть AnalyzeApp по архитектуре из `docs/architecture_v2_ru.md`.

## Что реализовано

- Возможности Этапа 1 и Этапа 2:
  - импорт репозитория (локальный путь или URL) и сохранение в SQLite;
  - просмотр истории коммитов (`git log`);
  - отчёт по коммиту (diff + метрики + Ruff + pytest + AI-summary через локальный LLM backend);
  - карта проекта (AST graph) + hotspot score;
  - AI-описание сути проекта и его структуры (1-2 абзаца для страницы репозитория);
  - отчёт по Working Tree;
  - flow `stage -> commit -> push`;
  - фоновые задачи (очередь + воркер).
- Этап 3 (основная часть):
  - inference-модуль `AIAuthorship` (извлечение признаков → модель → калибровка вероятности);
  - кэширование результатов `ai_authorship_cache` в SQLite;
  - CLI-команда `ai-authorship` для оценок по `working_tree`, `commit`, `file`.

## Запуск CLI

```bash
python -m analyze_app.cli import /path/to/repo
python -m analyze_app.cli commits /path/to/repo --limit 15
python -m analyze_app.cli report 1 /path/to/repo <commit_hash>
python -m analyze_app.cli working-tree-report 1 /path/to/repo
python -m analyze_app.cli project-map 1 /path/to/repo --top 10
python -m analyze_app.cli project-overview /path/to/repo --max-files 120
python -m analyze_app.cli ai-authorship 1 /path/to/repo --scope working_tree
python -m analyze_app.cli ai-authorship 1 /path/to/repo --scope commit --commit-hash <commit_hash>
python -m analyze_app.cli ai-authorship 1 /path/to/repo --scope file --files src/foo.py src/bar.py
python -m analyze_app.cli enqueue-jobs 1 /path/to/repo --commit-hash <commit_hash>
python -m analyze_app.cli gui
```

## Настройка AI-summary (GGUF без Ollama)

По умолчанию приложение использует прямой backend `llama_cpp`: модель загружается через `llama-cpp-python`, без запущенного Ollama-сервиса. Можно указать обычный путь к `.gguf` файлу или ссылку на уже скачанную модель из кеша Ollama.

```bash
export ANALYZE_APP_LLM_BACKEND="llama_cpp"
export ANALYZE_APP_LLM_MODEL_PATH="ollama://llama3.2:latest"
export ANALYZE_APP_LLM_CONTEXT_SIZE="4096"
export ANALYZE_APP_LLM_THREADS="0"
export ANALYZE_APP_LLM_GPU_LAYERS="0"
```

`ANALYZE_APP_LLM_THREADS=0` оставляет выбор числа CPU-потоков за `llama.cpp`. В desktop-приложении backend можно переключить через `Settings -> AI Model`: `GGUF / llama.cpp` работает напрямую с локальной моделью, а `Ollama service` использует запущенный сервис Ollama.

PowerShell:

```powershell
$env:ANALYZE_APP_LLM_BACKEND = "llama_cpp"
$env:ANALYZE_APP_LLM_MODEL_PATH = "ollama://llama3.2:latest"
```

Для отдельного GGUF-файла укажите полный путь, например `C:\models\model.gguf`.

Для Windows CPU wheel:

```powershell
python -m pip install --only-binary=:all: --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu "llama-cpp-python==0.3.0"
```

Если нужно временно вернуться к Ollama, установите optional dependency `analyze-app[ollama]` и переключите backend:

```bash
export ANALYZE_APP_LLM_BACKEND="ollama"
export ANALYZE_APP_OLLAMA_MODEL="llama3.2:latest"
export ANALYZE_APP_OLLAMA_URL="http://127.0.0.1:11434/api/generate"
```

## AIAuthorship: модель и калибровка

По умолчанию inference использует локальные JSON-артефакты:
- `analyze_app/infrastructure/ai/authorship/default_model.json`
- `analyze_app/infrastructure/ai/authorship/default_calibration.json`

Переопределение путей через переменные окружения:

```bash
export ANALYZE_APP_AI_AUTHORSHIP_MODEL_PATH="/path/to/model.json"
export ANALYZE_APP_AI_AUTHORSHIP_CALIBRATION_PATH="/path/to/calibration.json"
```

> Важно: обучение и подготовка датасета выполняются в отдельном CLI/сервисе (вне UI-процесса). Этот репозиторий реализует только inference-контур.

## Датасет AIGCodeSet: как читать колонки

Для датасета `basakdemirok/AIGCodeSet` (`all_data_with_ada_embeddings_will_be_splitted_into_train_test_set.csv`) полезно учитывать следующее:

- `problem_id` — идентификатор задачи (группировка решений одной задачи).
- `submission_id` — идентификатор конкретной отправки/решения.
- `status_in_folder` — технический статус/категория размещения в исходной структуре датасета.
- `LLM` — источник генерации (какая модель использовалась), если применимо.
- `code` — исходный код решения (основной текст для feature extraction).
- `ada_embedding` — векторное представление кода (обычно embedding от семейства OpenAI Ada; хранится как сериализованный список чисел). Практически: это dense-вектор фиксированной размерности для семантики и стиля текста/кода.
- `label` — целевая метка класса (например, human/AI в бинарной постановке).
- `lines` — общее число строк.
- `code_lines` — число непустых строк кода.
- `comments` — число строк-комментариев.
- `functions` — число функций.
- `blank_lines` — число пустых строк.

## Рекомендованный внешний пайплайн обучения (отдельный сервис)

1. Загрузить CSV и привести `ada_embedding` к `list[float]` (без строкового формата).
2. Зафиксировать `dataset_version` (например, по sha256 файла + дата).
3. Собрать train/validation/test split с группировкой по `problem_id` (чтобы снизить утечку).
4. Обучить базовый классификатор (например, Logistic Regression/GBDT).
5. Посчитать метрики: ROC-AUC, PR-AUC, Brier score, calibration curve.
6. Обучить calibrator (Platt или Isotonic) и сохранить отдельно.
7. Экспортировать артефакты в JSON:
   - веса/порядок фич/`model_version`;
   - параметры калибратора/`calibration_version`.
8. Подключить артефакты к этому приложению через переменные окружения.

## Ограничения

- UI-слой пока не добавлен; реализованы backend/CLI-компоненты. Детальная спецификация будущего интерфейса: `docs/ui_spec_v1_ru.md`.
- AIAuthorship является вероятностной эвристикой; не заменяет экспертную ревизию.
- Фоновые задачи остаются in-process и single-worker.
