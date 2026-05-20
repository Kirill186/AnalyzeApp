from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from analyze_app.presentation.qt_shell.state_store import AISettings, DEFAULT_QUALITY_THRESHOLDS, UiStateStore


@dataclass(frozen=True, slots=True)
class QualityField:
    key: str
    label: str
    hint: str
    direction: str
    suffix: str
    step: float
    decimals: int
    maximum: float


QUALITY_FIELDS: list[QualityField] = [
    QualityField("lint_issues_per_kloc", "Линт", "ruff issues / KLOC", "lower", " /KLOC", 0.1, 1, 10_000.0),
    QualityField("mypy_errors_per_kloc", "Типы", "mypy errors / KLOC", "lower", " /KLOC", 0.1, 1, 10_000.0),
    QualityField("tests_passed_rate_pct", "Тесты", "доля passed", "upper", "%", 1.0, 1, 100.0),
    QualityField("complexity_b_plus_share_pct", "Сложность", "доля B+ блоков", "lower", "%", 1.0, 1, 100.0),
    QualityField("maintainability_avg_mi", "Поддержка", "средний MI", "upper", "", 1.0, 1, 100.0),
    QualityField("dead_code_findings_per_kloc", "Мёртвый код", "findings / KLOC", "lower", " /KLOC", 0.1, 1, 10_000.0),
    QualityField("duplication_pct", "Дубли", "дублирование", "lower", "%", 1.0, 1, 100.0),
]


class QualitySettingsDialog(QDialog):
    def __init__(self, state_store: UiStateStore, parent=None) -> None:
        super().__init__(parent)
        self.state_store = state_store
        self.setWindowTitle("Quality Grades")
        self.setMinimumSize(900, 420)

        root = QVBoxLayout(self)
        intro = QLabel(
            "Пороги для оценок A/B/C/D. E — всё, что хуже D. "
            "Для метрик, где меньше лучше, значения — верхние границы; где больше лучше — нижние границы."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        group = QGroupBox("Границы оценивания")
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        headers = ["Метрика", "Правило", "A", "B", "C", "D"]
        for column, title in enumerate(headers):
            header = QLabel(f"<b>{title}</b>")
            grid.addWidget(header, 0, column)

        self.fields: dict[str, list[QDoubleSpinBox]] = {}
        self.field_labels: dict[str, str] = {}
        self.field_directions: dict[str, str] = {}

        thresholds = self.state_store.quality_thresholds()
        for row, field in enumerate(QUALITY_FIELDS, start=1):
            values = thresholds.get(field.key, DEFAULT_QUALITY_THRESHOLDS[field.key])
            metric_label = QLabel(f"{field.label}\n{field.hint}")
            metric_label.setWordWrap(True)
            grid.addWidget(metric_label, row, 0)

            if field.direction == "lower":
                rule = "меньше — лучше\nA/B/C/D: до значения"
            else:
                rule = "больше — лучше\nA/B/C/D: от значения"
            rule_label = QLabel(rule)
            rule_label.setWordWrap(True)
            grid.addWidget(rule_label, row, 1)

            editors: list[QDoubleSpinBox] = []
            for column, value in enumerate(values[:4], start=2):
                editor = QDoubleSpinBox()
                editor.setRange(0.0, field.maximum)
                editor.setDecimals(field.decimals)
                editor.setSingleStep(field.step)
                editor.setValue(float(value))
                editor.setSuffix(field.suffix)
                editor.setKeyboardTracking(False)
                editor.setMinimumWidth(112)
                grid.addWidget(editor, row, column)
                editors.append(editor)

            self.fields[field.key] = editors
            self.field_labels[field.key] = field.label
            self.field_directions[field.key] = field.direction

        root.addWidget(group)

        reset_row = QHBoxLayout()
        reset_row.addStretch()
        reset_button = QPushButton("Сбросить пороги")
        reset_button.clicked.connect(self._reset_to_defaults)
        reset_row.addWidget(reset_button)
        root.addLayout(reset_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _reset_to_defaults(self) -> None:
        for key, editors in self.fields.items():
            for editor, value in zip(editors, DEFAULT_QUALITY_THRESHOLDS[key], strict=False):
                editor.setValue(float(value))

    def _accept(self) -> None:
        parsed: dict[str, list[float]] = {}
        for key, editors in self.fields.items():
            values = [editor.value() for editor in editors]
            direction = self.field_directions[key]
            if direction == "lower" and values != sorted(values):
                QMessageBox.warning(
                    self,
                    "Некорректные пороги",
                    f"Для метрики «{self.field_labels[key]}» значения A/B/C/D должны идти по возрастанию.",
                )
                return
            if direction == "upper" and values != sorted(values, reverse=True):
                QMessageBox.warning(
                    self,
                    "Некорректные пороги",
                    f"Для метрики «{self.field_labels[key]}» значения A/B/C/D должны идти по убыванию.",
                )
                return
            parsed[key] = values

        self.state_store.set_quality_thresholds(parsed)
        self.accept()


class CodeEditorSettingsDialog(QDialog):
    def __init__(self, state_store: UiStateStore, parent=None) -> None:
        super().__init__(parent)
        self.state_store = state_store
        self.setWindowTitle("Code Editor")
        self.setMinimumWidth(720)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Команда редактора для открытия файлов из AnalyzeApp. Пустое поле включает автоопределение."))

        group = QGroupBox("Editor")
        form = QFormLayout(group)

        self.editor_command = QLineEdit(self.state_store.editor_command())
        self.editor_command.setPlaceholderText("code --reuse-window")
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse_editor)
        auto_button = QPushButton("Auto")
        auto_button.clicked.connect(self.editor_command.clear)

        editor_row = QHBoxLayout()
        editor_row.addWidget(self.editor_command, 1)
        editor_row.addWidget(browse_button)
        editor_row.addWidget(auto_button)
        form.addRow("Command", editor_row)

        root.addWidget(group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _browse_editor(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select editor executable",
            "",
            "Applications (*.exe);;All files (*)",
        )
        if path:
            self.editor_command.setText(f'"{path}"')

    def _accept(self) -> None:
        self.state_store.set_editor_command(self.editor_command.text())
        self.accept()


class AISettingsDialog(QDialog):
    def __init__(self, state_store: UiStateStore, parent=None) -> None:
        super().__init__(parent)
        self.state_store = state_store
        self.setWindowTitle("AI Model")
        self.setMinimumWidth(760)

        current = self.state_store.ai_settings()

        root = QVBoxLayout(self)

        group = QGroupBox("LLM backend")
        form = QFormLayout(group)

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("GGUF / llama.cpp", "llama_cpp")
        self.backend_combo.addItem("Ollama service", "ollama")
        self.backend_combo.setCurrentIndex(max(self.backend_combo.findData(current.backend), 0))
        self.backend_combo.currentIndexChanged.connect(self._sync_backend_fields)
        form.addRow("Backend", self.backend_combo)

        self.model_path = QLineEdit(current.model_path)
        self.model_path.setPlaceholderText("ollama://llama3.2:latest или C:\\models\\model.gguf")
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse_model)
        ollama_cache_button = QPushButton("Use llama3.2 cache")
        ollama_cache_button.clicked.connect(lambda: self.model_path.setText("ollama://llama3.2:latest"))

        model_row = QHBoxLayout()
        model_row.addWidget(self.model_path, 1)
        model_row.addWidget(browse_button)
        model_row.addWidget(ollama_cache_button)
        form.addRow("GGUF model", model_row)

        self.context_size = QSpinBox()
        self.context_size.setRange(512, 262_144)
        self.context_size.setSingleStep(512)
        self.context_size.setValue(current.context_size)
        form.addRow("Context size", self.context_size)

        self.threads = QSpinBox()
        self.threads.setRange(0, 256)
        self.threads.setValue(current.threads)
        self.threads.setSpecialValueText("Auto")
        form.addRow("CPU threads", self.threads)

        self.gpu_layers = QSpinBox()
        self.gpu_layers.setRange(-1, 999)
        self.gpu_layers.setValue(current.gpu_layers)
        form.addRow("GPU layers", self.gpu_layers)

        self.ollama_url = QLineEdit(current.ollama_url)
        form.addRow("Ollama URL", self.ollama_url)

        self.ollama_model = QLineEdit(current.ollama_model)
        form.addRow("Ollama model", self.ollama_model)

        root.addWidget(group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._sync_backend_fields()

    def _browse_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select GGUF model",
            "",
            "GGUF models (*.gguf);;All files (*)",
        )
        if path:
            self.model_path.setText(path)

    def _sync_backend_fields(self) -> None:
        backend = str(self.backend_combo.currentData())
        use_llama_cpp = backend == "llama_cpp"
        self.model_path.setEnabled(use_llama_cpp)
        self.context_size.setEnabled(use_llama_cpp)
        self.threads.setEnabled(use_llama_cpp)
        self.gpu_layers.setEnabled(use_llama_cpp)
        self.ollama_url.setEnabled(not use_llama_cpp)
        self.ollama_model.setEnabled(not use_llama_cpp)

    def _accept(self) -> None:
        backend = str(self.backend_combo.currentData())
        model_path = self.model_path.text().strip()
        if backend == "llama_cpp" and not model_path:
            QMessageBox.warning(self, "Некорректный ввод", "Укажите путь к GGUF-модели или ollama://model:tag.")
            return
        if backend == "ollama" and not self.ollama_model.text().strip():
            QMessageBox.warning(self, "Некорректный ввод", "Укажите имя модели Ollama.")
            return

        self.state_store.set_ai_settings(
            AISettings(
                backend=backend,  # type: ignore[arg-type]
                model_path=model_path,
                context_size=self.context_size.value(),
                threads=self.threads.value(),
                gpu_layers=self.gpu_layers.value(),
                ollama_url=self.ollama_url.text().strip(),
                ollama_model=self.ollama_model.text().strip(),
            )
        )
        self.accept()
