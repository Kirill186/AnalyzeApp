# Детальная спецификация UI AnalyzeApp (RU)

> Документ расширяет `docs/architecture_v2_ru.md` и детализирует экранную модель для Desktop UI (темная современная тема), включая навигацию по репозиториям, вкладки рабочего экрана и сценарии взаимодействия.

## 1. Цели UI

UI должен:
- ускорять обзор состояния нескольких репозиториев;
- позволять быстро переключаться между режимами анализа (overview / commits / map / workspace);
- обеспечивать безопасную работу с историей (через History Analysis Context) и рабочим деревом (Working Tree Context) без смешивания контекстов;
- давать визуально понятные quality-оценки (A/B/C/… + drill-down по клику);
- сохранять современный, контрастный, темный стиль с хорошей читаемостью.

---

## 2. Рекомендуемый технологический стек (как реализовывать)

### 2.1 Desktop shell
- **PySide6 (Qt6)** как основной UI-фреймворк:
  - нативные окна, меню, drag&drop, splitters, tabs;
  - хорошая поддержка больших списков (`QTreeView`, `QListView`, `QAbstractItemModel`);
  - удобная сигнал/слот модель для реактивного UI.

### 2.2 Гибридный рендер сложных визуализаций
- **QWebEngineView + локальные HTML/JS-страницы** для:
  - интерактивного графа коммитов;
  - карты проекта;
  - diff-вьюера с подсветкой.
- Bridge слой: `QWebChannel` (Qt ↔ JS), чтобы UI вызывал use-cases и получал DTO.

### 2.3 Папочная структура Presentation-слоя (рекомендуемая)
```text
analyze_app/presentation/qt_shell/
  main_window.py
  app_menu.py
  repo_sidebar.py
  repo_item_delegate.py
  repo_add_dialog.py
  report_tabs.py
  overview_tab.py
  commits_tab.py
  project_map_tab.py
  workspace_tab.py
  theme.py
  state_store.py
```

---

