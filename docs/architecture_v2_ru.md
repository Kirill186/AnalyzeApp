# Актуальная архитектура AnalyzeApp (v2)

## 1) Цели системы

AnalyzeApp — настольное приложение для анализа Python-проектов в Git-репозиториях, которое объединяет:
- навигацию по истории (ветки/коммиты/диффы);
- базовые операции управления версиями (status/stage/commit/push);
- статический и динамический анализ качества кода;
- AI-модуль объяснения изменений;
- AI-модуль оценки вероятности AI-генерации кода;
- интерактивную карту структуры проекта.

Ключевой принцип: **рабочая директория пользователя не изменяется во время исторического анализа**.

---

## 2) Архитектурный стиль

Рекомендуемый стиль: **модульный монолит + Clean Architecture + событийный оркестратор задач**.

Слои:
1. **Presentation (Desktop UI)**
2. **Application (Use Cases / Orchestration)**
3. **Domain (модели, политики, контракты)**
4. **Infrastructure (Git, анализаторы, AI, БД, кэш, очередь задач)**

Поперечные аспекты:
- наблюдаемость (логи, трассировка задач, метрики);
- безопасность выполнения (изоляция worktree + sandbox для тестов);
- кэширование результатов анализа и AI.

---

## 3) Контексты репозитория (обязательное разделение)

### A. History Analysis Context (безопасный)
- Работает через `git worktree` (или временный mirror checkout).
- Разрешены checkout/switch между коммитами.
- Используется для:
  - отчёта по коммиту;
  - карты проекта на конкретной ревизии;
  - исторических метрик и AI-резюме коммита.

### B. Working Tree Context (боевой)
- Работа только с текущей рабочей папкой пользователя.
- **Запрещены checkout/reset/switch** внутри AnalyzeApp.
- Используется для:
  - статуса незакоммиченных изменений;
  - отчёта по текущему diff;
  - stage/commit/push по явному подтверждению.

---

## 4) Целевая структура модулей

```text
analyze_app/
  presentation/
    qt_shell/
      main_window.py
      repo_sidebar.py
      commit_graph_view.py
      report_tabs.py
      actions_toolbar.py
    webview/
      pages/
        dashboard.html
        commit_report.html
        working_tree_report.html
        project_map.html
      assets/
      bridge.py

  application/
    use_cases/
      import_repository.py
      list_repositories.py
      build_dashboard.py
      list_commits.py
      get_commit_report.py
      get_working_tree_report.py
      build_project_map.py
      commit_and_push.py
      explain_changes_ai.py
      detect_ai_authorship.py
    dto/
    orchestrators/
      analysis_job_orchestrator.py

  domain/
    entities/
      repository.py
      commit.py
      file_change.py
      issue.py
      metrics.py
      project_graph.py
      llm_result.py
      ai_authorship_result.py
    services/
      risk_scoring_policy.py
      hotspot_policy.py
    ports/
      git_backend_port.py
      analyzer_port.py
      test_runner_port.py
      llm_port.py
      ai_authorship_port.py
      storage_port.py

  infrastructure/
    git/
      pygit_backend.py
      worktree_manager.py
    analysis/
      python/
        ruff_runner.py
        radon_runner.py
        vulture_runner.py
        mypy_runner.py
        pytest_runner.py
        issue_normalizer.py
      metrics/
        diff_metrics_service.py
      map/
        ast_map_builder.py
        hotspot_service.py
    ai/
      llm/
        ollama_backend.py
        api_backend.py
        prompt_builder.py
      authorship/
        feature_extractor.py
        model_runtime.py
        calibrator.py
    storage/
      sqlite/
        schema.sql
        repository_dao.py
        reports_dao.py
        ai_cache_dao.py
    jobs/
      queue.py
      workers.py
      sandbox_runner.py

  shared/
    config.py
    logging.py
    errors.py
```

---

## 5) Use Cases (актуализировано)

## Core
1. `ImportRepositoryUseCase`
   - локальный путь или URL;
   - clone/fetch + первичная индексация;
   - создание карточки репозитория.

2. `BuildDashboardUseCase`
   - агрегаты: количество коммитов, последнее изменение, авторы, покрытие кэша;
   - быстрые KPI качества из последних анализов.

3. `ListCommitsUseCase`
   - граф веток/коммитов, фильтры (ветка, автор, диапазон дат, файл).

4. `CommitReportUseCase`
   - diff + change metrics + lint/static + test results + AI-summary;
   - вычисление риск-скора коммита.

5. `WorkingTreeReportUseCase`
   - diff по незакоммиченным изменениям;
   - быстрый линт/тесты;
   - рекомендации перед commit.

6. `BuildProjectMapUseCase`
   - граф `module/file -> class -> function`;
   - зависимости импортов + hotspot overlay.

7. `CommitAndPushUseCase`
   - stage/commit/push;
   - валидация policy (например, не пушить при красных тестах — настраиваемо).

## AI-сценарии
8. `ExplainChangesAIUseCase`
   - генерирует структурированное объяснение diff/рисков/рекомендаций.

9. `DetectAIAuthorshipUseCase`
   - оценивает вероятность AI-генерации кода на уровне:
     - файла;
     - набора изменений (commit / working tree);
     - проекта (агрегатно, опционально).
   - возвращает вероятности + признаки + confidence + предупреждение об ограничениях.

---

## 6) Доменные сущности (обновлённые)

