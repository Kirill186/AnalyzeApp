from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
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
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from analyze_app.infrastructure.analysis.ruff_settings import RUFF_RULE_GROUPS, RegexRule, RuffSettings
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


class RuffSettingsDialog(QDialog):
    def __init__(self, state_store: UiStateStore, parent=None) -> None:
        super().__init__(parent)
        self.state_store = state_store
        self.setWindowTitle("Ruff Rules")
        self.setMinimumSize(860, 620)

        current = self.state_store.ruff_settings()
        known_codes = {code for code, _label in RUFF_RULE_GROUPS}
        extra_select = [code for code in current.select if code not in known_codes]

        root = QVBoxLayout(self)
        intro = QLabel(
            "Настройки Ruff применяются при анализе репозитория. В режиме repository config AnalyzeApp "
            "не передает Ruff дополнительные select/ignore параметры."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        ruff_group = QGroupBox("Built-in Ruff rules")
        ruff_layout = QVBoxLayout(ruff_group)
        form = QFormLayout()

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Repository config", "respect")
        self.mode_combo.addItem("Extend repository config", "extend")
        self.mode_combo.addItem("AnalyzeApp profile", "override")
        self.mode_combo.setCurrentIndex(max(self.mode_combo.findData(current.mode), 0))
        form.addRow("Mode", self.mode_combo)

        self.preview_checkbox = QCheckBox("Enable Ruff preview rules")
        self.preview_checkbox.setChecked(current.preview)
        form.addRow("Preview", self.preview_checkbox)

        ruff_layout.addLayout(form)

        checks_group = QGroupBox("Selected groups")
        checks_grid = QGridLayout(checks_group)
        self.rule_checks: dict[str, QCheckBox] = {}
        for index, (code, label) in enumerate(RUFF_RULE_GROUPS):
            checkbox = QCheckBox(f"{code} - {label}")
            checkbox.setChecked(code in current.select)
            self.rule_checks[code] = checkbox
            checks_grid.addWidget(checkbox, index // 2, index % 2)
        ruff_layout.addWidget(checks_group)

        advanced_form = QFormLayout()
        self.extra_select = QLineEdit(", ".join(extra_select))
        self.extra_select.setPlaceholderText("ANN, C4, N, PTH")
        advanced_form.addRow("Extra select", self.extra_select)

        self.ignore_codes = QLineEdit(", ".join(current.ignore))
        self.ignore_codes.setPlaceholderText("E501, S101")
        advanced_form.addRow("Ignore", self.ignore_codes)
        ruff_layout.addLayout(advanced_form)
        root.addWidget(ruff_group)

        custom_group = QGroupBox("Simple custom rules")
        custom_layout = QVBoxLayout(custom_group)
        self.custom_enabled = QCheckBox("Run simple custom rules after Ruff")
        self.custom_enabled.setChecked(current.custom_rules_enabled)
        custom_layout.addWidget(self.custom_enabled)

        calls_row = QHBoxLayout()
        self.forbidden_calls = QLineEdit(", ".join(current.forbidden_calls))
        self.forbidden_calls.setPlaceholderText("print, breakpoint, pdb.set_trace")
        add_print_button = QPushButton("Add print")
        add_print_button.clicked.connect(self._add_print_rule)
        calls_row.addWidget(self.forbidden_calls, 1)
        calls_row.addWidget(add_print_button)

        calls_form = QFormLayout()
        calls_form.addRow("Forbidden calls", calls_row)
        custom_layout.addLayout(calls_form)

        regex_label = QLabel("Regex rules: one line per rule, format pattern :: message.")
        regex_label.setWordWrap(True)
        custom_layout.addWidget(regex_label)

        self.regex_rules = QPlainTextEdit(self._format_regex_rules(current.regex_rules))
        self.regex_rules.setPlaceholderText(r"TODO|FIXME :: unfinished marker is not allowed")
        self.regex_rules.setMinimumHeight(120)
        custom_layout.addWidget(self.regex_rules)
        root.addWidget(custom_group)

        reset_row = QHBoxLayout()
        reset_row.addStretch()
        reset_button = QPushButton("Reset")
        reset_button.clicked.connect(self._reset_to_defaults)
        reset_row.addWidget(reset_button)
        root.addLayout(reset_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _add_print_rule(self) -> None:
        calls = self._parse_forbidden_calls(self.forbidden_calls.text())
        if "print" not in calls:
            calls.append("print")
        self.forbidden_calls.setText(", ".join(calls))

    def _reset_to_defaults(self) -> None:
        defaults = RuffSettings()
        self.mode_combo.setCurrentIndex(max(self.mode_combo.findData(defaults.mode), 0))
        for code, checkbox in self.rule_checks.items():
            checkbox.setChecked(code in defaults.select)
        self.extra_select.clear()
        self.ignore_codes.clear()
        self.preview_checkbox.setChecked(defaults.preview)
        self.custom_enabled.setChecked(defaults.custom_rules_enabled)
        self.forbidden_calls.clear()
        self.regex_rules.clear()

    def _accept(self) -> None:
        calls = self._parse_forbidden_calls(self.forbidden_calls.text())
        invalid_calls = [call for call in calls if not self._is_valid_call_name(call)]
        if invalid_calls:
            QMessageBox.warning(
                self,
                "Некорректное правило",
                f"Недопустимое имя вызова: {', '.join(invalid_calls)}",
            )
            return

        regex_rules = self._parse_regex_rules()
        if regex_rules is None:
            return

        selected = [code for code, checkbox in self.rule_checks.items() if checkbox.isChecked()]
        selected.extend(code for code in self._parse_code_list(self.extra_select.text()) if code not in selected)

        self.state_store.set_ruff_settings(
            RuffSettings(
                mode=str(self.mode_combo.currentData()),  # type: ignore[arg-type]
                select=selected,
                ignore=self._parse_code_list(self.ignore_codes.text()),
                preview=self.preview_checkbox.isChecked(),
                custom_rules_enabled=self.custom_enabled.isChecked(),
                forbidden_calls=calls,
                regex_rules=regex_rules,
            )
        )
        self.accept()

    def _parse_regex_rules(self) -> list[RegexRule] | None:
        rules: list[RegexRule] = []
        for line_no, raw_line in enumerate(self.regex_rules.toPlainText().splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            pattern, separator, message = line.partition("::")
            pattern = pattern.strip()
            message = message.strip() if separator else ""
            if not pattern:
                continue
            try:
                re.compile(pattern)
            except re.error as error:
                QMessageBox.warning(
                    self,
                    "Некорректное regex-правило",
                    f"Строка {line_no}: {error}",
                )
                return None
            rules.append(RegexRule(pattern=pattern, message=message))
        return rules

    @staticmethod
    def _format_regex_rules(rules: list[RegexRule]) -> str:
        lines: list[str] = []
        for rule in rules:
            if not rule.enabled:
                continue
            line = rule.pattern.strip()
            if rule.message.strip():
                line = f"{line} :: {rule.message.strip()}"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _parse_code_list(value: str) -> list[str]:
        parsed: list[str] = []
        for item in value.replace(",", " ").split():
            code = item.strip().upper()
            if code and code not in parsed:
                parsed.append(code)
        return parsed

    @staticmethod
    def _parse_forbidden_calls(value: str) -> list[str]:
        parsed: list[str] = []
        for item in value.replace(",", " ").split():
            call_name = item.strip()
            if call_name and call_name not in parsed:
                parsed.append(call_name)
        return parsed

    @staticmethod
    def _is_valid_call_name(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", value))


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

        authorship_group = QGroupBox("AI-оценка кода")
        authorship_layout = QVBoxLayout(authorship_group)
        self.use_solution_chunks = QCheckBox("Делить код на solution-like куски")
        self.use_solution_chunks.setChecked(current.use_solution_chunks)
        self.use_solution_chunks.setToolTip(
            "Если выключить, AI-оценка будет передавать модели целые .py файлы."
        )
        authorship_layout.addWidget(self.use_solution_chunks)

        authorship_hint = QLabel(
            "Включённый режим лучше изолирует функции и методы. "
            "Выключенный режим оценивает каждый Python-файл целиком."
        )
        authorship_hint.setWordWrap(True)
        authorship_layout.addWidget(authorship_hint)
        root.addWidget(authorship_group)

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
                use_solution_chunks=self.use_solution_chunks.isChecked(),
            )
        )
        self.accept()
