from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from analyze_app.presentation.qt_shell.state_store import RepoListItemVM


def _role_value(role) -> int:
    return int(getattr(role, "value", role))


REPO_ID_ROLE = _role_value(Qt.ItemDataRole.UserRole)
GROUP_KEY_ROLE = REPO_ID_ROLE + 1
REPO_GROUP_ROLE = REPO_ID_ROLE + 2

STANDARD_GROUPS = ("local", "remote", "archived")
GROUP_LABELS = {
    "local": "Локальные",
    "remote": "Удаленные",
    "archived": "Архив",
}


class RepoSidebar(QWidget):
    add_clicked = Signal()
    refresh_all_clicked = Signal()
    refresh_repo_clicked = Signal(int)
    favorite_toggled = Signal(int, bool)
    repo_group_changed = Signal(int, str)
    repo_order_changed = Signal(list)
    group_order_changed = Signal(list)
    group_renamed = Signal(str, str)
    group_delete_requested = Signal(str)
    repo_selected = Signal(int)
    repo_delete_requested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._item_map: dict[int, RepoListItemVM] = {}
        self._known_groups: list[str] = list(STANDARD_GROUPS)

        self.add_btn = QPushButton("+")
        self.add_btn.setToolTip("Добавить репозиторий")
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setToolTip("Обновить все репозитории")

        self.add_btn.clicked.connect(self.add_clicked.emit)
        self.refresh_btn.clicked.connect(self.refresh_all_clicked.emit)

        controls = QHBoxLayout()
        controls.addWidget(self.add_btn)
        controls.addWidget(self.refresh_btn)

        self.repo_list = _RepoListWidget()
        self.repo_list.itemClicked.connect(self._on_item_clicked)
        self.repo_list.itemSelectionChanged.connect(self._sync_card_selection)
        self.repo_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.repo_list.customContextMenuRequested.connect(self._open_context_menu)
        self.repo_list.repo_group_changed.connect(self.repo_group_changed.emit)
        self.repo_list.repo_order_changed.connect(self.repo_order_changed.emit)
        self.repo_list.group_order_changed.connect(self.group_order_changed.emit)

        root = QVBoxLayout(self)
        root.addLayout(controls)
        root.addWidget(self.repo_list)

    def set_repositories(self, repos: list[RepoListItemVM], groups: list[str] | None = None) -> None:
        selected_id = self._selected_repo_id()
        self._item_map = {item.repo_id: item for item in repos}
        self._known_groups = _known_group_keys(repos, groups or [])
        self.repo_list.clear()

        grouped: dict[str, list[RepoListItemVM]] = defaultdict(list)
        for repo in repos:
            grouped[_clean_group_key(repo.group, repo.source_type)].append(repo)

        for group in self._known_groups:
            group_repos = grouped[group]
            self._add_group_header(group)
            for repo in sorted(group_repos, key=lambda item: not item.is_favorite):
                self._add_repo_card(repo, selected_id)

        self._sync_card_selection()

    def _add_group_header(self, group: str) -> None:
        item = QListWidgetItem()
        item.setData(GROUP_KEY_ROLE, group)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        item.setSizeHint(QSize(280, 34))
        self.repo_list.addItem(item)

        label = QLabel(_group_label(group))
        label.setObjectName("repoGroupHeader")
        label.setStyleSheet(
            """
            QLabel#repoGroupHeader {
                color: #9AA7C7;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0px;
                padding: 10px 8px 4px 8px;
                text-transform: uppercase;
            }
            """
        )
        self.repo_list.setItemWidget(item, label)

    def _add_repo_card(self, repo: RepoListItemVM, selected_id: int | None) -> None:
        item = QListWidgetItem()
        item.setData(REPO_ID_ROLE, repo.repo_id)
        item.setData(REPO_GROUP_ROLE, _clean_group_key(repo.group, repo.source_type))
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )
        item.setSizeHint(QSize(280, 104))
        self.repo_list.addItem(item)
        self.repo_list.setItemWidget(item, _RepoCard(repo))
        if repo.repo_id == selected_id:
            item.setSelected(True)
            self.repo_list.setCurrentItem(item)

    def _selected_repo_id(self) -> int | None:
        item = self.repo_list.currentItem()
        if item is None:
            return None
        repo_id = item.data(REPO_ID_ROLE)
        return int(repo_id) if repo_id is not None else None

    def _sync_card_selection(self) -> None:
        for row in range(self.repo_list.count()):
            item = self.repo_list.item(row)
            widget = self.repo_list.itemWidget(item)
            if isinstance(widget, _RepoCard):
                widget.set_selected(item.isSelected())

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        repo_id = item.data(REPO_ID_ROLE)
        if repo_id is None:
            return
        self.repo_selected.emit(int(repo_id))

    def _open_context_menu(self, pos) -> None:
        item = self.repo_list.itemAt(pos)
        if item is None:
            return
        group = item.data(GROUP_KEY_ROLE)
        if group:
            self._open_group_context_menu(str(group), pos)
            return

        repo_id = item.data(REPO_ID_ROLE)
        if repo_id is None:
            return

        repo = self._item_map.get(int(repo_id))
        if repo is None:
            return

        menu = QMenu(self)
        favorite_action = menu.addAction(
            "Убрать из избранного" if repo.is_favorite else "Добавить в избранное"
        )
        refresh_action = menu.addAction("Обновить репозиторий")
        menu.addSeparator()

        group_menu = menu.addMenu("Переместить в группу")
        current_group = _clean_group_key(repo.group, repo.source_type)
        for group in self._known_groups:
            move_action = group_menu.addAction(_group_label(group))
            move_action.setData(group)
            move_action.setEnabled(group != current_group)
        group_menu.addSeparator()
        create_group_action = group_menu.addAction("Новая группа...")

        menu.addSeparator()
        delete_action = menu.addAction("Удалить репозиторий")

        action = menu.exec(self.repo_list.mapToGlobal(pos))
        if action is None:
            return
        if action == favorite_action:
            self.favorite_toggled.emit(repo.repo_id, not repo.is_favorite)
            return
        if action == refresh_action:
            self.refresh_repo_clicked.emit(repo.repo_id)
            return
        if action == create_group_action:
            self._prompt_for_group(repo.repo_id)
            return
        if action == delete_action:
            self.repo_delete_requested.emit(repo.repo_id)
            return

        target_group = action.data()
        if target_group:
            self.repo_group_changed.emit(repo.repo_id, str(target_group))

    def _open_group_context_menu(self, group: str, pos) -> None:
        menu = QMenu(self)
        rename_action = menu.addAction("Переименовать группу")
        delete_action = menu.addAction("Удалить группу")

        action = menu.exec(self.repo_list.mapToGlobal(pos))
        if action is None:
            return
        if action == rename_action:
            self._prompt_rename_group(group)
            return
        if action == delete_action:
            self.group_delete_requested.emit(group)

    def _prompt_for_group(self, repo_id: int) -> None:
        group_name, accepted = QInputDialog.getText(self, "Новая группа", "Название группы:")
        if not accepted:
            return
        group = group_name.strip()
        if not group or group == "favorites":
            return
        self.repo_group_changed.emit(repo_id, group)

    def _prompt_rename_group(self, group: str) -> None:
        group_name, accepted = QInputDialog.getText(
            self,
            "Переименовать группу",
            "Название группы:",
            QLineEdit.EchoMode.Normal,
            group,
        )
        if not accepted:
            return
        new_group = group_name.strip()
        if not new_group or new_group == "favorites" or new_group == group:
            return
        self.group_renamed.emit(group, new_group)


