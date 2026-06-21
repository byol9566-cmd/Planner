from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from core.config_loader import load_day, Block, DaySchedule


def _escape(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n").replace("\r", "")
    return text


def _parse_time(t: str) -> time:
    """'HH:MM' 또는 '24:00' 파싱. '24:00'은 다음날 00:00 처리용으로 None 반환."""
    if t == "24:00":
        return None  # sentinel: midnight next day
    h, m = t.split(":")
    return time(int(h), int(m))


def _to_dt(d: date, t: time | None) -> datetime:
    if t is None:
        return datetime(d.year, d.month, d.day) + timedelta(days=1)
    return datetime(d.year, d.month, d.day, t.hour, t.minute)


def _dtstamp_utc() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ")


def _dtlocal(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def _clamp_to_day(dt: datetime, d: date) -> datetime:
    midnight_next = datetime(d.year, d.month, d.day) + timedelta(days=1)
    return min(dt, midnight_next)


def _blocks_to_vevents(day: DaySchedule, d: date) -> list[str]:
    items: list[Block] = sorted(
        list(day.blocks) + list(day.events),
        key=lambda b: b.time,
    )

    dtstamp = _dtstamp_utc()
    vevents: list[str] = []

    for idx, block in enumerate(items):
        start_t = _parse_time(block.time)
        start_dt = _to_dt(d, start_t)

        # end_time 결정
        if getattr(block, "end_time", None):
            end_t = _parse_time(block.end_time)
            end_dt = _to_dt(d, end_t)
        elif idx + 1 < len(items):
            next_t = _parse_time(items[idx + 1].time)
            end_dt = _to_dt(d, next_t)
        else:
            end_dt = start_dt + timedelta(minutes=60)

        end_dt = _clamp_to_day(end_dt, d)

        uid_key = block.time.replace(":", "") + "-" + block.title
        uid = f"{_escape(uid_key)}@{d.isoformat()}.planner.local"

        lines = [
            "BEGIN:VEVENT",
            f"DTSTART;TZID=Asia/Seoul:{_dtlocal(start_dt)}",
            f"DTEND;TZID=Asia/Seoul:{_dtlocal(end_dt)}",
            f"SUMMARY:{_escape(block.title)}",
            f"CATEGORIES:{_escape(block.kind)}",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            "END:VEVENT",
        ]
        vevents.append("\r\n".join(lines))

    return vevents


def _build_ics(vevents: list[str]) -> str:
    header = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Schedule Notifier//KR\r\n"
        "CALSCALE:GREGORIAN\r\n"
    )
    footer = "END:VCALENDAR\r\n"
    body = "\r\n".join(vevents)
    if body:
        return header + body + "\r\n" + footer
    return header + footer


def export_day_to_ics(
    date_: date,
    config_path: Path,
    overrides_dir: Path,
    output_path: Path,
) -> int:
    day = load_day(date_, config_path, overrides_dir)
    vevents = _blocks_to_vevents(day, date_)
    ics = _build_ics(vevents)
    output_path.write_text(ics, encoding="utf-8")
    return len(vevents)


def export_range_to_ics(
    start: date,
    end: date,
    config_path: Path,
    overrides_dir: Path,
    output_path: Path,
) -> int:
    all_vevents: list[str] = []
    current = start
    while current <= end:
        try:
            day = load_day(current, config_path, overrides_dir)
            all_vevents.extend(_blocks_to_vevents(day, current))
        except Exception:
            pass
        current += timedelta(days=1)

    ics = _build_ics(all_vevents)
    output_path.write_text(ics, encoding="utf-8")
    return len(all_vevents)
