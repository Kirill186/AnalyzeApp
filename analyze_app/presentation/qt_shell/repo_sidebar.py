from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from analyze_app.presentation.qt_shell.state_store import RepoListItemVM


class RepoSidebar(QWidget):
    add_clicked = Signal()
    refresh_all_clicked = Signal()
    refresh_repo_clicked = Signal(int)
    favorite_toggled = Signal(int, bool)
    repo_selected = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._item_map: dict[int, RepoListItemVM] = {}

        self.add_btn = QPushButton("+")
        self.add_btn.setToolTip("Add repository")
        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setToolTip("Refresh all repositories")

        self.add_btn.clicked.connect(self.add_clicked.emit)
        self.refresh_btn.clicked.connect(self.refresh_all_clicked.emit)

        controls = QHBoxLayout()
        controls.addWidget(self.add_btn)
        controls.addWidget(self.refresh_btn)

        self.repo_list = QListWidget()
        self.repo_list.itemClicked.connect(self._on_item_clicked)

        root = QVBoxLayout(self)
        root.addLayout(controls)
        root.addWidget(self.repo_list)

    def set_repositories(self, repos: list[RepoListItemVM]) -> None:
        self._item_map = {item.repo_id: item for item in repos}
        self.repo_list.clear()
        grouped: dict[str, list[RepoListItemVM]] = defaultdict(list)
        for repo in repos:
            key = "favorites" if repo.is_favorite else repo.group
            grouped[key].append(repo)

        for group in ["favorites", "local", "remote", "archived"]:
            if not grouped[group]:
                continue
            header = QListWidgetItem(group.capitalize())
            header.setFlags(Qt.NoItemFlags)
            self.repo_list.addItem(header)
            for repo in grouped[group]:
                star = "★" if repo.is_favorite else "☆"
                subtitle = repo.last_updated_at.isoformat(timespec="minutes") if repo.last_updated_at else "never"
                text = f"{star} {repo.title}\n{repo.default_branch} • {subtitle}"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, repo.repo_id)
                self.repo_list.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        repo_id = item.data(Qt.UserRole)
        if repo_id is None:
            return
        self.repo_selected.emit(int(repo_id))