class _RepoListWidget(QListWidget):
    repo_group_changed = Signal(int, str)
    repo_order_changed = Signal(list)
    group_order_changed = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self._dragged_group: str | None = None
        self._dragged_repo_id: int | None = None
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSpacing(6)

    def startDrag(self, supported_actions) -> None:  # noqa: N802
        item = self.currentItem()
        group = item.data(GROUP_KEY_ROLE) if item else None
        repo_id = item.data(REPO_ID_ROLE) if item else None
        self._dragged_group = str(group) if group else None
        self._dragged_repo_id = int(repo_id) if repo_id is not None else None
        super().startDrag(supported_actions)

    def dropEvent(self, event) -> None:  # noqa: N802
        dragged_item = self.currentItem()
        dragged_group = self._dragged_group or (dragged_item.data(GROUP_KEY_ROLE) if dragged_item else None)
        dragged_repo_id = self._dragged_repo_id
        if dragged_repo_id is None and dragged_item:
            repo_id = dragged_item.data(REPO_ID_ROLE)
            dragged_repo_id = int(repo_id) if repo_id is not None else None
        target_item = self.itemAt(_event_pos(event))
        target_group = target_item.data(GROUP_KEY_ROLE) if target_item else None

        try:
            if dragged_repo_id is not None and target_group:
                event.ignore()
                self._schedule_repo_group_change(int(dragged_repo_id), str(target_group))
                return

            super().dropEvent(event)

            if dragged_group:
                self._schedule_group_order()
                return

            forced_groups = None
            if dragged_repo_id is not None and target_group:
                forced_groups = {int(dragged_repo_id): str(target_group)}
            self._schedule_layout_change(forced_groups=forced_groups)
        finally:
            self._dragged_group = None
            self._dragged_repo_id = None

    def _schedule_repo_group_change(self, repo_id: int, group: str) -> None:
        QTimer.singleShot(0, lambda: self.repo_group_changed.emit(repo_id, group))

    def _schedule_group_order(self) -> None:
        QTimer.singleShot(0, self._emit_group_order)

    def _schedule_layout_change(self, forced_groups: dict[int, str] | None = None) -> None:
        forced = dict(forced_groups or {})
        QTimer.singleShot(0, lambda: self._emit_layout_change(forced_groups=forced))

    def _emit_group_order(self) -> None:
        groups: list[str] = []
        for row in range(self.count()):
            group = self.item(row).data(GROUP_KEY_ROLE)
            if group and str(group) not in groups:
                groups.append(str(group))
        if groups:
            self.group_order_changed.emit(groups)

    def _emit_layout_change(self, forced_groups: dict[int, str] | None = None) -> None:
        order: list[int] = []
        group_changes: dict[int, str] = {}
        current_group: str | None = None
        group_order: list[str] = []

        for row in range(self.count()):
            item = self.item(row)
            header_group = item.data(GROUP_KEY_ROLE)
            if header_group:
                current_group = str(header_group)
                if current_group not in group_order:
                    group_order.append(current_group)
                continue

            repo_id_raw = item.data(REPO_ID_ROLE)
            if repo_id_raw is None:
                continue

            repo_id = int(repo_id_raw)
            order.append(repo_id)
            original_group = item.data(REPO_GROUP_ROLE)
            target_group = current_group or str(original_group or "")
            if target_group and target_group != original_group:
                group_changes[repo_id] = target_group

        group_changes.update(forced_groups or {})
        if group_order:
            self.group_order_changed.emit(group_order)
        for repo_id, group in group_changes.items():
            self.repo_group_changed.emit(repo_id, group)
        if order:
            self.repo_order_changed.emit(order)


