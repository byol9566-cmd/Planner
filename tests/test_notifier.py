from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from core.config_loader import Block
from core.notifier import Notifier, in_silent_hours


def test_in_silent_hours_true():
    # 01:00 is in [00:00, 08:00)
    now = datetime(2026, 6, 1, 1, 0)
    assert in_silent_hours(now, "00:00", "08:00") is True


def test_in_silent_hours_false():
    now = datetime(2026, 6, 1, 9, 0)
    assert in_silent_hours(now, "00:00", "08:00") is False


def test_in_silent_hours_boundary():
    # exactly at end boundary — not silent
    now = datetime(2026, 6, 1, 8, 0)
    assert in_silent_hours(now, "00:00", "08:00") is False


def test_notify_skipped_in_silent_hours():
    tts = MagicMock()
    notifier = Notifier(tts=tts, silent_start="00:00", silent_end="08:00")
    block = Block("06:00", "기상", "wake")
    notifier.notify(block, datetime(2026, 6, 1, 6, 0))
    tts.speak.assert_not_called()


def test_notify_calls_tts_outside_silent():
    tts = MagicMock()
    notifier = Notifier(tts=tts, silent_start="00:00", silent_end="08:00")
    block = Block("09:00", "헬스", "workout")
    with patch.object(notifier, "_toast"):
        notifier.notify(block, datetime(2026, 6, 1, 9, 0))
    tts.speak.assert_called_once()


def test_notify_pre_alert_message():
    tts = MagicMock()
    notifier = Notifier(tts=tts, silent_start="00:00", silent_end="08:00")
    block = Block("09:00", "헬스", "workout")
    with patch.object(notifier, "_toast") as mock_toast:
        notifier.notify(block, datetime(2026, 6, 1, 8, 55), pre_alert=True)
    call_args = mock_toast.call_args[0]
    assert "5분 후" in call_args[1]


def test_notify_toast_failure_does_not_crash():
    tts = MagicMock()
    notifier = Notifier(tts=tts, silent_start="00:00", silent_end="08:00")
    block = Block("09:00", "헬스", "workout")
    with patch.object(notifier, "_toast", side_effect=Exception("no winotify")):
        notifier.notify(block, datetime(2026, 6, 1, 9, 0))
