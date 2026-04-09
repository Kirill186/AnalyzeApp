from __future__ import annotations

from PySide6.QtWidgets import QTabWidget

from analyze_app.presentation.qt_shell.commits_tab import CommitsTab
from analyze_app.presentation.qt_shell.overview_tab import OverviewTab
from analyze_app.presentation.qt_shell.project_map_tab import ProjectMapTab
from analyze_app.presentation.qt_shell.workspace_tab import WorkspaceTab


class ReportTabs(QTabWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.overview_tab = OverviewTab()
        self.commits_tab = CommitsTab()
        self.project_map_tab = ProjectMapTab()
        self.workspace_tab = WorkspaceTab()

        self.addTab(self.overview_tab, "Обзор")
        self.addTab(self.commits_tab, "История")
        self.addTab(self.project_map_tab, "Карта")
        self.addTab(self.workspace_tab, "WS")
