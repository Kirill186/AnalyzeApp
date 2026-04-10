from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from analyze_app.domain.entities import Commit


@dataclass(slots=True)
class _NodeLayout:
    lane: int
    row: int


class _CommitGraphView(QGraphicsView):
    commit_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self._cards: dict[str, QGraphicsRectItem] = {}
        self._selected_hash: str | None = None

    def set_commits(self, commits: list[Commit]) -> None:
        self.scene.clear()
        self._cards.clear()
        self._selected_hash = None
        if not commits:
            return

        layout = self._build_layout(commits)
        card_w = 260
        card_h = 64
        lane_step = 320
        row_step = 110
        x_offset = 36
        y_offset = 24

        points: dict[str, QPointF] = {}
        for commit in commits:
            node = layout[commit.hash]
            x = x_offset + (node.lane * lane_step)
            y = y_offset + (node.row * row_step)
            center_x = x + card_w / 2
            center_y = y + card_h / 2
            points[commit.hash] = QPointF(center_x, center_y)

        edge_pen = QPen(QColor("#5B8CFF"), 2)
        for commit in commits:
            start = points.get(commit.hash)
            if not start:
                continue
            for parent_hash in commit.parents:
                end = points.get(parent_hash)
                if not end:
                    continue
                mid_y = (start.y() + end.y()) / 2
                self.scene.addLine(start.x(), start.y() + card_h / 2 - 6, start.x(), mid_y, edge_pen)
                self.scene.addLine(start.x(), mid_y, end.x(), mid_y, edge_pen)
                self.scene.addLine(end.x(), mid_y, end.x(), end.y() - card_h / 2 + 6, edge_pen)

        for commit in commits:
            node = layout[commit.hash]
            x = x_offset + (node.lane * lane_step)
            y = y_offset + (node.row * row_step)
            card = QGraphicsRectItem(x, y, card_w, card_h)
            card.setBrush(QColor("#1A2438"))
            card.setPen(QPen(QColor("#26324A"), 1.4))
            card.setData(0, commit.hash)
            card.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.scene.addItem(card)

            title = QGraphicsSimpleTextItem(f"{commit.hash[:10]} • {commit.author}", card)
            title.setBrush(QColor("#E6ECFF"))
            title.setPos(x + 10, y + 8)

            message = commit.message.replace("\n", " ").strip()
            if len(message) > 62:
                message = f"{message[:59]}..."
            subtitle = QGraphicsSimpleTextItem(message or "(без сообщения)", card)
            subtitle.setBrush(QColor("#9AA7C7"))
            subtitle.setPos(x + 10, y + 32)

            self._cards[commit.hash] = card

        bounds = self.scene.itemsBoundingRect()
        self.scene.setSceneRect(bounds.adjusted(-20, -20, 20, 20))

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        item = self.itemAt(event.pos())
        while item is not None and not isinstance(item, QGraphicsRectItem):
            item = item.parentItem()
        if isinstance(item, QGraphicsRectItem):
            commit_hash = item.data(0)
            if commit_hash:
                self.select_commit(str(commit_hash), emit_signal=True)
        super().mousePressEvent(event)

    def select_commit(self, commit_hash: str, emit_signal: bool = False) -> None:
        if self._selected_hash == commit_hash:
            return

        if self._selected_hash and self._selected_hash in self._cards:
            old_card = self._cards[self._selected_hash]
            old_card.setBrush(QColor("#1A2438"))
            old_card.setPen(QPen(QColor("#26324A"), 1.4))

        self._selected_hash = commit_hash
        card = self._cards.get(commit_hash)
        if card:
            card.setBrush(QColor("#243452"))
            card.setPen(QPen(QColor("#5B8CFF"), 2.0))
            self.centerOn(card)

        if emit_signal:
            self.commit_clicked.emit(commit_hash)

    def _build_layout(self, commits: list[Commit]) -> dict[str, _NodeLayout]:
        layout: dict[str, _NodeLayout] = {}
        lanes: list[str] = []

        for row, commit in enumerate(commits):
            if commit.hash in lanes:
                lane_idx = lanes.index(commit.hash)
            else:
                lane_idx = len(lanes)
                lanes.append(commit.hash)

            layout[commit.hash] = _NodeLayout(lane=lane_idx, row=row)

            parents = list(commit.parents)
            if not parents:
                lanes.pop(lane_idx)
                continue

            lanes[lane_idx] = parents[0]
            for parent_hash in parents[1:]:
                if parent_hash in lanes:
                    continue
                lanes.insert(lane_idx + 1, parent_hash)

        return layout


