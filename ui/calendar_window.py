from __future__ import annotations

import calendar
import json
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTime, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QAbstractItemView,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
    QMainWindow,
)

from core.config_loader import load_day, save_calendar_type, template_names
from core.completion import day_completion_ratio
from core.notion_sync import autosync_in_background

TYPE_COLORS: dict[str, str] = {
    "A":   "#4361EE",  # 휴가일 — 파랑
    "B":   "#F72585",  # 부대 금요일 — 핑크
    "C":   "#7209B7",  # 부대 주말 — 보라
    "D":   "#FF6B35",  # 외출일 — 오렌지
    "E":   "#06D6A0",  # 외박 — 민트
    "F":   "#ADB5BD",  # 부대 평일 — 회색
    "OFF": "#343A40",  # 휴식 — 검정
}
DEFAULT_COLOR = "#6C757D"


def _blend(hex_color: str, ratio: float) -> str:
    """Blend hex_color toward bright green based on ratio (0..1)."""
    base = hex_color.lstrip("#")
    r = int(base[0:2], 16)
    g = int(base[2:4], 16)
    b = int(base[4:6], 16)
    tr, tg, tb = 0x06, 0xD6, 0xA0  # mint green
    nr = int(r + (tr - r) * ratio)
    ng = int(g + (tg - g) * ratio)
    nb = int(b + (tb - b) * ratio)
    return f"#{nr:02X}{ng:02X}{nb:02X}"


class QuickEventDialog(QDialog):
    """임의 날짜에 일회성 이벤트를 빠르게 추가하는 다이얼로그."""

    KIND_OPTIONS = [
        "event", "wake", "workout", "meal", "buffer", "deepwork",
        "reading", "theme", "marketing", "wrap", "winddown", "sleep", "light",
    ]

    def __init__(self, d: date, parent=None):
        super().__init__(parent)
        self._date = d
        self.setWindowTitle(f"이벤트 추가 — {d.isoformat()}")
        self.setModal(True)
        self.setMinimumWidth(320)
        self.setStyleSheet(
            "QDialog { background:#0D0D0F; color:#E0E0EE; }"
            "QLabel { color:#E0E0EE; }"
            "QTimeEdit, QLineEdit, QComboBox {"
            "  background:#16161E; color:#E0E0EE;"
            "  border:1px solid #333; border-radius:4px; padding:3px 6px;"
            "}"
            "QPushButton {"
            "  background:#16161E; color:#E0E0EE;"
            "  border:1px solid #444; border-radius:4px; padding:4px 12px;"
            "}"
            "QPushButton:hover { border:1px solid #FFD700; }"
        )
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(8)

        # 시간 — 현재 시각에서 다음 정각
        now = datetime.now()
        next_hour = now.replace(minute=0, second=0, microsecond=0)
        if now.minute > 0 or now.second > 0:
            next_hour = next_hour.replace(hour=(now.hour + 1) % 24)
        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setTime(QTime(next_hour.hour, 0))
        self._time_edit.setMinimumTime(QTime(0, 0))
        self._time_edit.setMaximumTime(QTime(23, 59))
        form.addRow("시간", self._time_edit)

        # 제목
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("이벤트 제목")
        form.addRow("제목", self._title_edit)

        # kind
        self._kind_combo = QComboBox()
        self._kind_combo.addItems(self.KIND_OPTIONS)
        self._kind_combo.setCurrentText("event")
        form.addRow("종류", self._kind_combo)

        layout.addLayout(form)

        # 버튼
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("확인")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def time_str(self) -> str:
        return self._time_edit.time().toString("HH:mm")

    def title(self) -> str:
        return self._title_edit.text().strip()

    def kind(self) -> str:
        return self._kind_combo.currentText()