### Базовые
- `Repository(repo_id, origin_url, working_path, default_branch, created_at, last_scanned_at)`
- `Commit(hash, parents, author, authored_at, committer, committed_at, message, branch_refs)`
- `FileChange(path, status, old_path, additions, deletions, hunks)`
- `Issue(tool, code, message, severity, category, file, line, col, fingerprint)`

### Метрики
- `ChangeMetrics(files_changed, lines_added, lines_deleted, churn_per_file, modules_touched)`
- `QualityMetrics(complexity, maintainability, duplication_proxy, typing_health)`
- `TestRunResult(total, passed, failed, skipped, duration_sec, failed_tests)`

### AI
- `LLMResult(summary, per_file_summary, risks, recommendations, tags, evidence, model_info)`
- `AIAuthorshipResult(scope, probability, confidence, top_signals, calibration_version, model_info, disclaimer)`

### Граф
- `ProjectGraph(nodes, edges, hotspots, symbols_index)`

---

## 7) Подсистема AI-оценки «вероятности использования AI»

## 7.1 Режим inference (в приложении)
Pipeline:
1. Нормализация входа (файлы/дифф, исключение vendor/generated).
2. Извлечение признаков:
   - стилометрия (длина строк/токенов, распределения конструкций);
   - AST/структурные паттерны;
   - метрики повторяемости/шаблонности;
   - сигналы из commit metadata (опционально, осторожно).
3. Прогон модели классификации.
4. Калибровка вероятности (Platt/Isotonic).
5. Формирование объяснения результата без категоричных утверждений.

## 7.2 Режим обучения (отдельный контур)
- Отдельный CLI/сервис, **не в UI-процессе**.
- Версионирование датасета и модели (`dataset_version`, `model_version`).
- Обязательные метрики: ROC-AUC, PR-AUC, Brier score, calibration curve.
- Тест на смещения (по языковым стилям, доменам, форматтерам).

## 7.3 Этические и юридические ограничения
- Результат отображать как «вероятностную оценку», не как детектор факта.
- Добавить дисклеймер в UI и экспортируемые отчёты.
- Не применять как единственный источник санкционных решений.

---

## 8) Infrastructure детали

## 8.1 Git subsystem
- `GitBackend`: commits, diff, blame (опц.), status, stage, commit, push.
- `WorktreeManager`: жизненный цикл аналитических worktree.
- `RefCache`: кэш refs/graph для быстрого UI.

## 8.2 Static + Dynamic analysis
- Статика: Ruff, Radon, Vulture, (Mypy опц.).
- Динамика: pytest с таймаутами и лимитами ресурсов.
- Нормализация в единый `Issue`/`TestRunResult`.

## 8.3 Job orchestration
- Очередь задач (локальная): `analysis_queue`.
- Типы задач: `commit_analysis`, `working_tree_analysis`, `map_rebuild`, `ai_summary`, `ai_authorship_infer`.
- Отмена/повтор/дедупликация по ключу (`repo+commit+pipeline_version`).

## 8.4 Storage (SQLite)
Таблицы минимум:
- `repositories`
- `commits_cache`
- `commit_reports`
- `working_tree_reports`
- `project_maps`
- `analysis_jobs`
- `ai_summaries_cache`
- `ai_authorship_cache`
- `settings`

Кэш-ключ должен включать версии пайплайна:
`(repo_id, commit_hash, analyzer_version, prompt_version, model_version)`.

---

## 9) UI/UX (актуальный состав экранов)

1. **Repository Dashboard**
   - карточки репозиториев;
   - дата последнего анализа;
   - индикаторы качества/рисков.

2. **Repository Workspace**
   - слева: дерево файлов/фильтры;
   - центр: граф коммитов + лента;
   - справа: вкладки `Diff`, `Metrics`, `Issues`, `Tests`, `AI Summary`, `AI Authorship`.

3. **Project Map**
   - уровни: module/file → class → function;
   - подсветка hotspots + проблемных узлов.

4. **Working Tree Panel**
   - текущие изменения;
   - pre-commit quality gate;
   - commit/push flow.

---

## 10) Нефункциональные требования

- Производительность: инкрементальный анализ, кэш, фоновые воркеры.
- Надёжность: повторяемые пайплайны, идемпотентные задачи.
- Безопасность: sandbox для запуска тестов недоверенного кода.
- Расширяемость: `LanguageAnalyzer` и `AIBackend` как плагины.
- Наблюдаемость: структурные логи + диагностика job timeline.

---

## 11) План внедрения по этапам

### Этап 1 (MVP)
- Импорт репозитория, граф коммитов, diff;
- Ruff + pytest;
- отчёт по коммиту;
- базовый AI-summary через Ollama;
- SQLite-кэш.

### Этап 2
- Карта проекта (AST + hotspots);
- рабочая панель Working Tree + commit/push;
- фоновые очереди задач;
- AI-summary с evidence blocks.

### Этап 3
- AIAuthorship inference модуль;
- калибровка вероятностей;
- экспорт отчётов (HTML/PDF/JSON);
- политика quality gates.

### Этап 4
- Контур обучения/переобучения AIAuthorship;
- A/B моделей;
- расширение на другие языки (каркас анализатора уже готов).

---

## 12) Почему эта версия архитектуры лучше исходной

- Явно добавлен второй AI-контур (оценка AI-генерации) как независимый модуль.
- Зафиксированы контуры исполнения: history vs working tree (безопасность данных пользователя).
- Добавлены job orchestration и версионированный кэш — критично для desktop UX.
- Расширены доменные модели для тестов, качества и вероятностных AI-оценок.
- Подготовлена траектория эволюции от MVP до исследовательского контура обучения.