## 3. Глобальный каркас экрана

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Верхнее меню: File Edit View Analyze Settings Help                          │
├───────────────┬──────────────────────────────────────────────────────────────┤
│ Левая панель  │ Верхняя полоска вкладок: [Обзор] [История] [Карта] [WS]    │
│ репозиториев  ├──────────────────────────────────────────────────────────────┤
│               │ Контент активной вкладки                                    │
│ + / ⟳ кнопки  │                                                              │
│ список repos  │                                                              │
│ (drag/drop,   │                                                              │
│ favorites,    │                                                              │
│ grouping)     │                                                              │
└───────────────┴──────────────────────────────────────────────────────────────┘
```

### 3.1 Пропорции
- Sidebar: 280–360 px (resizable).
- Основная область: все оставшееся пространство.
- Минимальная ширина окна: 1280 px (рекомендация для комфортного диффа/графа).

---

## 4. Верхнее меню (обычное меню)

### File
- Add Repository…
- Refresh Current Repository
- Refresh All Repositories
- Exit

### View
- Toggle Left Sidebar
- Reset Layout
- Zoom In/Out (для web-based вкладок)

### Analyze
- Rebuild Project Map
- Run Working Tree Analysis
- Run Commit Analysis (selected commit)

### Settings
- Quality Grades (границы A/B/C/…)
- AI modules
- Paths / clone root

### Help
- About
- Open Logs
- Architecture docs

---

## 5. Левая вертикальная панель репозиториев

## 5.1 Верх панели: две кнопки
1. **`+` Add Repository**
2. **`⟳` Refresh All**

Расположение: горизонтально в один ряд над списком.

## 5.2 Список репозиториев: требования

### Структура элемента репозитория
- Иконка типа источника (`local`/`remote`).
- Название репозитория.
- Подстрока: ветка + время последнего обновления.
- Справа мини-кнопки:
  - `★` добавить/убрать из избранного;
  - `⟳` обновить только этот репозиторий;
  - опционально `…` (контекстное меню).

### Поведение
- **Drag & drop reorder** внутри списка.
- **Избранное наверху** (автосекция pinned/favorites).
- **Группировка (желательно — включена по умолчанию):**
  - Favorites
  - Local
  - Remote
  - Archived (опционально)
- Репозитории внутри группы перетаскиваются; между группами — по разрешенным правилам.

### Модель данных UI для списка
```python
RepoListItemVM(
  repo_id: int,
  title: str,
  source_type: Literal['local', 'remote'],
  group: Literal['favorites', 'local', 'remote', 'archived'],
  is_favorite: bool,
  last_updated_at: datetime | None,
  default_branch: str,
  health_grade: str | None,
)
```

### Персистентность порядка и групп
- Хранить в `settings`:
  - `repo_order` (json массив repo_id),
  - `repo_groups` (repo_id→group),
  - `repo_favorites` (set/list).

## 5.3 Добавление репозитория (диалог)
Поля:
- **Repository URL** (необязательное, если выбран local path).
- **Local Path** (необязательное, если указан URL).
- **Display Name** (опционально).
- `Import` / `Cancel`.

Валидация:
- должен быть указан хотя бы один источник;
- URL проверяется на git-совместимый формат;
- локальный путь должен существовать и быть git-репозиторием (или предложить clone).

---

## 6. Вкладки главного экрана

## 6.1 Вкладка 1: «Общая информация о проекте» (Overview)

Порядок блоков:
1. **Название проекта** (крупный заголовок).
2. Под заголовком: **кол-во файлов и строк кода**.
3. Блок **Quality Metrics Grades** (карточки A/B/C/…):
   - метрики сгруппированы по текущим анализаторам проекта (см. таблицу ниже);
   - если данных нет — `—` (прочерк);
   - по клику на карточку открывается правый Drawer/диалог с деталями.
4. Блок: **краткое описание `project_overview_backend.py`**
   - 1–3 абзаца;
   - рядом: кнопка «Regenerate».
5. Блок: **README** (если найден)
   - рендер markdown;
   - fallback: «README отсутствует».

### Оценки A/B/C/… (настраиваемые)
- В Settings пользователь задает пороги для каждой метрики.
- Формула grade вычисляется в application-слое; UI только отображает.

### Набор метрик (актуализировано под текущие раннеры)

| Группа | Короткое название в UI | Источник | Что показываем в карточке |
|---|---|---|---|
| Code Quality | **Линт** | `RuffRunner` | Кол-во замечаний Ruff, тренд к прошлому запуску, grade. |
| Type Safety | **Типы** | `MypyRunner` | Кол-во type errors/notes, доля файлов без ошибок, grade. |
| Testing | **Тесты** | `PytestRunner` | Passed/Failed/Skipped, длительность, grade по failed-rate. |
| Complexity | **Сложность** | `RadonRunner` (`radon cc`) | Кол-во блоков c rank B+ и max complexity, grade. |
| Maintainability | **Поддержка** | `RadonRunner` (`radon mi`) | Средний/минимальный MI и rank, grade. |
| Dead Code | **Мёртвый код** | `VultureRunner` | Кол-во находок vulture и confidence-порог, grade. |
| Duplication | **Дубли** | `DuplicationRunner` (планируемый; до внедрения — `—`) | % дублирования кода по проекту/модулю + grade. |
| AI Signals | **AI-сигнал** | `DetectAIAuthorshipUseCase` | Probability, confidence, top signals + дисклеймер (не «качество», а аналитический сигнал). |

> Примечание: карточка «Дубли» включена в UI в том же стандарте A–E. Пока отдельный раннер дублирования не подключен, показывается `—` и tooltip «метрика недоступна».

### Примерные критерии оценивания (A–E)

| Метрика | A | B | C | D | E |
|---|---:|---:|---:|---:|---:|
| Линт (ruff issues / KLOC) | 0–2 | 3–6 | 7–12 | 13–20 | >20 |
| Типы (mypy errors / KLOC) | 0 | 0.1–1 | 1.1–3 | 3.1–6 | >6 |
| Тесты (доля failed) | 0% | >0–2% | >2–5% | >5–10% | >10% |
| Сложность (доля B+ блоков) | <5% | 5–10% | 10–20% | 20–35% | >35% |
| Поддержка (средний MI) | ≥85 | 75–84 | 65–74 | 50–64 | <50 |
| Мёртвый код (vulture findings / KLOC) | 0–1 | 1.1–3 | 3.1–6 | 6.1–10 | >10 |
| **Дубли (% дублирования)** | **0–3%** | **>3–6%** | **>6–10%** | **>10–15%** | **>15%** |

> Эти границы стартовые и должны настраиваться в Settings профиля качества.

Пример карточки:
```text
┌ Complexity ───────┐
│ Grade: B          │
│ value: 7.8        │
│ threshold: A<6    │
└───────────────────┘
```

## 6.2 Вкладка 2: «История коммитов» (Commits)

Layout:
- **Слева/центр:** граф веток и коммитов (tree/graph).
- **Справа:** вертикальный список последних коммитов.

Требования:
- граф должен показывать ветвления/слияния;
- выбор коммита синхронизируется со списком справа;
- закладываем интерактивность под будущий checkout (пока read-only + подготовленные action hooks);
- фильтры сверху: branch, author, date range, text.

## 6.3 Вкладка 3: «Карта проекта» (Project Map)

Содержимое:
- интерактивный граф `module/file → class → function`;
- переключатель режимов:
  - structural view;
  - hotspot overlay;
- панель справа с деталями выбранного узла.

## 6.4 Вкладка 4: «Рабочее пространство» (Workspace)

Содержимое:
- список измененных файлов;
- diff по выбранному файлу (split/unified режимы);
- опциональные индикаторы: lint/issues/tests по файлу;
- quick actions: stage file / open in editor (если подключен).

Важно:
- только Working Tree Context;
- никаких checkout/reset/switch операций из этой вкладки.

---

## 7. Доработки сверх базовых требований (рекомендуется добавить)

1. **Глобальный поиск** (`Ctrl+K`): repo, commit, файл, символ.
2. **Фоновая очередь и статус-бар**:
   - индикатор активных задач;
   - прогресс обновления репозиториев/анализа.
3. **Системные уведомления**: успешно обновлен repo, ошибка pull, завершен анализ.
4. **Пустые/ошибочные состояния** для каждого экрана (skeleton + понятные действия).
5. **Disclaimers для AI-оценок** (вероятностная природа, не детектор факта).
6. **Горячие клавиши**:
   - `Ctrl+N` add repo,
   - `F5` refresh current,
   - `Ctrl+Shift+R` refresh all,
   - `Ctrl+1..4` переключение вкладок.

---

## 8. Визуальный стиль (темный современный)

## 8.1 Цветовые токены
- `bg/app`: `#0B1020`
- `bg/panel`: `#121A2B`
- `bg/elevated`: `#1A2438`
- `text/primary`: `#E6ECFF`
- `text/secondary`: `#9AA7C7`
- `accent`: `#5B8CFF`
- `success`: `#2EC27E`
- `warning`: `#F5C451`
- `danger`: `#F66151`

