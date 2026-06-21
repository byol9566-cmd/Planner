from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QDialog, QListWidget, QListWidgetItem, QVBoxLayout, QLineEdit, QLabel,
)

from core.config_loader import load_day

from core import theme as _theme
BG = _theme.get("bg")
CARD = _theme.get("card_bg")
TITLE = _theme.get("title")
ACCENT = "#FFD700"


class SearchDialog(QDialog):
    date_selected = Signal(date)

    def __init__(self, config_path: Path, overrides_dir: Path, parent=None):
        super().__init__(parent)
        self._config_path = config_path
        self._overrides_dir = overrides_dir
        self._today = date.today()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._run_search)

        self.setWindowTitle("일정 검색")
        self.resize(520, 400)
        self._apply_dark()
        self._build_ui()

    def _apply_dark(self):
        self.setStyleSheet(f"""
            QDialog {{ background: {BG}; color: {TITLE}; }}
            QLineEdit {{
                background: {CARD}; color: {TITLE};
                border: 1px solid #2A2A3A; border-radius: 4px;
                padding: 6px 8px; font-size: 14px;
            }}
            QListWidget {{
                background: {CARD}; color: {TITLE};
                border: 1px solid #2A2A3A; border-radius: 4px;
                font-size: 13px;
            }}
            QListWidget::item {{ padding: 5px 8px; border: 1px solid transparent; }}
            QListWidget::item:hover {{ border: 1px solid {ACCENT}; border-radius: 3px; }}
            QListWidget::item:selected {{ background: #1E1E2E; border: 1px solid {ACCENT}; }}
            QLabel {{ color: #888899; font-size: 12px; }}
        """)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("블록 제목으로 검색… (±60일)")
        self._input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._input)

        self._hint = QLabel("검색어를 입력하세요.")
        layout.addWidget(self._hint)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_item_activated)
        self._list.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self._list)

    def _on_text_changed(self, text: str):
        self._debounce.stop()
        if not text.strip():
            self._list.clear()
            self._hint.setText("검색어를 입력하세요.")
            return
        self._debounce.start()

    def _run_search(self):
        query = self._input.text().strip()
        if not query:
            return

        results: list[tuple[int, date, str]] = []  # (abs_diff, date_, display)
        today = self._today

        for delta in range(-60, 61):
            d = today + timedelta(days=delta)
            try:
                day = load_day(d, self._config_path, self._overrides_dir)
            except Exception:
                continue

            items = list(day.blocks) + list(day.events)
            for item in items:
                title = getattr(item, "title", "")
                if query.lower() in title.lower():
                    time_str = getattr(item, "time", "")
                    kind = getattr(item, "kind", "")
                    display = f"{d.isoformat()}  {time_str}  {title}  [{kind}]"
                    results.append((abs(delta), d, display))

        results.sort(key=lambda x: x[0])

        self._list.clear()
        if results:
            self._hint.setText(f"결과 {len(results)}건")
            for _, d, display in results:
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, d)
                self._list.addItem(item)
        else:
            self._hint.setText("결과 없음")

    def _on_item_activated(self, item: QListWidgetItem):
        d: date = item.data(Qt.UserRole)
        if d is not None:
            self.date_selected.emit(d)
            self.accept()
