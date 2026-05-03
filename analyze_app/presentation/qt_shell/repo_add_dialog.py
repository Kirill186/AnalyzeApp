from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class RepoAddDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Repository")
        self.setMinimumWidth(500)

        self.source_type_combo = QComboBox()
        self.source_type_combo.addItem("Remote URL", "remote")
        self.source_type_combo.addItem("Local folder", "local")

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://github.com/org/repo.git")
        self.path_edit = QLineEdit()
        self.display_name_edit = QLineEdit()

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_path)

        path_layout = QHBoxLayout()
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(browse_btn)

        remote_page = QWidget()
        remote_layout = QFormLayout(remote_page)
        remote_layout.setContentsMargins(0, 0, 0, 0)
        remote_layout.addRow("Repository URL", self.url_edit)

        local_page = QWidget()
        local_layout = QFormLayout(local_page)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.addRow("Local Path", path_layout)

        self.source_stack = QStackedWidget()
        self.source_stack.addWidget(remote_page)
        self.source_stack.addWidget(local_page)
        self.source_type_combo.currentIndexChanged.connect(self.source_stack.setCurrentIndex)

        form = QFormLayout()
        form.addRow("Add as", self.source_type_combo)
        form.addRow(self.source_stack)
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
        if self.source_type == "remote":
            url = self.url_edit.text().strip()
            if not url:
                QMessageBox.warning(self, "Validation", "Enter a Repository URL.")
                return
            if not (url.startswith("http://") or url.startswith("https://") or url.endswith(".git")):
                QMessageBox.warning(self, "Validation", "URL must be git-compatible.")
                return
            self.accept()
            return

        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "Validation", "Choose a Local Path.")
            return
        local_path = Path(path).expanduser().resolve()
        if not local_path.exists() or not local_path.is_dir():
            QMessageBox.warning(self, "Validation", "Local Path must exist and be a folder.")
            return
        if not (local_path / ".git").exists():
            QMessageBox.warning(
                self,
                "Validation",
                "Selected folder does not look like a git repository (.git was not found).",
            )
            return
        self.accept()

    @property
    def source_type(self) -> str:
        return str(self.source_type_combo.currentData())

    @property
    def source(self) -> str:
        if self.source_type == "local":
            return self.path_edit.text().strip()
        return self.url_edit.text().strip()

    @property
    def display_name(self) -> str:
        return self.display_name_edit.text().strip()