class DeleteEventDialog(QDialog):
    """선택된 날짜의 이벤트를 삭제하는 다이얼로그."""

    def __init__(self, d: date, events: list, parent=None):
        super().__init__(parent)
        self._date = d
        self._events = events
        self.setWindowTitle(f"이벤트 삭제 — {d.isoformat()}")
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setStyleSheet(
            "QDialog { background:#0D0D0F; color:#E0E0EE; }"
            "QLabel { color:#E0E0EE; }"
            "QListWidget {"
            "  background:#16161E; color:#E0E0EE;"
            "  border:1px solid #333; border-radius:4px; padding:3px 6px;"
            "}"
            "QListWidget::item:selected { background:#2A2A4E; color:#FFD700; }"
            "QPushButton {"
            "  background:#16161E; color:#E0E0EE;"
            "  border:1px solid #444; border-radius:4px; padding:4px 12px;"
            "}"
            "QPushButton:hover { border:1px solid #FFD700; }"
        )
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lbl = QLabel(f"{self._date.isoformat()} 이벤트 목록 (다중 선택 가능):")
        layout.addWidget(lbl)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self._list.setMinimumHeight(120)
        for ev in self._events:
            label = f"{ev.get('time', '')}  {ev.get('title', '')}  [{ev.get('kind', 'event')}]"
            self._list.addItem(label)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_delete = QPushButton("삭제")
        btn_delete.setStyleSheet(
            "QPushButton { background:#3A1010; color:#FF6B6B; border:1px solid #5A2020; }"
            "QPushButton:hover { border:1px solid #FFD700; }"
        )
        btn_cancel = QPushButton("취소")
        btn_delete.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_delete)
        layout.addLayout(btn_row)

    def selected_indices(self) -> list[int]:
        return [self._list.row(item) for item in self._list.selectedItems()]


