#!/usr/bin/env python
"""GUI entrypoint for Schedule Notifier."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
OVERRIDES_DIR = BASE_DIR / "overrides"


def main() -> None:
    from PySide6.QtWidgets import QApplication

    # 테마 먼저 로드 — UI 모듈이 import 시점에 색상을 캐싱하므로 그 전에 적용
    from core import theme
    theme.load_from_config(CONFIG_PATH)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 전역 QSS — 라이트/다크 공통 fallback
    p = theme.palette()
    app.setStyleSheet(
        f"QMainWindow, QDialog, QWidget {{ background:{p['bg']}; color:{p['title']}; }}"
        f"QMenu {{ background:{p['card_bg']}; color:{p['title']}; border:1px solid {p['line']}; }}"
        f"QMenu::item:selected {{ background:{p['card_hover']}; }}"
        f"QScrollArea {{ background:{p['bg']}; }}"
    )

    from core.config_loader import load_day
    from core.scheduler import ScheduleEngine
    from ui.timeline_window import TimelineWindow
    from ui.tray import TrayIcon
    from ui.calendar_window import CalendarWindow

    sched = load_day(date.today(), CONFIG_PATH, OVERRIDES_DIR)

    engine = ScheduleEngine(CONFIG_PATH, OVERRIDES_DIR)
    engine.start()

    cal_window = CalendarWindow(CONFIG_PATH, overrides_dir=OVERRIDES_DIR)

    window = TimelineWindow(sched, engine=engine, config_path=CONFIG_PATH,
                            overrides_dir=OVERRIDES_DIR, calendar_window=cal_window)
    window.show()

    def _on_calendar_changed():
        engine.reload_today()
        if engine.today:
            window.update_schedule(engine.today)

    cal_window.schedule_changed.connect(_on_calendar_changed)

    def _on_day_view_requested(target_day: date) -> None:
        target_sched = load_day(target_day, CONFIG_PATH, OVERRIDES_DIR)
        window.update_schedule(target_sched)
        window.show()
        window.raise_()
        window.activateWindow()

    cal_window.day_view_requested.connect(_on_day_view_requested)

    tray = TrayIcon(window, engine=engine, calendar_window=cal_window,
                    config_path=CONFIG_PATH, overrides_dir=OVERRIDES_DIR)
    tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
