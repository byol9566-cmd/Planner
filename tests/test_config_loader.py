from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from core.config_loader import Block, DaySchedule, load_day, save_override


CONFIG = {
    "settings": {
        "timezone": "Asia/Seoul",
        "pre_alert_minutes": 5,
        "daily_refresh_time": "00:05",
        "tts_voice": "ko-KR-SunHiNeural",
        "tts_rate": "+0%",
        "silent_hours_start": "00:00",
        "silent_hours_end": "08:00",
    },
    "weekday_themes": {
        "Mon": "주간 킥오프",
        "Tue": "인스타툰",
    },
    "templates": {
        "A": {
            "name": "휴가일",
            "blocks": [
                {"time": "08:30", "title": "기상", "kind": "wake"},
                {"time": "19:30", "title": "요일 테마 블록", "kind": "theme"},
                {"time": "24:00", "title": "취침", "kind": "sleep"},
            ],
        },
        "B": {
            "name": "부대 금요일",
            "blocks": [
                {"time": "12:00", "title": "낮 틈틈이 폰", "kind": "light"},
            ],
        },
    },
    "calendar": {
        "2026-06-01": {"type": "A"},
        "2026-06-02": {"type": "B"},
        "2026-06-03": {"type": "A", "note": "테스트 메모", "events": [
            {"time": "14:00", "title": "치과", "kind": "event"},
        ]},
    },
}


@pytest.fixture()
def config_file(tmp_path: Path) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps(CONFIG, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture()
def overrides_dir(tmp_path: Path) -> Path:
    d = tmp_path / "overrides"
    d.mkdir()
    return d


def test_load_day_type_a(config_file, overrides_dir):
    sched = load_day(date(2026, 6, 1), config_file, overrides_dir)
    assert sched.type_code == "A"
    assert sched.type_name == "휴가일"
    assert len(sched.blocks) == 3
    assert sched.note is None


def test_load_day_type_b(config_file, overrides_dir):
    sched = load_day(date(2026, 6, 2), config_file, overrides_dir)
    assert sched.type_code == "B"
    assert sched.type_name == "부대 금요일"


def test_load_day_events(config_file, overrides_dir):
    sched = load_day(date(2026, 6, 3), config_file, overrides_dir)
    assert len(sched.events) == 1
    assert sched.events[0].title == "치과"
    assert sched.note == "테스트 메모"


def test_theme_expand_on_monday(config_file, overrides_dir):
    # 2026-06-01 is a Monday
    sched = load_day(date(2026, 6, 1), config_file, overrides_dir)
    theme_block = next(b for b in sched.blocks if b.kind == "theme")
    assert "주간 킥오프" in theme_block.title


def test_theme_not_expanded_on_type_b(config_file, overrides_dir):
    sched = load_day(date(2026, 6, 2), config_file, overrides_dir)
    # type B has no theme block — just verify no crash
    assert all(b.kind != "theme" for b in sched.blocks)


def test_24_00_block_converts_to_next_day(config_file, overrides_dir):
    from datetime import timedelta

    sched = load_day(date(2026, 6, 1), config_file, overrides_dir)
    sleep_block = next(b for b in sched.blocks if b.time == "24:00")
    dt = sleep_block.to_datetime(date(2026, 6, 1))
    assert dt.date() == date(2026, 6, 2)
    assert dt.time().hour == 0 and dt.time().minute == 0


def test_override_replaces_blocks(config_file, overrides_dir):
    override_blocks = [
        Block("09:00", "특별 미팅", "event"),
        Block("11:00", "점심", "meal"),
    ]
    save_override(date(2026, 6, 1), override_blocks, overrides_dir)

    sched = load_day(date(2026, 6, 1), config_file, overrides_dir)
    assert len(sched.blocks) == 2
    assert sched.blocks[0].title == "특별 미팅"


def test_save_override_creates_file(config_file, overrides_dir):
    blocks = [Block("10:00", "운동", "workout")]
    path = save_override(date(2026, 6, 5), blocks, overrides_dir)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["blocks"][0]["title"] == "운동"


def test_unknown_date_defaults_to_type_a(config_file, overrides_dir):
    sched = load_day(date(2026, 7, 1), config_file, overrides_dir)
    assert sched.type_code == "A"