class DayCell(QPushButton):
    type_changed = Signal(date, str)
    edit_requested = Signal(date)
    view_requested = Signal(date)
    event_add_requested = Signal(date)
    event_delete_requested = Signal(date)

    def __init__(self, d: date, type_code: str, type_names: dict[str, str],
                 stats: dict | None = None, is_today: bool = False,
                 has_events: bool = False):
        super().__init__()
        self._date = d
        self._type_code = type_code
        self._type_names = type_names
        self._stats = stats
        self._has_events = has_events
        self.setMinimumSize(52, 64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._refresh(is_today)
        self.clicked.connect(self._on_click)

    def _refresh(self, is_today: bool = False) -> None:
        base_color = TYPE_COLORS.get(self._type_code, DEFAULT_COLOR)
        if self._stats and self._stats["total_blocks"]:
            ratio = self._stats["time_pct"] / 100.0
            color = _blend(base_color, ratio)
        else:
            color = base_color
        border = "3px solid #FFD700" if is_today else f"1px solid {base_color}"
        self.setStyleSheet(
            f"QPushButton {{ background:{color}; border:{border}; border-radius:6px;"
            f" color:white; font-size:10px; text-align:center; padding:2px; }}"
            f"QPushButton:hover {{ border:1px solid #FFD700; }}"
        )
        name = self._type_names.get(self._type_code, self._type_code)
        short = name[:3] if len(name) > 3 else name
        if self._stats and self._stats["total_blocks"]:
            ratio_txt = f"{self._stats['done_blocks']}/{self._stats['total_blocks']}"
            pct_txt = f"{self._stats['time_pct']:.0f}%"
            self.setText(
                f"{self._date.day}  [{self._type_code}]\n{short}\n{ratio_txt} · {pct_txt}"
            )
        else:
            self.setText(f"{self._date.day}\n{self._type_code}\n{short}")

    def set_type(self, code: str) -> None:
        self._type_code = code
        self._refresh(self._date == date.today())

    def _on_click(self) -> None:
        menu = QMenu(self)
        type_menu = menu.addMenu("타입 변경")
        for code, name in self._type_names.items():
            action = type_menu.addAction(f"[{code}] {name}")
            action.setData(("type", code))
        menu.addSeparator()
        view_action = menu.addAction("이 날짜 타임라인 보기")
        view_action.setData(("view", None))
        edit_action = menu.addAction("이 날짜 블록 편집…")
        edit_action.setData(("edit", None))
        menu.addSeparator()
        add_event_action = menu.addAction("⚡ 이벤트 추가…")
        add_event_action.setData(("add_event", None))
        if self._has_events:
            del_event_action = menu.addAction("🗑 이벤트 삭제…")
            del_event_action.setData(("del_event", None))
        chosen = menu.exec(self.mapToGlobal(self.rect().bottomLeft()))
        if not chosen:
            return
        kind, value = chosen.data()
        if kind == "type":
            self.set_type(value)
            self.type_changed.emit(self._date, value)
        elif kind == "view":
            self.view_requested.emit(self._date)
        elif kind == "edit":
            self.edit_requested.emit(self._date)
        elif kind == "add_event":
            self.event_add_requested.emit(self._date)
        elif kind == "del_event":
            self.event_delete_requested.emit(self._date)


class MonthView(QWidget):
    day_view_requested = Signal(date)
    schedule_changed = Signal()

    def __init__(self, year: int, month: int, config_path: Path,
                 overrides_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self._config_path = config_path
        self._overrides_dir = overrides_dir
        self._type_names = template_names(config_path)
        self._cells: dict[date, DayCell] = {}
        self._year = year
        self._month = month
        self._build(year, month)

    def _build(self, year: int, month: int) -> None:
        if self.layout():
            # clear old layout
            while self.layout().count():
                item = self.layout().takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        else:
            grid = QGridLayout(self)
            grid.setSpacing(3)

        grid = self.layout()

        day_names = ["월", "화", "수", "목", "금", "토", "일"]
        for col, dn in enumerate(day_names):
            lbl = QLabel(dn)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color:#888; font-size:11px;")
            grid.addWidget(lbl, 0, col)

        with open(self._config_path, encoding="utf-8") as f:
            raw = json.load(f)
        cal_data = raw.get("calendar", {})

        today = date.today()
        cal = calendar.Calendar(firstweekday=0)  # Monday first
        week_row = 1
        for week in cal.monthdatescalendar(year, month):
            for col, d in enumerate(week):
                entry = cal_data.get(d.isoformat(), {})
                type_code = entry.get("type", "A")
                has_events = bool(entry.get("events"))
                stats = None
                if self._overrides_dir and d.month == month:
                    stats = day_completion_ratio(d, self._config_path, self._overrides_dir)
                cell = DayCell(d, type_code, self._type_names,
                               stats=stats, is_today=(d == today),
                               has_events=has_events)
                if d.month != month:
                    cell.setEnabled(False)
                    cell.setStyleSheet("background:#1A1A1A; border:1px solid #333; color:#555; border-radius:6px; font-size:11px;")
                else:
                    cell.type_changed.connect(self._on_type_changed)
                    cell.edit_requested.connect(self._on_edit_requested)
                    cell.view_requested.connect(self._on_view_requested)
                    cell.event_add_requested.connect(self._on_event_add_requested)
                    cell.event_delete_requested.connect(self._on_event_delete_requested)
                    self._cells[d] = cell
                grid.addWidget(cell, week_row, col)
            week_row += 1

    def _on_type_changed(self, d: date, code: str) -> None:
        save_calendar_type(d, code, self._config_path)
        if d in self._cells and self._overrides_dir:
            from core.completion import day_completion_ratio
            stats = day_completion_ratio(d, self._config_path, self._overrides_dir)
            self._cells[d]._stats = stats
            self._cells[d]._type_code = code
            self._cells[d]._refresh(d == date.today())
        autosync_in_background(self._config_path, self._overrides_dir, d)

    def _on_edit_requested(self, d: date) -> None:
        if not self._overrides_dir:
            return
        from ui.block_editor import BlockEditorDialog
        from core.config_loader import load_day, save_override
        sched = load_day(d, self._config_path, self._overrides_dir)
        dlg = BlockEditorDialog(
            list(sched.blocks),
            f"블록 편집 — {d.isoformat()}",
            lambda blocks: save_override(d, blocks, self._overrides_dir),
            parent=self,
        )
        if dlg.exec():
            self.reload()
            autosync_in_background(self._config_path, self._overrides_dir, d)

    def _on_view_requested(self, d: date) -> None:
        self.day_view_requested.emit(d)

    def _on_event_add_requested(self, d: date) -> None:
        dlg = QuickEventDialog(d, parent=self)
        if dlg.exec():
            title = dlg.title()
            if not title:
                return
            self._save_event(d, dlg.time_str(), title, dlg.kind())

    def _on_event_delete_requested(self, d: date) -> None:
        with open(self._config_path, encoding="utf-8") as f:
            raw = json.load(f)
        cal = raw.get("calendar", {})
        entry = cal.get(d.isoformat(), {})
        events = entry.get("events", [])
        if not events:
            return
        dlg = DeleteEventDialog(d, events, parent=self)
        if dlg.exec():
            indices = set(dlg.selected_indices())
            if not indices:
                return
            entry["events"] = [ev for i, ev in enumerate(events) if i not in indices]
            if not entry["events"]:
                entry.pop("events", None)
            cal[d.isoformat()] = entry
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
            self.reload()
            self.schedule_changed.emit()
            autosync_in_background(self._config_path, self._overrides_dir, d)

    def _save_event(self, d: date, time_str: str, title: str, kind: str) -> None:
        with open(self._config_path, encoding="utf-8") as f:
            raw = json.load(f)
        cal = raw.setdefault("calendar", {})
        entry = cal.setdefault(d.isoformat(), {})
        entry.setdefault("events", []).append({"time": time_str, "title": title, "kind": kind})
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        self.reload()
        self.schedule_changed.emit()
        autosync_in_background(self._config_path, self._overrides_dir, d)

    def reload(self) -> None:
        self._cells.clear()
        self._build(self._year, self._month)


class CalendarWindow(QMainWindow):
    schedule_changed = Signal()
    day_view_requested = Signal(date)

    def __init__(self, config_path: Path, overrides_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self._config_path = config_path
        self._overrides_dir = overrides_dir
        today = date.today()
        self._year = today.year
        self._month = today.month
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("월간 캘린더 편집")
        self.setMinimumSize(420, 360)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        # header nav
        nav = QHBoxLayout()
        prev_btn = QPushButton("◀")
        prev_btn.setFixedWidth(32)
        prev_btn.clicked.connect(self._prev_month)
        nav.addWidget(prev_btn)

        self._month_lbl = QLabel()
        self._month_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._month_lbl.setFont(QFont("Malgun Gothic", 13, QFont.Weight.Bold))
        nav.addWidget(self._month_lbl, stretch=1)

        next_btn = QPushButton("▶")
        next_btn.setFixedWidth(32)
        next_btn.clicked.connect(self._next_month)
        nav.addWidget(next_btn)
        root.addLayout(nav)

        # legend
        legend = QHBoxLayout()
        type_names = template_names(self._config_path)
        for code, name in list(type_names.items())[:4]:
            color = TYPE_COLORS.get(code, DEFAULT_COLOR)
            chip = QLabel(f"[{code}] {name[:5]}")
            chip.setStyleSheet(f"background:{color}; color:white; padding:2px 6px; border-radius:4px; font-size:10px;")
            legend.addWidget(chip)
        legend.addStretch()
        root.addLayout(legend)

        legend2 = QHBoxLayout()
        for code, name in list(type_names.items())[4:]:
            color = TYPE_COLORS.get(code, DEFAULT_COLOR)
            chip = QLabel(f"[{code}] {name[:5]}")
            chip.setStyleSheet(f"background:{color}; color:white; padding:2px 6px; border-radius:4px; font-size:10px;")
            legend2.addWidget(chip)
        legend2.addStretch()
        root.addLayout(legend2)

        self._month_view = MonthView(self._year, self._month, self._config_path,
                                     overrides_dir=self._overrides_dir)
        self._month_view.day_view_requested.connect(self.day_view_requested.emit)
        self._month_view.schedule_changed.connect(self.schedule_changed.emit)
        root.addWidget(self._month_view, stretch=1)

        self._update_label()

    def _update_label(self) -> None:
        self._month_lbl.setText(f"{self._year}년 {self._month}월")

    def _prev_month(self) -> None:
        if self._month == 1:
            self._year -= 1
            self._month = 12
        else:
            self._month -= 1
        self._refresh()

    def _next_month(self) -> None:
        if self._month == 12:
            self._year += 1
            self._month = 1
        else:
            self._month += 1
        self._refresh()

    def _refresh(self) -> None:
        self._update_label()
        self._month_view._year = self._year
        self._month_view._month = self._month
        self._month_view.reload()
        self.schedule_changed.emit()

    def refresh(self) -> None:
        """Reload current month — call after external changes (e.g. timeline toggle)."""
        self._month_view.reload()

    def showEvent(self, event):
        self._month_view.reload()
        super().showEvent(event)
