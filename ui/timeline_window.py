from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QPainterPath,
)
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QScrollArea, QSizePolicy, QTextEdit, QToolTip, QVBoxLayout, QWidget,
)

from core.config_loader import Block, DaySchedule, save_override
from core.completion import (
    block_key, compute_stats, load_completions, load_notes, get_note,
    set_note, toggle_completion,
)
from core.streak import current_streak


def _notion_autosync(config_path, overrides_dir, target_date):
    from core.notion_sync import autosync_in_background
    autosync_in_background(config_path, overrides_dir, target_date)

# ── palette ──────────────────────────────────────────────
from core import theme as _theme
BG          = QColor(_theme.get("bg"))
CARD_BG     = QColor(_theme.get("card_bg"))
CARD_HOVER  = QColor(_theme.get("card_hover"))
LINE_COLOR  = QColor(_theme.get("line"))
TIME_COLOR  = QColor(_theme.get("time"))
TITLE_COLOR = QColor(_theme.get("title"))
KIND_COLOR  = QColor(_theme.get("kind"))
DUR_COLOR   = QColor(_theme.get("dur"))
NOW_COLOR   = QColor(_theme.get("now"))
HEADER_BG   = QColor(_theme.get("header_bg"))

KIND_ACCENT: dict[str, QColor] = {
    "wake":      QColor("#FFD700"),
    "workout":   QColor("#FF6B35"),
    "meal":      QColor("#7CB518"),
    "buffer":    QColor("#555570"),
    "deepwork":  QColor("#4361EE"),
    "reading":   QColor("#9B5DE5"),
    "theme":     QColor("#3A86FF"),
    "marketing": QColor("#F72585"),
    "wrap":      QColor("#06D6A0"),
    "winddown":  QColor("#8338EC"),
    "sleep":     QColor("#023E8A"),
    "light":     QColor("#90E0EF"),
    "event":     QColor("#E63946"),
}
DEFAULT_ACCENT = QColor("#444466")

HOUR_PX  = 90   # pixels per hour  (30min=45px, 1h=90px)
LEFT_W   = 48   # time axis width
CARD_PAD = 6    # px between card and edges
RADIUS   = 6


def _mins(t: str) -> int:
    if t == "24:00":
        return 24 * 60
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _fmt_dur(minutes: int) -> str:
    if minutes <= 0:
        return ""
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


CHECK_SIZE = 18
CHECK_PAD = 8

DONE_TITLE_COLOR = QColor(_theme.get("done_title"))
DONE_CARD_BG     = QColor(_theme.get("done_card_bg"))
CHECK_BORDER     = QColor(_theme.get("check_border"))
CHECK_DONE_BG    = QColor("#06D6A0")
CHECK_DONE_FG    = QColor(_theme.get("bg"))


