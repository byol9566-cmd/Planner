from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from .config_loader import DaySchedule, load_day, settings
from .notifier import Notifier
from .tts import TTS

logger = logging.getLogger(__name__)


class ScheduleEngine:
    def __init__(self, config_path: Path, overrides_dir: Path):
        self.config_path = config_path
        self.overrides_dir = overrides_dir
        self._sched = BackgroundScheduler()
        self._day: DaySchedule | None = None
        self._notifier: Notifier | None = None

    def start(self) -> None:
        cfg = settings(self.config_path)
        tts = TTS(voice=cfg.get("tts_voice", "ko-KR-SunHiNeural"), rate=cfg.get("tts_rate", "+0%"))
        self._notifier = Notifier(
            tts=tts,
            silent_start=cfg.get("silent_hours_start", "00:00"),
            silent_end=cfg.get("silent_hours_end", "08:00"),
        )
        self._load_today()

        h, m = map(int, cfg.get("daily_refresh_time", "00:05").split(":"))
        self._sched.add_job(self._load_today, CronTrigger(hour=h, minute=m), id="daily_refresh")

        self._sched.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        self._sched.shutdown(wait=False)

    def _load_today(self) -> None:
        today = date.today()
        self._day = load_day(today, self.config_path, self.overrides_dir)
        self._reschedule_day()
        logger.info("Loaded schedule for %s (%s)", today, self._day.type_name)

    def _reschedule_day(self) -> None:
        for job in self._sched.get_jobs():
            if job.id.startswith("block_"):
                job.remove()

        if self._day is None:
            return

        cfg = settings(self.config_path)
        pre_min = int(cfg.get("pre_alert_minutes", 5))
        today = self._day.date

        all_blocks = self._day.blocks + self._day.events
        for i, block in enumerate(all_blocks):
            fire_at = block.to_datetime(today)
            now = datetime.now()
            if fire_at <= now:
                continue

            self._sched.add_job(
                self._fire_block,
                DateTrigger(run_date=fire_at),
                args=[block, fire_at, False],
                id=f"block_main_{i}",
            )

            pre_at = fire_at - timedelta(minutes=pre_min)
            if pre_at > now:
                self._sched.add_job(
                    self._fire_block,
                    DateTrigger(run_date=pre_at),
                    args=[block, pre_at, True],
                    id=f"block_pre_{i}",
                )

    def _fire_block(self, block, fire_at: datetime, pre_alert: bool) -> None:
        if self._notifier:
            self._notifier.notify(block, fire_at, pre_alert=pre_alert)

    def reload_today(self) -> None:
        self._load_today()

    def snooze_next(self, minutes: int = 10) -> tuple[str, datetime] | None:
        """가장 가까운 다가오는 블록 알림을 minutes만큼 뒤로 미룬다.
        Returns (block_title, new_fire_at) or None if 미룰 블록이 없음."""
        if self._day is None:
            return None
        now = datetime.now()
        all_blocks = self._day.blocks + self._day.events
        upcoming = [(b, b.to_datetime(self._day.date)) for b in all_blocks]
        upcoming = [(b, t) for b, t in upcoming if t > now]
        if not upcoming:
            return None
        upcoming.sort(key=lambda bt: bt[1])
        target_block, target_at = upcoming[0]
        new_at = target_at + timedelta(minutes=minutes)

        for job in self._sched.get_jobs():
            if job.id.startswith("block_") and job.args and job.args[0] is target_block:
                job.remove()

        self._sched.add_job(
            self._fire_block,
            DateTrigger(run_date=new_at),
            args=[target_block, new_at, False],
            id=f"block_snoozed_{int(new_at.timestamp())}",
        )
        return (target_block.title, new_at)

    @property
    def today(self) -> DaySchedule | None:
        return self._day
