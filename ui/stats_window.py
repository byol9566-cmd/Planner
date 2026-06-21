from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QRect, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.stats_aggregator import aggregate_range
from core.streak import current_streak, longest_streak

# ── 색상 팔레트 (theme) ────────────────────────────────
from core import theme as _theme
BG = _theme.get("bg")
CARD_BG = _theme.get("card_bg")
TITLE_COLOR = _theme.get("title")
TIME_COLOR = _theme.get("time")
MUTED = _theme.get("muted")

KIND_ACCENT: dict[str, str] = {
    "wake":      "#FFD700",
    "workout":   "#FF6B35",
    "meal":      "#7CB518",
    "buffer":    "#555570",
    "deepwork":  "#4361EE",
    "reading":   "#9B5DE5",
    "theme":     "#3A86FF",
    "marketing": "#F72585",
    "wrap":      "#06D6A0",
    "winddown":  "#8338EC",
    "sleep":     "#023E8A",
    "light":     "#90E0EF",
    "event":     "#E63946",
}

KIND_LABEL: dict[str, str] = {
    "wake":      "기상",
    "workout":   "운동",
    "meal":      "식사",
    "buffer":    "버퍼",
    "deepwork":  "집중",
    "reading":   "독서",
    "theme":     "테마",
    "marketing": "마케팅",
    "wrap":      "마무리",
    "winddown":  "이완",
    "sleep":     "수면",
    "light":     "가벼운작업",
    "event":     "이벤트",
}

WEEKDAY_LABEL = ["월", "화", "수", "목", "금", "토", "일"]


def _fmt_min(minutes: int) -> str:
    """분 → 'Xh Ym' 형태 문자열."""
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def _base_font(size: int = 11, bold: bool = False) -> QFont:
    f = QFont("Malgun Gothic")
    f.setPointSize(size)
    f.setBold(bold)
    return f


