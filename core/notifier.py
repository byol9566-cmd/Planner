from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time

from .config_loader import Block
from .tts import TTS

logger = logging.getLogger(__name__)


def _parse_hhmm(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


def in_silent_hours(now: datetime, start: str, end: str) -> bool:
    s = _parse_hhmm(start)
    e = _parse_hhmm(end)
    t = now.time()
    if s == e:
        return False
    if s < e:
        return s <= t < e
    return t >= s or t < e


@dataclass
class Notifier:
    tts: TTS
    silent_start: str = "00:00"
    silent_end: str = "08:00"
    app_name: str = "Schedule Notifier"

    def notify(self, block: Block, when: datetime, *, pre_alert: bool = False) -> None:
        if in_silent_hours(when, self.silent_start, self.silent_end):
            logger.info("Silent hours — skipping notify for %s", block.title)
            return
        title = f"{block.time} · {block.title}"
        body = "5분 후 시작" if pre_alert else "지금 시작"
        try:
            self._toast(title, body)
        except Exception as e:
            logger.warning("Toast failed: %s", e)
        spoken = f"{body}. {block.title}"
        try:
            self.tts.speak(spoken)
        except Exception as e:
            logger.warning("TTS failed: %s", e)

    def _toast(self, title: str, body: str) -> None:
        from winotify import Notification
        toast = Notification(
            app_id=self.app_name,
            title=title,
            msg=body,
            duration="short",
        )
        toast.show()
