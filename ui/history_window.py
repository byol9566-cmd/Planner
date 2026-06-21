from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from core.history import clear_history, load_history


class HistoryWindow(QMainWindow):
    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self._data_dir = data_dir
        self.setWindowTitle("알림 히스토리")
        self.setMinimumSize(380, 460)
        self.setStyleSheet("QMainWindow { background:#0D0D0F; }")
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QLabel("📜 알림 히스토리")
        header.setStyleSheet("color:#E0E0EE; background:transparent;")
        header.setFont(QFont("Malgun Gothic", 11, QFont.Weight.Bold))
        root.addWidget(header)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background:#16161E; color:#E0E0EE;"
            " border:1px solid #2A2A3A; border-radius:4px; padding:4px; }"
            "QListWidget::item { padding:4px; border-bottom:1px solid #1E1E28; }"
            "QListWidget::item:selected { background:#2A2A4E; color:#FFD700; }"
        )
        root.addWidget(self._list, stretch=1)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("새로고침")
        btn_clear = QPushButton("모두 지우기")
        for b in (btn_refresh, btn_clear):
            b.setStyleSheet(
                "QPushButton { background:#16161E; color:#E0E0EE;"
                "border:1px solid #444; border-radius:4px; padding:4px 12px; }"
                "QPushButton:hover { border:1px solid #FFD700; }"
            )
        btn_refresh.clicked.connect(self.refresh)
        btn_clear.clicked.connect(self._on_clear)
        btn_row.addStretch()
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_clear)
        root.addLayout(btn_row)

    def refresh(self) -> None:
        self._list.clear()
        records = load_history(self._data_dir, limit=300)
        if not records:
            item = QListWidgetItem("(기록 없음)")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(item)
            return
        for r in records:
            ts = r.get("ts", "")
            time = r.get("time", "")
            title = r.get("title", "")
            kind = r.get("kind", "")
            label = f"{ts}  [{time}] {title}  ·  {kind}"
            self._list.addItem(label)

    def _on_clear(self) -> None:
        ret = QMessageBox.question(
            self, "확인", "알림 히스토리를 모두 지울까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            clear_history(self._data_dir)
            self.refresh()