# ── 카드 컨테이너 ─────────────────────────────────────────────────────────
class _Card(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background:{CARD_BG}; border-radius:8px;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(6)

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


def _label(text: str, size: int = 11, color: str = TITLE_COLOR,
           bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(_base_font(size, bold))
    lbl.setStyleSheet(f"color:{color}; background:transparent;")
    return lbl


# ── kind별 막대 차트 ──────────────────────────────────────────────────────
class KindBarChart(QWidget):
    """kind별 수평 막대 차트 (QPainter 직접 렌더링)."""

    ROW_H = 28
    LABEL_W = 70
    STAT_W = 160
    BAR_MAX_W = 260
    PAD_H = 10
    PAD_V = 8

    def __init__(self, by_kind: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # done_min 기준 내림차순 정렬
        self._rows: list[tuple[str, dict]] = sorted(
            by_kind.items(), key=lambda kv: kv[1]["done_min"], reverse=True
        )
        self.setMinimumHeight(self.PAD_V * 2 + len(self._rows) * self.ROW_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background:transparent;")

    def paintEvent(self, _event) -> None:  # noqa: N802
        if not self._rows:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        font = _base_font(10)
        p.setFont(font)

        # 전체 total_min 중 최댓값 (막대 스케일 기준)
        max_total = max((v["total_min"] for _, v in self._rows), default=1) or 1

        for i, (kind, stats) in enumerate(self._rows):
            y = self.PAD_V + i * self.ROW_H
            bar_y = y + 6
            bar_h = self.ROW_H - 12

            done_min = stats["done_min"]
            total_min = stats["total_min"]
            pct = (done_min / total_min * 100) if total_min else 0.0

            # 라벨
            p.setPen(QColor(TITLE_COLOR))
            lbl_rect = QRect(0, y, self.LABEL_W, self.ROW_H)
            p.drawText(lbl_rect, Qt.AlignVCenter | Qt.AlignLeft,
                       KIND_LABEL.get(kind, kind))

            # 배경 막대 (total)
            bg_w = int(total_min / max_total * self.BAR_MAX_W)
            bg_rect = QRect(self.LABEL_W + self.PAD_H, bar_y, bg_w, bar_h)
            p.fillRect(bg_rect, QColor(TIME_COLOR))

            # 전경 막대 (done)
            fg_w = int(done_min / max_total * self.BAR_MAX_W)
            if fg_w > 0:
                fg_rect = QRect(self.LABEL_W + self.PAD_H, bar_y, fg_w, bar_h)
                p.fillRect(fg_rect, QColor(KIND_ACCENT.get(kind, "#888888")))

            # 통계 텍스트
            p.setPen(QColor(MUTED))
            stat_x = self.LABEL_W + self.PAD_H + self.BAR_MAX_W + 8
            stat_text = (
                f"{_fmt_min(done_min)} / {_fmt_min(total_min)} "
                f"({pct:.0f}%)"
            )
            stat_rect = QRect(stat_x, y, self.STAT_W, self.ROW_H)
            p.drawText(stat_rect, Qt.AlignVCenter | Qt.AlignLeft, stat_text)

        p.end()


# ── 요일별 막대 차트 ──────────────────────────────────────────────────────
class WeekdayBarChart(QWidget):
    """월~일 7개 수직 막대 차트."""

    BAR_W = 36
    BAR_MAX_H = 80
    PAD = 12
    LABEL_H = 20

    def __init__(self, by_weekday: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = by_weekday  # {0..6: {"done_pct": float, "days": int}}
        total_w = 7 * (self.BAR_W + self.PAD) + self.PAD
        self.setFixedSize(total_w, self.BAR_MAX_H + self.LABEL_H * 2 + 20)
        self.setStyleSheet("background:transparent;")

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(_base_font(9))

        for wd in range(7):
            info = self._data.get(wd, {"done_pct": 0.0, "days": 0})
            pct = info["done_pct"]
            bar_h = int(pct / 100 * self.BAR_MAX_H)

            x = self.PAD + wd * (self.BAR_W + self.PAD)
            # 배경
            bg_rect = QRect(x, self.LABEL_H, self.BAR_W, self.BAR_MAX_H)
            p.fillRect(bg_rect, QColor(TIME_COLOR))
            # 전경
            if bar_h > 0:
                fg_rect = QRect(x, self.LABEL_H + self.BAR_MAX_H - bar_h,
                                self.BAR_W, bar_h)
                p.fillRect(fg_rect, QColor("#4361EE"))

            # 요일 라벨
            p.setPen(QColor(TITLE_COLOR))
            lbl_rect = QRect(x, self.LABEL_H + self.BAR_MAX_H + 4,
                             self.BAR_W, self.LABEL_H)
            p.drawText(lbl_rect, Qt.AlignCenter, WEEKDAY_LABEL[wd])

            # 달성률 텍스트
            p.setPen(QColor(MUTED))
            pct_rect = QRect(x, 0, self.BAR_W, self.LABEL_H)
            p.drawText(pct_rect, Qt.AlignCenter, f"{pct:.0f}%")

        p.end()


# ── 일별 트렌드 막대 ──────────────────────────────────────────────────────
class DailyTrendChart(QWidget):
    """날짜별 time_pct 미니 막대 차트."""

    date_clicked = Signal(date)

    BAR_MAX_H = 60
    LABEL_H = 16

    def __init__(self, daily: list[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._daily = daily
        n = max(len(daily), 1)
        self.setMinimumHeight(self.BAR_MAX_H + self.LABEL_H + 10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("background:transparent;")
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._daily or event.button() != Qt.LeftButton:
            return
        n = len(self._daily)
        w = self.width()
        if w <= 0:
            return
        idx = int(event.position().x() / w * n)
        if 0 <= idx < n:
            d = self._daily[idx].get("date")
            if isinstance(d, date):
                self.date_clicked.emit(d)

    def paintEvent(self, _event) -> None:  # noqa: N802
        if not self._daily:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(_base_font(8))

        n = len(self._daily)
        w = self.width()
        bar_w = max(int(w / n) - 2, 2)

        for i, entry in enumerate(self._daily):
            pct = entry["done_pct"]
            bar_h = int(pct / 100 * self.BAR_MAX_H)
            x = int(i * w / n)

            # 배경
            bg_rect = QRect(x, 0, bar_w, self.BAR_MAX_H)
            p.fillRect(bg_rect, QColor(TIME_COLOR))

            # 전경
            if bar_h > 0:
                color = "#06D6A0" if pct >= 70 else "#4361EE"
                fg_rect = QRect(x, self.BAR_MAX_H - bar_h, bar_w, bar_h)
                p.fillRect(fg_rect, QColor(color))

        p.end()


# ── 메인 StatsWindow ──────────────────────────────────────────────────────
class StatsWindow(QMainWindow):
    """통계 창 — 기간별 집계, 스트릭, kind/요일/일별 차트."""

    date_selected = Signal(date)

    def __init__(
        self,
        config_path: Path,
        overrides_dir: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config_path = config_path
        self._overrides_dir = overrides_dir
        self._period = "주간"  # 현재 선택된 기간

        self.setWindowTitle("통계")
        self.setMinimumWidth(680)
        self.setStyleSheet(f"QMainWindow {{ background:{BG}; }} "
                           f"QWidget {{ background:{BG}; color:{TITLE_COLOR}; }}")

        self._build_ui()

    # ── UI 구성 ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 12, 16, 12)
        root_layout.setSpacing(10)

        # 헤더
        header = self._make_header()
        root_layout.addWidget(header)

        # 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(f"background:{BG}; border:none;")
        root_layout.addWidget(scroll)

        self._scroll_content = QWidget()
        self._scroll_content.setStyleSheet(f"background:{BG};")
        self._content_layout = QVBoxLayout(self._scroll_content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(12)
        self._content_layout.addStretch()
        scroll.setWidget(self._scroll_content)

        # 스트릭 라벨 참조 보관
        self._streak_label: QLabel | None = None
        self._longest_label: QLabel | None = None

    def _make_header(self) -> QWidget:
        header = QWidget()
        header.setStyleSheet(f"background:{BG};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(8)

        # 타이틀
        title = _label("통계", 16, TITLE_COLOR, bold=True)
        h_layout.addWidget(title)

        # 기간 토글 버튼
        for period in ["주간", "월간", "최근 30일"]:
            btn = QPushButton(period)
            btn.setFont(_base_font(10))
            btn.setCheckable(True)
            btn.setChecked(period == self._period)
            btn.setFixedHeight(28)
            btn.setStyleSheet(self._btn_style(period == self._period))
            btn.clicked.connect(lambda checked, p=period, b=btn: self._on_period(p, b))
            h_layout.addWidget(btn)
            setattr(self, f"_btn_{period}", btn)

        h_layout.addStretch()

        # 스트릭 표시
        self._streak_label = _label("STREAK --일", 11, "#FFD700", bold=True)
        self._longest_label = _label("최장 --일", 10, MUTED)
        h_layout.addWidget(self._streak_label)
        h_layout.addWidget(self._longest_label)

        return header

    @staticmethod
    def _btn_style(active: bool) -> str:
        if active:
            return (
                "QPushButton { background:#4361EE; color:#FFFFFF; "
                "border-radius:6px; padding:0 10px; border:none; }"
            )
        return (
            "QPushButton { background:#16161E; color:#888899; "
            "border-radius:6px; padding:0 10px; border:none; }"
            "QPushButton:hover { background:#1E1E2E; }"
        )

    def _on_period(self, period: str, clicked_btn: QPushButton) -> None:
        self._period = period
        # 버튼 상태 업데이트
        for p in ["주간", "월간", "최근 30일"]:
            btn: QPushButton = getattr(self, f"_btn_{p}", None)
            if btn:
                active = (p == period)
                btn.setChecked(active)
                btn.setStyleSheet(self._btn_style(active))
        self._reload()

    # ── 기간 계산 ─────────────────────────────────────────────────────────
    def _date_range(self) -> tuple[date, date]:
        today = date.today()
        if self._period == "주간":
            # 이번 주 월요일~오늘
            start = today - timedelta(days=today.weekday())
            return start, today
        elif self._period == "월간":
            # 이번 달 1일~오늘
            return today.replace(day=1), today
        else:  # 최근 30일
            return today - timedelta(days=29), today

    # ── 데이터 로드 및 렌더링 ─────────────────────────────────────────────
    def _reload(self) -> None:
        today = date.today()
        start, end = self._date_range()

        # 스트릭 업데이트
        try:
            cs = current_streak(today, self._config_path, self._overrides_dir)
            ls = longest_streak(start, end, self._config_path, self._overrides_dir)
        except Exception:
            cs, ls = 0, 0

        if self._streak_label:
            self._streak_label.setText(f"STREAK {cs}일")
        if self._longest_label:
            self._longest_label.setText(f"최장 {ls}일")

        # 집계
        try:
            data = aggregate_range(start, end, self._config_path, self._overrides_dir)
        except Exception:
            return

        self._render_content(data)

    def _render_content(self, data: dict) -> None:
        # 기존 위젯 제거 (stretch 포함)
        layout = self._content_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        totals = data["totals"]
        by_kind = data["by_kind"]
        by_weekday = data["by_weekday"]
        daily = data["daily"]

        # ── 요약 카드 ──────────────────────────────────────────────────
        summary_card = _Card()
        total_min = totals["total_min"]
        done_min = totals["done_min"]
        total_pct = (done_min / total_min * 100) if total_min else 0.0

        summary_card.add(_label("요약", 12, TITLE_COLOR, bold=True))
        summary_card.add(_label(
            f"달성률 (시간 기준):  {total_pct:.1f}%",
            11, "#4361EE"
        ))
        summary_card.add(_label(
            f"블록:  {totals['done_count']} / {totals['total_count']}개",
            10, MUTED
        ))
        summary_card.add(_label(
            f"시간:  {_fmt_min(done_min)} / {_fmt_min(total_min)}",
            10, MUTED
        ))
        summary_card.add(_label(
            f"집계 일수:  {totals['days']}일",
            10, TIME_COLOR
        ))
        layout.addWidget(summary_card)

        # ── kind별 차트 ────────────────────────────────────────────────
        if by_kind:
            kind_card = _Card()
            kind_card.add(_label("종류별 달성", 12, TITLE_COLOR, bold=True))
            chart = KindBarChart(by_kind)
            kind_card.add(chart)
            layout.addWidget(kind_card)

        # ── 요일별 평균 달성률 ─────────────────────────────────────────
        wd_card = _Card()
        wd_card.add(_label("요일별 평균 달성률", 12, TITLE_COLOR, bold=True))
        wd_chart = WeekdayBarChart(by_weekday)
        wd_card.add(wd_chart)
        layout.addWidget(wd_card)

        # ── 일별 트렌드 ────────────────────────────────────────────────
        if daily:
            trend_card = _Card()
            trend_card.add(_label("일별 달성률 트렌드", 12, TITLE_COLOR, bold=True))
            trend_note = _label(
                "초록=70%이상, 파랑=70%미만",
                9, TIME_COLOR
            )
            trend_card.add(trend_note)
            trend_chart = DailyTrendChart(daily)
            trend_chart.date_clicked.connect(self.date_selected.emit)
            trend_card.add(trend_chart)
            layout.addWidget(trend_card)

        layout.addStretch()

    # ── 창이 보일 때 자동 리로드 ──────────────────────────────────────────
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._reload()
