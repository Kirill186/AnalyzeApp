from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from analyze_app.presentation.qt_shell.state_store import DEFAULT_QUALITY_THRESHOLDS, UiStateStore


QUALITY_FIELDS: list[tuple[str, str]] = [
    ("lint_issues_per_kloc", "Линт (ruff issues / KLOC)"),
    ("mypy_errors_per_kloc", "Типы (mypy errors / KLOC)"),
    ("tests_failed_rate_pct", "Тесты (доля failed, %)"),
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
