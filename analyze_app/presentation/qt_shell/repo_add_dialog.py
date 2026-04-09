from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class RepoAddDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Repository")
        self.setMinimumWidth(500)

        self.url_edit = QLineEdit()
        self.path_edit = QLineEdit()
        self.display_name_edit = QLineEdit()

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_path)

        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(browse_btn)

        form = QFormLayout()
        form.addRow("Repository URL", self.url_edit)
        form.addRow("Local Path", path_layout)
        form.addRow("Display Name", self.display_name_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(buttons)

    def _browse_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select repository path")
        if folder:
            self.path_edit.setText(folder)

    def _validate_accept(self) -> None:
        url = self.url_edit.text().strip()
        path = self.path_edit.text().strip()
        if not url and not path:
            QMessageBox.warning(self, "Validation", "Укажите Repository URL или Local Path.")
            return
        if url and not (url.startswith("http://") or url.startswith("https://") or url.endswith(".git")):
            QMessageBox.warning(self, "Validation", "URL должен быть git-совместимым.")
            return
        self.accept()

    @property
    def source(self) -> str:
        return self.path_edit.text().strip() or self.url_edit.text().strip()

    @property
    def display_name(self) -> str:
        return self.display_name_edit.text().strip()