class CommitsTab(QWidget):
    commit_selected = Signal(str)
    checkout_requested = Signal(str)
    ai_summary_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._selected_hash: str | None = None

        self.graph_view = _CommitGraphView()
        self.graph_view.commit_clicked.connect(self._select_commit_from_graph)

        self.commit_list = QListWidget()
        self.commit_list.itemClicked.connect(self._select_commit_from_list)

        self.checkout_btn = QPushButton("Checkout")
        self.checkout_btn.clicked.connect(self._emit_checkout)
        self.describe_btn = QPushButton("Описание (Ollama)")
        self.describe_btn.clicked.connect(self._emit_ai_summary)

        actions = QHBoxLayout()
        actions.addWidget(QLabel("Последние коммиты"))
        actions.addStretch()
        actions.addWidget(self.checkout_btn)
        actions.addWidget(self.describe_btn)

        self.summary_toggle = QToolButton()
        self.summary_toggle.setText("Скрыть описание")
        self.summary_toggle.setCheckable(True)
        self.summary_toggle.setChecked(True)
        self.summary_toggle.clicked.connect(self._toggle_summary)

        self.summary_view = QTextEdit()
        self.summary_view.setReadOnly(True)
        self.summary_view.setPlaceholderText("Выберите коммит и нажмите «Описание (Ollama)»")

        right_layout = QVBoxLayout()
        right_layout.addLayout(actions)
        right_layout.addWidget(self.commit_list)
        right_layout.addWidget(self.summary_toggle, alignment=Qt.AlignRight)
        right_layout.addWidget(self.summary_view)

        right_panel = QWidget()
        right_panel.setLayout(right_layout)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.graph_view)
        splitter.addWidget(right_panel)
        splitter.setSizes([860, 420])

        root = QVBoxLayout(self)
        root.addWidget(splitter)

    def set_commits(self, commits: list[Commit]) -> None:
        self._selected_hash = None
        self.commit_list.clear()
        self.graph_view.set_commits(commits)

        for commit in commits:
            date_text = commit.authored_at.astimezone().strftime("%Y-%m-%d %H:%M")
            line = f"{commit.hash[:10]} • {commit.author} • {date_text}\n{commit.message}"
            item = QListWidgetItem(line)
            item.setData(Qt.UserRole, commit.hash)
            self.commit_list.addItem(item)

        if commits:
            self._set_selected_hash(commits[0].hash)

    def set_commit_summary(self, commit_hash: str, summary: str, model_info: str) -> None:
        header = f"### {commit_hash[:10]}\nМодель: {model_info}\n\n"
        self.summary_view.setMarkdown(f"{header}{summary}")
        if not self.summary_toggle.isChecked():
            self.summary_toggle.click()

    def _set_selected_hash(self, commit_hash: str) -> None:
        self._selected_hash = commit_hash
        self.graph_view.select_commit(commit_hash)

        for idx in range(self.commit_list.count()):
            item = self.commit_list.item(idx)
            if item.data(Qt.UserRole) == commit_hash:
                self.commit_list.setCurrentItem(item)
                break

        self.commit_selected.emit(commit_hash)

    def _select_commit_from_list(self, item: QListWidgetItem) -> None:
        commit_hash = item.data(Qt.UserRole)
        if commit_hash:
            self._set_selected_hash(str(commit_hash))

    def _select_commit_from_graph(self, commit_hash: str) -> None:
        self._set_selected_hash(commit_hash)

    def _emit_checkout(self) -> None:
        if self._selected_hash:
            self.checkout_requested.emit(self._selected_hash)

    def _emit_ai_summary(self) -> None:
        if self._selected_hash:
            self.ai_summary_requested.emit(self._selected_hash)

    def _toggle_summary(self) -> None:
        visible = self.summary_toggle.isChecked()
        self.summary_view.setVisible(visible)
        self.summary_toggle.setText("Скрыть описание" if visible else "Показать описание")
