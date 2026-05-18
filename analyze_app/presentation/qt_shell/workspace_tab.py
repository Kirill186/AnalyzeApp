from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from analyze_app.presentation.qt_shell.web_view_utils import render_html_template


class WorkspaceWebPage(QWebEnginePage):
    file_selected = Signal(str)
    mode_selected = Signal(str)
    view_selected = Signal(str)
    stage_requested = Signal(str)
    stage_all_requested = Signal()
    commit_requested = Signal(str, bool)
    push_requested = Signal()
    open_requested = Signal(str)
    working_tree_requested = Signal()

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:  # type: ignore[override]
        if url.scheme() != "analyzeapp":
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)
        if url.host().lower() != "workspace":
            return False

        params = parse_qs(url.query())
        file_path = (params.get("file") or [""])[0]
        mode = (params.get("value") or [""])[0].lower()
        view = (params.get("view") or [""])[0].lower()
        message = (params.get("message") or [""])[0]
        push = (params.get("push") or [""])[0].lower() in {"1", "true", "yes", "on"}
        action = (params.get("action") or [""])[0].lower()

        if action == "select" and file_path:
            self.file_selected.emit(file_path)
        elif action == "mode" and mode in {"split", "unified"}:
            self.mode_selected.emit(mode)
        elif action == "view" and view in {"diff", "before", "after"}:
            self.view_selected.emit(view)
        elif action == "stage" and file_path:
            self.stage_requested.emit(file_path)
        elif action == "stage_all":
            self.stage_all_requested.emit()
        elif action == "commit":
            self.commit_requested.emit(message, push)
        elif action == "push":
            self.push_requested.emit()
        elif action == "open" and file_path:
            self.open_requested.emit(file_path)
        elif action == "working_tree":
            self.working_tree_requested.emit()
        return False


