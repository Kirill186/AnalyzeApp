from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow


@dataclass(slots=True)
class AppMenuActions:
    add_repository: QAction
    refresh_current: QAction
    refresh_all: QAction
    rebuild_map: QAction
    run_working_tree: QAction
    run_commit: QAction
    toggle_sidebar: QAction
    quality_grades: QAction


def build_menu(window: QMainWindow) -> AppMenuActions:
    menu_bar = window.menuBar()

    file_menu = menu_bar.addMenu("File")
    add_repository = file_menu.addAction("Add Repository…")
    refresh_current = file_menu.addAction("Refresh Current Repository")
    refresh_all = file_menu.addAction("Refresh All Repositories")
    file_menu.addSeparator()
    file_menu.addAction("Exit", window.close)

    view_menu = menu_bar.addMenu("View")
    toggle_sidebar = view_menu.addAction("Toggle Left Sidebar")

    analyze_menu = menu_bar.addMenu("Analyze")
    rebuild_map = analyze_menu.addAction("Rebuild Project Map")
    run_working_tree = analyze_menu.addAction("Run Working Tree Analysis")
    run_commit = analyze_menu.addAction("Run Commit Analysis")

    settings_menu = menu_bar.addMenu("Settings")
    quality_grades = settings_menu.addAction("Quality Grades")

    menu_bar.addMenu("Help")

    return AppMenuActions(
        add_repository=add_repository,
        refresh_current=refresh_current,
        refresh_all=refresh_all,
        rebuild_map=rebuild_map,
        run_working_tree=run_working_tree,
        run_commit=run_commit,
        toggle_sidebar=toggle_sidebar,
        quality_grades=quality_grades,
    )