class TimelineCanvas(QWidget):
    completion_toggled = None  # set by parent

    def __init__(self, sched: DaySchedule, completions: set[str] | None = None, parent=None):
        super().__init__(parent)
        self._sched = sched
        self._completions = completions or set()
        self.setMinimumWidth(260)
        self.setMinimumHeight(24 * HOUR_PX + 40)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self._block_rects: list[tuple[QRectF, Block, int]] = []  # (rect, block, dur_min)
        self._check_rects: list[tuple[QRectF, Block]] = []
        self._on_toggle = None  # callback(block_key)
        self._notes: dict[str, str] = {}
        self._memo_callback = None  # callback(block)

    def set_block_moved_callback(self, cb) -> None:
        self._on_block_moved = cb

    # ── drag state ───────────────────────────────────────
    _drag_block = None
    _drag_press_y: float = 0.0
    _drag_orig_min: int = 0
    _drag_offset_min: int = 0

    def set_toggle_callback(self, cb) -> None:
        self._on_toggle = cb

    def set_completions(self, completions: set[str]) -> None:
        self._completions = completions
        self.update()

    def set_notes(self, notes: dict[str, str]) -> None:
        self._notes = notes
        self.update()

    def set_memo_callback(self, cb) -> None:
        self._memo_callback = cb

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position() if hasattr(event, 'position') else event.localPos()
        for rect, block in self._check_rects:
            if rect.contains(pos):
                if self._on_toggle:
                    self._on_toggle(block)
                return
        for rect, block, _dur in self._block_rects:
            if rect.contains(pos):
                self._drag_block = block
                self._drag_press_y = pos.y()
                self._drag_orig_min = _mins(block.time)
                self._drag_offset_min = 0
                all_b = self._blocks_sorted()
                try:
                    idx = all_b.index(block)
                except ValueError:
                    idx = -1
                prev_b = all_b[idx - 1] if idx > 0 else None
                next_b = all_b[idx + 1] if 0 <= idx < len(all_b) - 1 else None
                # 인접 블록 시작 위치는 넘지 못함 (최소 5분 간격 확보)
                lo = (_mins(prev_b.time) + 5) if prev_b else 0
                hi = (_mins(next_b.time) - 5) if next_b else (24 * 60 - 5)
                self._drag_min_offset = lo - self._drag_orig_min
                self._drag_max_offset = hi - self._drag_orig_min
                return

    def mouseMoveEvent(self, event):
        if self._drag_block is not None:
            pos = event.position() if hasattr(event, 'position') else event.localPos()
            delta_px = pos.y() - self._drag_press_y
            delta_min = int(round(delta_px / HOUR_PX * 60 / 5)) * 5
            lo = getattr(self, "_drag_min_offset", -24 * 60)
            hi = getattr(self, "_drag_max_offset", 24 * 60)
            delta_min = max(lo, min(hi, delta_min))
            if delta_min != self._drag_offset_min:
                self._drag_offset_min = delta_min
                self.update()
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            return
        # default tooltip behavior
        pos = event.position() if hasattr(event, 'position') else event.localPos()
        for rect, block in self._check_rects:
            if rect.contains(pos):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                QToolTip.showText(event.globalPosition().toPoint(), "완료 토글", self)
                return
        for rect, block, dur_min in self._block_rects:
            if rect.contains(pos):
                self.setCursor(Qt.CursorShape.ArrowCursor)
                tip = f"{block.time}  {block.title}\n{block.kind}  ·  {_fmt_dur(dur_min)}  ·  드래그로 시간 조정"
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        self.setCursor(Qt.CursorShape.ArrowCursor)
        QToolTip.hideText()

    def mouseReleaseEvent(self, event):
        if self._drag_block is None:
            return
        block = self._drag_block
        offset = self._drag_offset_min
        self._drag_block = None
        self._drag_offset_min = 0
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if abs(offset) < 5:
            self.update()
            return
        new_min = max(0, min(self._drag_orig_min + offset, 23 * 60 + 55))
        new_time = f"{new_min // 60:02d}:{new_min % 60:02d}"
        if new_time == block.time:
            self.update()
            return
        cb = getattr(self, "_on_block_moved", None)
        if cb:
            cb(block, new_time)
        self.update()

    def contextMenuEvent(self, event) -> None:
        pos = event.pos()
        hit_block = None
        for rect, block, _dur in self._block_rects:
            if rect.contains(QPointF(pos)):
                hit_block = block
                break
        if hit_block is None:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#16161E; color:#E0E0EE; border:1px solid #2A2A3E; }"
            "QMenu::item:selected { background:#2A2A4E; }"
        )
        act = menu.addAction("메모 편집…")
        chosen = menu.exec(event.globalPos())
        if chosen == act and self._memo_callback:
            self._memo_callback(hit_block)

    def _blocks_sorted(self) -> list[Block]:
        return sorted(
            self._sched.blocks + self._sched.events,
            key=lambda b: _mins(b.time),
        )

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w = self.width()

        # background
        p.fillRect(self.rect(), BG)

        # hour grid lines + labels
        font_time = QFont("Segoe UI", 8)
        p.setFont(font_time)
        for hour in range(25):
            y = hour * HOUR_PX
            p.setPen(QPen(LINE_COLOR, 1))
            p.drawLine(LEFT_W, y, w, y)
            p.setPen(QPen(TIME_COLOR, 1))
            p.drawText(0, y - 7, LEFT_W - 6, 14,
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{hour:02d}:00")

        # blocks (proportional — top always matches time axis)
        blocks = self._blocks_sorted()
        self._block_rects = []
        self._check_rects = []
        x  = LEFT_W + CARD_PAD
        cw = w - LEFT_W - CARD_PAD * 2
        for i, block in enumerate(blocks):
            start_min = _mins(block.time)
            if i + 1 < len(blocks):
                end_min = _mins(blocks[i + 1].time)
            elif block.end_time:
                end_min = _mins(block.end_time)
            else:
                end_min = min(start_min + 60, 24 * 60)
            dur_min = max(end_min - start_min, 1)
            if block is self._drag_block and self._drag_offset_min:
                start_min = max(0, min(start_min + self._drag_offset_min, 24 * 60 - 1))
            top    = start_min * HOUR_PX // 60
            draw_h = max(dur_min * HOUR_PX // 60, 2)
            if block is self._drag_block and self._drag_offset_min:
                p.setOpacity(0.75)
            else:
                p.setOpacity(1.0)

            accent = KIND_ACCENT.get(block.kind, DEFAULT_ACCENT)
            is_done = block_key(block) in self._completions
            cr = QRectF(x, top + 1, cw, draw_h - 2)
            self._block_rects.append((cr, block, dur_min))

            path = QPainterPath()
            path.addRoundedRect(cr, RADIUS, RADIUS)
            p.fillPath(path, QBrush(DONE_CARD_BG if is_done else CARD_BG))

            bar_path = QPainterPath()
            bar_color = accent.darker(180) if is_done else accent
            bar_path.addRoundedRect(QRectF(x, top + 1, 4, draw_h - 2), 2, 2)
            p.fillPath(bar_path, QBrush(bar_color))

            # memo dot indicator (●) if note exists
            has_note = block_key(block) in self._notes
            if has_note:
                dot_r = 4.0
                check_x_left = x + cw - CHECK_SIZE - CHECK_PAD
                dot_cx = check_x_left - dot_r - 5
                dot_cy = top + max((draw_h - CHECK_SIZE) / 2, 2) + CHECK_SIZE / 2
                p.setBrush(QBrush(QColor("#FFD700")))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(dot_cx, dot_cy), dot_r, dot_r)

            # checkbox at right edge (always rendered, even on thin cards)
            check_y = top + max((draw_h - CHECK_SIZE) / 2, 2)
            check_rect = QRectF(x + cw - CHECK_SIZE - CHECK_PAD, check_y, CHECK_SIZE, CHECK_SIZE)
            self._check_rects.append((check_rect, block))
            check_path = QPainterPath()
            check_path.addRoundedRect(check_rect, 4, 4)
            if is_done:
                p.fillPath(check_path, QBrush(CHECK_DONE_BG))
                p.setPen(QPen(CHECK_DONE_FG, 2))
                cx, cy = check_rect.center().x(), check_rect.center().y()
                p.drawLine(int(cx - 4), int(cy), int(cx - 1), int(cy + 3))
                p.drawLine(int(cx - 1), int(cy + 3), int(cx + 5), int(cy - 3))
            else:
                p.setPen(QPen(CHECK_BORDER, 1.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(check_path)

            if draw_h < 20:
                continue  # too thin — tooltip only

            # time
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            p.setPen(QPen(accent.lighter(160), 1))
            p.drawText(QRectF(x + 10, top + 4, cw - 14, 16),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       block.time)

            title_color = DONE_TITLE_COLOR if is_done else TITLE_COLOR
            title_right_pad = CHECK_SIZE + CHECK_PAD * 2 + 4

            if draw_h < 36:
                # single-line compact
                font = QFont("Malgun Gothic", 9, QFont.Weight.Bold)
                font.setStrikeOut(is_done)
                p.setFont(font)
                p.setPen(QPen(title_color, 1))
                p.drawText(QRectF(x + 54, top + 4, cw - 58 - title_right_pad, 16),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           block.title)
                continue

            # title word-wrap
            title_h = draw_h - 24 - (18 if draw_h >= 56 else 2)
            font = QFont("Malgun Gothic", 9, QFont.Weight.Bold)
            font.setStrikeOut(is_done)
            p.setFont(font)
            p.setPen(QPen(title_color, 1))
            p.drawText(QRectF(x + 10, top + 22, cw - 14 - title_right_pad, max(title_h, 14)),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                       | Qt.TextFlag.TextWordWrap,
                       block.title)

            # duration
            if draw_h >= 56:
                p.setFont(QFont("Segoe UI", 8))
                p.setPen(QPen(DUR_COLOR, 1))
                p.drawText(QRectF(x + 4, top + draw_h - 18, cw - 10, 16),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                           _fmt_dur(dur_min))

        # current time indicator
        now = datetime.now()
        now_min = now.hour * 60 + now.minute
        now_y = now_min * HOUR_PX // 60

        # dot
        p.setBrush(QBrush(NOW_COLOR))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(LEFT_W + 2, now_y), 5, 5)

        # dashed line
        pen = QPen(NOW_COLOR, 1.5, Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 3])
        p.setPen(pen)
        p.drawLine(LEFT_W + 8, now_y, w - 50, now_y)

        # "현재" label
        font_now = QFont("Segoe UI", 8, QFont.Weight.Bold)
        p.setFont(font_now)
        p.setPen(QPen(NOW_COLOR, 1))
        p.drawText(w - 46, now_y - 7, 44, 14,
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   "현재")

        p.end()

    def update_schedule(self, sched: DaySchedule) -> None:
        self._sched = sched
        self.update()


class MemoDialog(QDialog):
    def __init__(self, block_title: str, initial_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"메모 — {block_title}")
        self.setMinimumSize(320, 200)
        self.setStyleSheet(
            "QDialog { background:#16161E; }"
            "QLabel { color:#E0E0EE; background:transparent; font-size:11px; }"
            "QTextEdit { background:#0D0D0F; color:#E0E0EE; border:1px solid #2A2A3E;"
            "border-radius:4px; font-size:12px; padding:4px; }"
            "QPushButton { border-radius:5px; font-size:11px; padding:4px 12px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl = QLabel(block_title)
        lbl.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        layout.addWidget(lbl)

        self._edit = QTextEdit()
        self._edit.setMinimumSize(200, 120)
        self._edit.setPlainText(initial_text)
        layout.addWidget(self._edit)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_ok = QPushButton("확인")
        btn_ok.setStyleSheet(
            "QPushButton { background:#1A3A2E; color:#7BD8B0; border:1px solid #2A5A4A; }"
            "QPushButton:hover { background:#1F4A3A; }"
        )
        btn_cancel = QPushButton("취소")
        btn_cancel.setStyleSheet(
            "QPushButton { background:#1E1E2A; color:#888899; border:1px solid #2A2A3E; }"
            "QPushButton:hover { background:#252535; }"
        )
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def text(self) -> str:
        return self._edit.toPlainText().strip()


class TimelineWindow(QMainWindow):
    def __init__(self, sched: DaySchedule, engine=None,
                 config_path: Path | None = None, overrides_dir: Path | None = None,
                 calendar_window=None):
        super().__init__()
        self._sched = sched
        self._engine = engine
        self._config_path = config_path
        self._overrides_dir = overrides_dir
        self._calendar_window = calendar_window
        self._completions: set[str] = (
            load_completions(sched.date, overrides_dir) if overrides_dir else set()
        )
        self._setup_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30_000)

    def _setup_ui(self) -> None:
        self.setWindowTitle(f"Schedule — {self._sched.date.isoformat()}")
        self.setMinimumSize(300, 560)
        self.resize(320, 780)

        # window-level dark bg
        self.setStyleSheet("QMainWindow { background:#0D0D0F; }")

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── header bar ──────────────────────────────────
        header_bar = QWidget()
        header_bar.setMinimumHeight(72)
        header_bar.setStyleSheet(f"background:{HEADER_BG.name()};")
        hbox = QHBoxLayout(header_bar)
        hbox.setContentsMargins(12, 0, 8, 0)

        header_col = QVBoxLayout()
        header_col.setContentsMargins(0, 0, 0, 0)
        header_col.setSpacing(2)
        self._header = QLabel()
        self._header.setStyleSheet("color:#E0E0EE; background:transparent;")
        self._header.setFont(QFont("Malgun Gothic", 10, QFont.Weight.Bold))
        header_col.addWidget(self._header)

        self._stats = QLabel()
        self._stats.setStyleSheet("color:#7CB518; background:transparent;")
        self._stats.setFont(QFont("Malgun Gothic", 8))
        header_col.addWidget(self._stats)

        self._streak_lbl = QLabel()
        self._streak_lbl.setStyleSheet("color:#FF6B35; background:transparent;")
        self._streak_lbl.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
        header_col.addWidget(self._streak_lbl)

        self._now_lbl = QLabel()
        self._now_lbl.setStyleSheet("color:#FFD700; background:transparent;")
        self._now_lbl.setFont(QFont("Malgun Gothic", 8, QFont.Weight.Bold))
        header_col.addWidget(self._now_lbl)

        self._next_lbl = QLabel()
        self._next_lbl.setStyleSheet("color:#888899; background:transparent;")
        self._next_lbl.setFont(QFont("Malgun Gothic", 8))
        header_col.addWidget(self._next_lbl)
        hbox.addLayout(header_col, stretch=1)

        cal_btn = QPushButton("캘린더")
        cal_btn.setFixedSize(54, 26)
        cal_btn.setStyleSheet(
            "QPushButton { background:#1A3A2E; color:#7BD8B0; border:1px solid #2A5A4A;"
            "border-radius:5px; font-size:11px; }"
            "QPushButton:hover { background:#1F4A3A; }"
        )
        cal_btn.clicked.connect(self._open_calendar)
        hbox.addWidget(cal_btn)

        edit_btn = QPushButton("편집")
        edit_btn.setFixedSize(44, 26)
        edit_btn.setStyleSheet(
            "QPushButton { background:#1E2A5E; color:#7BA4FF; border:1px solid #2A3A7E;"
            "border-radius:5px; font-size:11px; }"
            "QPushButton:hover { background:#253270; }"
        )
        edit_btn.clicked.connect(self._open_editor)
        hbox.addWidget(edit_btn)

        root.addWidget(header_bar)

        # thin accent line under header
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#1E1E2E;")
        root.addWidget(line)

        # ── scroll + canvas ──────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border:none; background:#0D0D0F; }"
            "QScrollBar:vertical { background:#0D0D0F; width:6px; }"
            "QScrollBar::handle:vertical { background:#2A2A3E; border-radius:3px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }"
        )
        self._canvas = TimelineCanvas(self._sched, self._completions)
        self._canvas.set_toggle_callback(self._on_toggle)
        self._canvas.set_memo_callback(self._on_memo_requested)
        self._canvas.set_block_moved_callback(self._on_block_moved)
        if self._overrides_dir:
            self._canvas.set_notes(load_notes(self._sched.date, self._overrides_dir))
        scroll.setWidget(self._canvas)
        root.addWidget(scroll)

        self._update_header()
        self._update_progress_header()

    def _update_progress_header(self) -> None:
        now = datetime.now()
        now_min = now.hour * 60 + now.minute
        blocks = sorted(self._sched.blocks + self._sched.events, key=lambda b: _mins(b.time))
        if not blocks:
            self._now_lbl.setText("일정 없음")
            self._next_lbl.setText("")
            return

        current = None
        cur_end = 0
        next_block = None
        for i, b in enumerate(blocks):
            start = _mins(b.time)
            if i + 1 < len(blocks):
                end = _mins(blocks[i + 1].time)
            elif b.end_time:
                end = _mins(b.end_time)
            else:
                end = min(start + 60, 24 * 60)
            if start <= now_min < end:
                current = b
                cur_end = end
                if i + 1 < len(blocks):
                    next_block = blocks[i + 1]
                break
        if current is None:
            upcoming = [b for b in blocks if _mins(b.time) > now_min]
            if upcoming:
                next_block = upcoming[0]
                self._now_lbl.setText("⏸ 휴식 중")
            else:
                self._now_lbl.setText("오늘 일정 종료")
                self._next_lbl.setText("")
                return
        else:
            elapsed = now_min - _mins(current.time)
            total = cur_end - _mins(current.time)
            self._now_lbl.setText(f"지금: {current.title}  •  {_fmt_dur(elapsed)} / {_fmt_dur(total)}")

        if next_block:
            mins_to = _mins(next_block.time) - now_min
            self._next_lbl.setText(f"다음: {next_block.time} {next_block.title} ({mins_to}분 후)")
        else:
            self._next_lbl.setText("다음 일정 없음")

    def _on_block_moved(self, old_block: Block, new_time: str) -> None:
        if not self._overrides_dir:
            return
        new_blocks = [
            dataclasses.replace(b, time=new_time) if b is old_block else b
            for b in self._sched.blocks
        ]
        save_override(self._sched.date, new_blocks, self._overrides_dir)
        if self._engine:
            self._engine.reload_today()
            if self._engine.today:
                self.update_schedule(self._engine.today)
        _notion_autosync(self._config_path, self._overrides_dir, self._sched.date)

    def _update_header(self) -> None:
        self._header.setText(
            f"{self._sched.date.isoformat()}  ·  {self._sched.type_name}"
        )
        stats = compute_stats(self._sched.blocks, self._completions)
        self._stats.setText(
            f"달성 {stats['done_blocks']}/{stats['total_blocks']}  "
            f"·  시간 {stats['time_pct']:.0f}%  ·  개수 {stats['count_pct']:.0f}%"
        )
        self.setWindowTitle(f"Schedule — {self._sched.date.isoformat()} [{self._sched.type_name}]")
        if self._config_path and self._overrides_dir:
            try:
                n = current_streak(date.today(), self._config_path, self._overrides_dir)
                self._streak_lbl.setText(f"🔥 {n}일 연속" if n > 0 else "")
            except Exception:
                self._streak_lbl.setText("")
        else:
            self._streak_lbl.setText("")

    def _on_toggle(self, block: Block) -> None:
        if not self._overrides_dir:
            return
        key = block_key(block)
        new_state = toggle_completion(self._sched.date, key, self._overrides_dir)
        if new_state:
            self._completions.add(key)
        else:
            self._completions.discard(key)
        self._canvas.set_completions(self._completions)
        self._update_header()
        if self._calendar_window:
            self._calendar_window.refresh()
        _notion_autosync(self._config_path, self._overrides_dir, self._sched.date)

    def _on_memo_requested(self, block: Block) -> None:
        if not self._overrides_dir:
            return
        key = block_key(block)
        current_note = get_note(self._sched.date, key, self._overrides_dir)
        dlg = MemoDialog(block.title, current_note, parent=self)
        if dlg.exec():
            set_note(self._sched.date, key, dlg.text(), self._overrides_dir)
            self._canvas.set_notes(load_notes(self._sched.date, self._overrides_dir))
            _notion_autosync(self._config_path, self._overrides_dir, self._sched.date)

    def set_calendar_window(self, cal_window) -> None:
        self._calendar_window = cal_window

    def _open_calendar(self) -> None:
        if not self._calendar_window:
            return
        self._calendar_window.show()
        self._calendar_window.raise_()
        self._calendar_window.activateWindow()

    def _open_editor(self) -> None:
        if not self._config_path or not self._overrides_dir:
            return
        from ui.block_editor import BlockEditorDialog
        from core.config_loader import save_override
        overrides_dir = self._overrides_dir
        target = self._sched.date

        dlg = BlockEditorDialog(
            list(self._sched.blocks),
            f"블록 편집 — {self._sched.date.isoformat()}",
            lambda blocks: save_override(target, blocks, overrides_dir),
            parent=self,
        )
        if dlg.exec() and self._engine:
            self._engine.reload_today()
            if self._engine.today:
                self.update_schedule(self._engine.today)

    def update_schedule(self, sched: DaySchedule) -> None:
        self._sched = sched
        if self._overrides_dir:
            self._completions = load_completions(sched.date, self._overrides_dir)
            self._canvas.set_completions(self._completions)
            self._canvas.set_notes(load_notes(sched.date, self._overrides_dir))
        self._canvas.update_schedule(sched)
        self._update_header()
        self._update_progress_header()

    def _tick(self) -> None:
        if self._overrides_dir:
            fresh = load_completions(self._sched.date, self._overrides_dir)
            if fresh != self._completions:
                self._completions = fresh
                self._canvas.set_completions(fresh)
                self._update_header()
        self._update_progress_header()
        self._canvas.update()
