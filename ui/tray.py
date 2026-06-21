from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtGui import QAction, QColor, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


def _make_icon(color: str = "#4361EE") -> QIcon:
    px = QPixmap(16, 16)
    px.fill(QColor(color))
    return QIcon(px)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, timeline_window, engine=None, calendar_window=None,
                 config_path=None, overrides_dir=None, parent=None):
        super().__init__(_make_icon(), parent)
        self._window = timeline_window
        self._engine = engine
        self._cal_window = calendar_window
        self._config_path = config_path
        self._overrides_dir = overrides_dir
        self._tmpl_window = None
        self._stats_window = None
        self._dnd_until: datetime | None = None
        self._settings_window = None
        self._history_window = None
        self._data_dir = (config_path.parent / "data") if config_path else None
        self.setToolTip("Schedule Notifier")
        self._build_menu()
        self.activated.connect(self._on_activate)

        if self._engine and self._engine._notifier:
            self._original_notify = self._engine._notifier.notify
            self._engine._notifier.notify = self._guarded_notify

    def _build_menu(self) -> None:
        menu = QMenu()

        show_action = QAction("타임라인 열기", menu)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)

        cal_action = QAction("캘린더 편집", menu)
        cal_action.triggered.connect(self._show_calendar)
        menu.addAction(cal_action)

        stats_action = QAction("통계 보기", menu)
        stats_action.triggered.connect(self._show_stats)
        menu.addAction(stats_action)

        history_action = QAction("📜 알림 히스토리", menu)
        history_action.triggered.connect(self._show_history)
        menu.addAction(history_action)

        search_action = QAction("🔍 검색…", menu)
        search_action.triggered.connect(self._show_search)
        menu.addAction(search_action)

        ical_action = QAction("📅 iCal 내보내기 (이번 달)", menu)
        ical_action.triggered.connect(self._export_ical)
        menu.addAction(ical_action)

        notion_today_action = QAction("☁ Notion 동기화 (오늘)", menu)
        notion_today_action.triggered.connect(lambda: self._notion_push_day(0))
        menu.addAction(notion_today_action)

        notion_week_action = QAction("☁ Notion 동기화 (이번 주)", menu)
        notion_week_action.triggered.connect(self._notion_push_week)
        menu.addAction(notion_week_action)

        menu.addSeparator()

        pause1h_action = QAction("⏸ 1시간 알림 일시정지", menu)
        pause1h_action.triggered.connect(lambda: self._pause_dnd_minutes(60))
        menu.addAction(pause1h_action)

        pause_today_action = QAction("⏸ 오늘 종일 일시정지", menu)
        pause_today_action.triggered.connect(self._pause_dnd_today)
        menu.addAction(pause_today_action)

        resume_action = QAction("▶ 알림 재개", menu)
        resume_action.triggered.connect(self._resume_dnd)
        menu.addAction(resume_action)

        menu.addSeparator()

        tmpl_action = QAction("기본 템플릿 편집", menu)
        tmpl_action.triggered.connect(self._show_template_editor)
        menu.addAction(tmpl_action)

        settings_action = QAction("⚙ 설정…", menu)
        settings_action.triggered.connect(self._show_settings)
        menu.addAction(settings_action)

        theme_action = QAction("🌓 테마 전환", menu)
        theme_action.triggered.connect(self._toggle_theme)
        menu.addAction(theme_action)

        menu.addSeparator()

        snooze10_action = QAction("다음 알림 10분 미루기", menu)
        snooze10_action.triggered.connect(lambda: self._snooze(10))
        menu.addAction(snooze10_action)

        snooze30_action = QAction("다음 알림 30분 미루기", menu)
        snooze30_action.triggered.connect(lambda: self._snooze(30))
        menu.addAction(snooze30_action)

        menu.addSeparator()

        reload_action = QAction("일정 새로고침", menu)
        reload_action.triggered.connect(self._reload)
        menu.addAction(reload_action)

        menu.addSeparator()

        backup_action = QAction("💾 백업 만들기", menu)
        backup_action.triggered.connect(self._create_backup)
        menu.addAction(backup_action)

        menu.addSeparator()

        quit_action = QAction("종료", menu)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def _on_activate(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _show_template_editor(self) -> None:
        if not self._config_path:
            return
        if self._tmpl_window is None:
            from ui.block_editor import TemplateEditorDialog
            self._tmpl_window = TemplateEditorDialog(self._config_path)
        self._tmpl_window.show()
        self._tmpl_window.raise_()
        self._tmpl_window.activateWindow()

    def _show_calendar(self) -> None:
        if self._cal_window:
            self._cal_window.show()
            self._cal_window.raise_()
            self._cal_window.activateWindow()

    def _show_stats(self) -> None:
        if not self._config_path or not self._overrides_dir:
            return
        if self._stats_window is None:
            from ui.stats_window import StatsWindow
            self._stats_window = StatsWindow(self._config_path, self._overrides_dir)
            self._stats_window.date_selected.connect(self._jump_to_date)
        self._stats_window.show()
        self._stats_window.raise_()
        self._stats_window.activateWindow()

    def _jump_to_date(self, d) -> None:
        if not self._config_path or not self._overrides_dir:
            return
        from core.config_loader import load_day
        sched = load_day(d, self._config_path, self._overrides_dir)
        self._window.update_schedule(sched)
        self._show_window()

    def _get_notion_sync(self):
        if not self._config_path or self._data_dir is None:
            return None
        from core.notion_sync import NotionConfig, NotionSync
        cfg = NotionConfig.from_settings(self._config_path)
        if cfg is None:
            self.showMessage(
                "Schedule Notifier",
                "Notion 설정이 비어있습니다. ⚙ 설정에서 토큰과 DB ID를 입력하세요.",
                QSystemTrayIcon.MessageIcon.Warning, 3500,
            )
            return None
        return NotionSync(cfg, self._data_dir)

    def _notion_push_day(self, day_offset: int = 0) -> None:
        from datetime import date, timedelta
        sync = self._get_notion_sync()
        if sync is None or not self._overrides_dir:
            return
        target = date.today() + timedelta(days=day_offset)
        try:
            n = sync.push_day(target, self._config_path, self._overrides_dir)
            self.showMessage("Schedule Notifier",
                             f"Notion 동기화 완료: {target.isoformat()} ({n}개 블록)",
                             QSystemTrayIcon.MessageIcon.Information, 3000)
        except Exception as e:
            self.showMessage("Schedule Notifier",
                             f"Notion 동기화 실패: {e}",
                             QSystemTrayIcon.MessageIcon.Warning, 3500)

    def _notion_push_week(self) -> None:
        from datetime import date, timedelta
        sync = self._get_notion_sync()
        if sync is None or not self._overrides_dir:
            return
        today = date.today()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        try:
            n = sync.push_range(start, end, self._config_path, self._overrides_dir)
            self.showMessage("Schedule Notifier",
                             f"Notion 주간 동기화 완료: {n}개 블록",
                             QSystemTrayIcon.MessageIcon.Information, 3000)
        except Exception as e:
            self.showMessage("Schedule Notifier",
                             f"Notion 주간 동기화 실패: {e}",
                             QSystemTrayIcon.MessageIcon.Warning, 3500)

    def _toggle_theme(self) -> None:
        if not self._config_path:
            return
        from core import theme
        new_name = theme.toggle(self._config_path)
        self.showMessage(
            "Schedule Notifier",
            f"테마: {new_name} (재시작 후 완전히 적용됩니다)",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _show_history(self) -> None:
        if self._data_dir is None:
            return
        if self._history_window is None:
            from ui.history_window import HistoryWindow
            self._history_window = HistoryWindow(self._data_dir)
        self._history_window.refresh()
        self._history_window.show()
        self._history_window.raise_()
        self._history_window.activateWindow()

    def _snooze(self, minutes: int) -> None:
        if not self._engine:
            return
        result = self._engine.snooze_next(minutes)
        if result is None:
            self.showMessage("Schedule Notifier", "미룰 다음 알림이 없습니다",
                             QSystemTrayIcon.MessageIcon.Information, 2000)
            return
        title, new_at = result
        self.showMessage(
            "Schedule Notifier",
            f"'{title}' → {new_at.strftime('%H:%M')}로 미룸",
            QSystemTrayIcon.MessageIcon.Information, 2500,
        )

    def _show_window(self) -> None:
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def _reload(self) -> None:
        if self._engine:
            self._engine.reload_today()
            if self._engine.today:
                self._window.update_schedule(self._engine.today)
            self.showMessage("Schedule Notifier", "일정 새로고침 완료", QSystemTrayIcon.MessageIcon.Information, 2000)

    # ------------------------------------------------------------------
    # DND (방해 금지)
    # ------------------------------------------------------------------

    def _is_dnd_active(self) -> bool:
        if self._dnd_until is None:
            return False
        return datetime.now() < self._dnd_until

    def _guarded_notify(self, *args, **kwargs) -> None:
        if self._is_dnd_active():
            return
        self._original_notify(*args, **kwargs)
        if self._data_dir is not None:
            try:
                from core.history import log_notification
                block = kwargs.get("block") if "block" in kwargs else (args[0] if args else None)
                if block is not None:
                    log_notification(
                        getattr(block, "time", ""),
                        getattr(block, "title", ""),
                        getattr(block, "kind", ""),
                        self._data_dir,
                    )
            except Exception:
                pass

    def _pause_dnd_minutes(self, minutes: int) -> None:
        self._dnd_until = datetime.now() + timedelta(minutes=minutes)
        self.showMessage(
            "Schedule Notifier",
            f"알림이 {minutes}분 동안 일시정지됩니다",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _pause_dnd_today(self) -> None:
        now = datetime.now()
        self._dnd_until = now.replace(hour=23, minute=59, second=59, microsecond=0)
        self.showMessage(
            "Schedule Notifier",
            "오늘 23:59까지 알림이 일시정지됩니다",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _resume_dnd(self) -> None:
        self._dnd_until = None
        self.showMessage(
            "Schedule Notifier",
            "알림이 재개되었습니다",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    # ------------------------------------------------------------------
    # 설정
    # ------------------------------------------------------------------

    def _show_settings(self) -> None:
        if not self._config_path:
            return
        if self._settings_window is None:
            from ui.settings_dialog import SettingsDialog
            self._settings_window = SettingsDialog(self._config_path)
            self._settings_window.settings_changed.connect(self._on_settings_changed)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _on_settings_changed(self) -> None:
        if self._engine:
            self._engine.reload_today()

    # ------------------------------------------------------------------
    # 백업
    # ------------------------------------------------------------------

    def _show_search(self) -> None:
        if not self._config_path or not self._overrides_dir:
            return
        from ui.search_dialog import SearchDialog
        dlg = SearchDialog(self._config_path, self._overrides_dir)
        def _jump(d):
            from core.config_loader import load_day
            sched = load_day(d, self._config_path, self._overrides_dir)
            self._window.update_schedule(sched)
            self._show_window()
        dlg.date_selected.connect(_jump)
        dlg.exec()

    def _export_ical(self) -> None:
        if not self._config_path or not self._overrides_dir:
            return
        try:
            from core.ical_export import export_range_to_ics
            from datetime import date
            import calendar as _cal
            today = date.today()
            start = today.replace(day=1)
            last = _cal.monthrange(today.year, today.month)[1]
            end = today.replace(day=last)
            out = self._config_path.parent / f"planner_{today.strftime('%Y-%m')}.ics"
            n = export_range_to_ics(start, end, self._config_path, self._overrides_dir, out)
            self.showMessage("Schedule Notifier",
                             f"{n}개 이벤트 → {out.name}",
                             QSystemTrayIcon.MessageIcon.Information, 3000)
        except Exception as e:
            self.showMessage("Schedule Notifier",
                             f"iCal 내보내기 실패: {e}",
                             QSystemTrayIcon.MessageIcon.Warning, 3000)

    def _create_backup(self) -> None:
        if not self._config_path or not self._overrides_dir:
            self.showMessage(
                "Schedule Notifier",
                "백업 실패: 경로 정보가 없습니다",
                QSystemTrayIcon.MessageIcon.Warning,
                2500,
            )
            return
        try:
            from core.backup import create_backup
            output_dir = self._config_path.parent / "backups"
            zip_path = create_backup(self._config_path, self._overrides_dir, output_dir)
            self.showMessage(
                "Schedule Notifier",
                f"백업 완료: {zip_path.name}",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        except Exception as e:
            self.showMessage(
                "Schedule Notifier",
                f"백업 실패: {e}",
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )
