from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
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


QUALITY_FIELDS: list[tuple[str, str]] = [
    ("lint_issues_per_kloc", "Линт (ruff issues / KLOC)"),
    ("mypy_errors_per_kloc", "Типы (mypy errors / KLOC)"),
    ("tests_passed_rate_pct", "Тесты (доля passed, %)"),
    ("complexity_b_plus_share_pct", "Сложность (доля B+ блоков, %)"),
    ("maintainability_avg_mi", "Поддержка (средний MI)"),
    ("dead_code_findings_per_kloc", "Мёртвый код (findings / KLOC)"),
    ("duplication_pct", "Дубли (% дублирования)"),
]


class QualitySettingsDialog(QDialog):
    def __init__(self, state_store: UiStateStore, parent=None) -> None:
        super().__init__(parent)
        self.state_store = state_store
        self.setWindowTitle("Quality Grades")
        self.setMinimumWidth(760)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Пороги для оценок A/B/C/D. E — всё, что хуже D."))

        group = QGroupBox("Границы метрик")
        form = QFormLayout(group)
        self.fields: dict[str, QLineEdit] = {}

        thresholds = self.state_store.quality_thresholds()
        for key, label in QUALITY_FIELDS:
            values = thresholds.get(key, DEFAULT_QUALITY_THRESHOLDS[key])
            editor = QLineEdit(", ".join(str(value).rstrip("0").rstrip(".") if float(value).is_integer() else str(value) for value in values))
            editor.setPlaceholderText("Например: 2, 6, 12, 20")
            form.addRow(label, editor)
            self.fields[key] = editor

        root.addWidget(group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _accept(self) -> None:
        parsed: dict[str, list[float]] = {}
        for key, editor in self.fields.items():
            raw = editor.text().strip()
            try:
                values = [float(chunk.strip()) for chunk in raw.split(",") if chunk.strip()]
            except ValueError:
                QMessageBox.warning(self, "Некорректный ввод", f"Поле '{key}' должно содержать только числа.")
                return
            if len(values) != 4:
                QMessageBox.warning(self, "Некорректный ввод", f"Поле '{key}' должно содержать 4 значения.")
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