class _RepoCard(QFrame):
    def __init__(self, repo: RepoListItemVM) -> None:
        super().__init__()
        self.setObjectName("repoCard")
        self.setProperty("favorite", "true" if repo.is_favorite else "false")
        self.setProperty("selected", "false")
        self.setToolTip(repo.working_path or repo.origin_url)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 9, 10, 9)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)

        title = QLabel(repo.title)
        title.setObjectName("repoTitle")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        top.addWidget(title, 1)

        star = QLabel("★" if repo.is_favorite else "☆")
        star.setObjectName("repoStar")
        star.setToolTip("В избранном" if repo.is_favorite else "Не в избранном")
        top.addWidget(star, 0, Qt.AlignmentFlag.AlignRight)
        root.addLayout(top)

        meta = QHBoxLayout()
        meta.setSpacing(6)

        branch = QLabel(repo.default_branch or "-")
        branch.setObjectName("repoBranch")
        branch.setToolTip("Текущая ветка по умолчанию")
        meta.addWidget(branch, 0)

        changed = QLabel(_relative_time(repo.last_updated_at))
        changed.setObjectName("repoTime")
        changed.setToolTip(_absolute_time(repo.last_updated_at))
        meta.addWidget(changed, 1)
        root.addLayout(meta)

        source = QLabel(_compact_source(repo))
        source.setObjectName("repoPath")
        source.setToolTip(repo.working_path or repo.origin_url)
        root.addWidget(source)

        self.setStyleSheet(
            """
            QFrame#repoCard {
                background: #172034;
                border: 1px solid #2E3A55;
                border-radius: 8px;
            }
            QFrame#repoCard[favorite="true"] {
                border-color: #D8B24D;
                background: #1D2534;
            }
            QFrame#repoCard[selected="true"] {
                border-color: #5B8CFF;
                background: #1C2A46;
            }
            QLabel#repoTitle {
                color: #F4F7FF;
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 0px;
            }
            QLabel#repoStar {
                color: #D8B24D;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#repoBranch {
                color: #DDE6FF;
                background: #24314C;
                border: 1px solid #34466A;
                border-radius: 6px;
                padding: 3px 7px;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#repoTime {
                color: #AFC5E8;
                font-size: 11px;
            }
            QLabel#repoPath {
                color: #7F8EAD;
                font-size: 11px;
            }
            """
        )

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)