## 8.2 Типографика
- Базовый шрифт: Inter / Segoe UI / SF Pro fallback.
- Размеры: 13 (body), 15 (section), 20 (h2), 28 (h1).

## 8.3 Компонентный стиль
- Скругления 10–14 px.
- Мягкие тени и тонкие border (`#26324A`).
- Hover/pressed состояния обязательны для интерактивных элементов.

---

## 9. UX-сценарии

## 9.1 Добавление репозитория
1. Пользователь жмет `+`.
2. Вводит URL или local path.
3. `Import` → `ImportRepositoryUseCase`.
4. Новый repo появляется в нужной группе, доступен сразу.

## 9.2 Обновление одного репозитория
1. Нажатие `⟳` у элемента.
2. Запускается `git fetch/pull` + обновление cached summary.
3. UI показывает progress и timestamp обновления.

## 9.3 Refresh all
1. Нажатие верхней `⟳`.
2. Для каждого repo создается job (с ограничением параллелизма).
3. Итоговый отчет в status bar: `N success / M failed`.

## 9.4 Работа с метриками на вкладке Overview
1. Видны grade-карточки.
2. Клик по карточке → детальная панель: источники данных, значение, пороги, история тренда.
3. Названия карточек в UI короткие и русские: «Линт», «Типы», «Сложность», «Поддержка», «Мёртвый код», «Тесты», «Дубли», «AI-сигнал».