class WorkspaceTab(QWidget):
    file_selected = Signal(str)
    stage_requested = Signal(str)
    stage_all_requested = Signal()
    commit_requested = Signal(str, bool)
    push_requested = Signal()
    open_requested = Signal(str)
    working_tree_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._files: list[dict[str, object]] = []
        self._diff_by_file: dict[str, str] = {}
        self._before_by_file: dict[str, str] = {}
        self._after_by_file: dict[str, str] = {}
        self._selected_file: str | None = None
        self._mode = "split"
        self._view = "diff"
        self._source = "working_tree"
        self._title = "Рабочее пространство"
        self._subtitle = ""
        self._action_status = ""
        self._can_stage = False
        self._can_commit = False
        self._can_push = False
        self._can_open = False
        self._can_browse_working_tree = False
        self._loading = False

        self.web = QWebEngineView()
        self.page = WorkspaceWebPage(self.web)
        self.page.file_selected.connect(self._on_file_selected)
        self.page.mode_selected.connect(self._on_mode_selected)
        self.page.view_selected.connect(self._on_view_selected)
        self.page.stage_requested.connect(self.stage_requested.emit)
        self.page.stage_all_requested.connect(self.stage_all_requested.emit)
        self.page.commit_requested.connect(self.commit_requested.emit)
        self.page.push_requested.connect(self.push_requested.emit)
        self.page.open_requested.connect(self.open_requested.emit)
        self.page.working_tree_requested.connect(self.working_tree_requested.emit)
        self.web.setPage(self.page)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.web)
        self._render()

    def set_workspace_data(
        self,
        files: list[dict[str, object]],
        diff_by_file: dict[str, str],
        selected_file: str | None = None,
    ) -> None:
        self.set_working_tree_data(files, diff_by_file, selected_file=selected_file)

    def set_working_tree_data(
        self,
        files: list[dict[str, object]],
        diff_by_file: dict[str, str],
        selected_file: str | None = None,
        message: str | None = None,
        can_write: bool = True,
    ) -> None:
        self._loading = False
        self._source = "working_tree"
        self._title = "Рабочее дерево"
        self._subtitle = message or "Локальные изменения относительно HEAD."
        self._action_status = ""
        self._can_stage = can_write
        self._can_commit = can_write
        self._can_push = can_write
        self._can_open = True
        self._can_browse_working_tree = False
        self._files = files
        self._diff_by_file = diff_by_file
        self._before_by_file = {}
        self._after_by_file = {}
        self._view = "diff"
        self._select_file(selected_file)
        self._render()

    def set_commit_data(
        self,
        commit_hash: str,
        commit_message: str,
        files: list[dict[str, object]],
        diff_by_file: dict[str, str],
        before_by_file: dict[str, str],
        after_by_file: dict[str, str],
        selected_file: str | None = None,
        parent_hash: str | None = None,
        can_browse_working_tree: bool = True,
    ) -> None:
        self._loading = False
        self._source = "commit"
        self._title = f"Коммит {commit_hash[:10]}"
        parent = f"сравнение с {parent_hash[:10]}" if parent_hash else "первый коммит"
        label = commit_message.strip() or "(без сообщения)"
        self._subtitle = f"{label} · {parent}"
        self._action_status = ""
        self._can_stage = False
        self._can_commit = False
        self._can_push = False
        self._can_open = False
        self._can_browse_working_tree = can_browse_working_tree
        self._files = files
        self._diff_by_file = diff_by_file
        self._before_by_file = before_by_file
        self._after_by_file = after_by_file
        if self._view not in {"diff", "before", "after"}:
            self._view = "diff"
        self._select_file(selected_file)
        self._render()

    def set_action_status(self, message: str) -> None:
        self._action_status = message
        self._render()

    def _select_file(self, selected_file: str | None = None) -> None:
        known_paths = {str(item.get("path") or "") for item in self._files}
        target = selected_file or self._selected_file or (self._files[0]["path"] if self._files else None)
        target_path = str(target) if target is not None else ""
        self._selected_file = target_path if target_path in known_paths else (
            str(self._files[0]["path"]) if self._files else None
        )

    def set_loading(self) -> None:
        self._loading = True
        self._source = "loading"
        self._title = "Рабочее пространство"
        self._subtitle = "Загружаю данные репозитория."
        self._action_status = ""
        self._can_stage = False
        self._can_commit = False
        self._can_push = False
        self._can_open = False
        self._can_browse_working_tree = False
        self._files = []
        self._diff_by_file = {}
        self._before_by_file = {}
        self._after_by_file = {}
        self._selected_file = None
        self._view = "diff"
        self._render()

    def clear(self) -> None:
        self._loading = False
        self._source = "empty"
        self._title = "Рабочее пространство"
        self._subtitle = "Выберите репозиторий или коммит."
        self._action_status = ""
        self._can_stage = False
        self._can_commit = False
        self._can_push = False
        self._can_open = False
        self._can_browse_working_tree = False
        self._files = []
        self._diff_by_file = {}
        self._before_by_file = {}
        self._after_by_file = {}
        self._selected_file = None
        self._view = "diff"
        self._render()

    def _on_file_selected(self, file_path: str) -> None:
        self._selected_file = file_path
        self.file_selected.emit(file_path)
        self._render()

    def _on_mode_selected(self, mode: str) -> None:
        if mode not in {"split", "unified"}:
            return
        self._mode = mode
        self._render()

    def _on_view_selected(self, view: str) -> None:
        if view not in {"diff", "before", "after"}:
            return
        self._view = view
        self._render()

    def _render(self) -> None:
        template_path = Path(__file__).with_name("web_assets") / "workspace.html"
        selected = self._selected_file or ""
        payload = {
            "files": self._files,
            "selectedFile": self._selected_file,
            "mode": self._mode,
            "view": self._view,
            "source": self._source,
            "title": self._title,
            "subtitle": self._subtitle,
            "actionStatus": self._action_status,
            "diffText": self._diff_by_file.get(selected, ""),
            "beforeText": self._before_by_file.get(selected, ""),
            "afterText": self._after_by_file.get(selected, ""),
            "canStage": self._can_stage,
            "canCommit": self._can_commit,
            "canPush": self._can_push,
            "canOpen": self._can_open,
            "canBrowseWorkingTree": self._can_browse_working_tree,
            "loading": self._loading,
        }
        html = render_html_template(template_path, payload)
        self.web.setHtml(html, QUrl.fromLocalFile(str(template_path.parent)))