def _event_pos(event):
    if hasattr(event, "position"):
        return event.position().toPoint()
    return event.pos()


def _known_group_keys(repos: list[RepoListItemVM], groups: list[str]) -> list[str]:
    ordered_groups: list[str] = []
    for group in groups:
        group = _clean_group_key(group, "")
        if group and group not in ordered_groups:
            ordered_groups.append(group)

    for repo in repos:
        group = _clean_group_key(repo.group, repo.source_type)
        if group not in ordered_groups:
            ordered_groups.append(group)
    return ordered_groups


def _group_label(group: str) -> str:
    return GROUP_LABELS.get(group, group)


def _clean_group_key(group: str, fallback: str) -> str:
    group = str(group or "").strip()
    if not group or group == "favorites":
        return fallback
    return group


def _relative_time(value: datetime | None) -> str:
    if value is None:
        return "нет коммитов"
    if value.tzinfo is None:
        now = datetime.now()
    else:
        now = datetime.now(value.tzinfo or timezone.utc)
    diff = now - value
    seconds = max(int(diff.total_seconds()), 0)
    if seconds < 60:
        return "изменен только что"
    minutes = seconds // 60
    if minutes < 60:
        return f"изменен {minutes} мин назад"
    hours = minutes // 60
    if hours < 24:
        return f"изменен {hours} ч назад"
    days = hours // 24
    if days < 30:
        return f"изменен {days} дн назад"
    months = days // 30
    if months < 12:
        return f"изменен {months} мес назад"
    years = days // 365
    return f"изменен {years} г назад"


def _absolute_time(value: datetime | None) -> str:
    if value is None:
        return "В репозитории пока нет коммитов или дата недоступна"
    return f"Последний коммит: {value.astimezone().strftime('%Y-%m-%d %H:%M')}"


def _compact_source(repo: RepoListItemVM) -> str:
    source = repo.origin_url if repo.source_type == "remote" and repo.origin_url else repo.working_path
    if not source:
        return ""
    if repo.source_type == "remote":
        return source.removesuffix(".git").rsplit("/", 1)[-1]
    path = Path(source)
    parent = path.parent.name
    return f"{parent}/{path.name}" if parent else path.name