---

## 10. Привязка к существующим use-cases и backend

- Добавление репозитория: `ImportRepositoryUseCase`.
- История коммитов: `ListCommitsUseCase`.
- Отчет рабочей области: `WorkingTreeReportUseCase`.
- Карта проекта: `BuildProjectMapUseCase`.
- Project overview summary: `BuildProjectOverviewUseCase` + `infrastructure/ai/project_overview_backend.py`.

Примечание по текущему состоянию backend:
- в отчетах `CommitReportUseCase` и `WorkingTreeReportUseCase` уже напрямую участвуют `RuffRunner` и `PytestRunner`;
- метрики `RadonRunner` / `MypyRunner` / `VultureRunner` / `DetectAIAuthorshipUseCase` и будущий `DuplicationRunner` должны быть подключены в общий агрегатор dashboard-метрик (или отдельные фоновые job) и отображаться в тех же карточках Overview.

Принцип:
- UI не выполняет git/analysis напрямую;
- UI вызывает application use-cases и отображает DTO.

---

## 11. Минимальный MVP UI (порядок реализации)

### Sprint 1
- MainWindow + top menu + sidebar с repo list.
- Add repo dialog.
- Tabs shell (4 вкладки, базовый контент).

### Sprint 2
- Drag&drop reorder + favorites + persist settings.
- Overview tab с grades + README рендер.

### Sprint 3
- Commits tab: граф + правый список.
- Workspace tab: список файлов + diff viewer.

### Sprint 4
- Project map интерактив.
- Тонкая полировка dark theme + hotkeys + empty/error states.

---

## 12. Критерии приемки (acceptance criteria)

1. В левой панели есть кнопки `+` и `⟳`; добавление и обновление работает.
2. Репозитории можно перетаскивать, избранные закрепляются сверху.
3. Есть 4 вкладки: Overview, Commits, Project Map, Workspace.
4. Overview показывает название, файлы/LOC, quality grades, summary backend-модуля и README.
5. Commits-вкладка отображает граф веток/коммитов и список последних коммитов справа.
6. Workspace показывает diff по файлам.
7. Интерфейс по умолчанию в темной теме и сохраняет layout/preferences.

---

## 13. Риски и решения

- **Большой commit graph тормозит UI** → виртуализация + lazy loading + web canvas.
- **Долгий refresh всех repo** → очередь задач + ограничение concurrency + отмена.
- **Сложность drag&drop с grouping** → использовать `QStandardItemModel` + кастомные mime payload.
- **Неполные метрики/отсутствие тестов** → единый fallback `—` + tooltip с причиной.

---

## 14. Что еще было добавлено по сравнению с запросом

- Конкретизирован стек реализации (PySide6 + QWebEngine + QWebChannel).
- Добавлены data contracts (ViewModel) и схема хранения UI-настроек.
- Добавлены критерии приемки и поэтапный план реализации.
- Добавлены UX-паттерны: empty states, hotkeys, status bar job progress.
