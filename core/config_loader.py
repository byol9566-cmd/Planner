from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Block:
    time: str            # "HH:MM" or "24:00"
    title: str
    kind: str            # wake|workout|meal|buffer|deepwork|reading|theme|marketing|wrap|winddown|sleep|light|event
    end_time: str = ""   # optional explicit end time "HH:MM"; empty = implicit (next block's start)

    def to_datetime(self, ref_date: date) -> datetime:
        if self.time == "24:00":
            return datetime.combine(ref_date, time(0, 0)) + timedelta(days=1)
        h, m = map(int, self.time.split(":"))
        return datetime.combine(ref_date, time(h, m))

    def to_dict(self) -> dict:
        d: dict = {"time": self.time, "title": self.title, "kind": self.kind}
        if self.end_time:
            d["end_time"] = self.end_time
        return d


@dataclass(frozen=True)
class DaySchedule:
    date: date
    type_code: str
    type_name: str
    blocks: list[Block]
    events: list[Block]
    note: str | None


def _load_raw(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def settings(config_path: Path) -> dict:
    return _load_raw(config_path)["settings"]


def _expand_theme(blocks: list[Block], ref_date: date, weekday_themes: dict) -> list[Block]:
    day_key = ref_date.strftime("%a")  # Mon, Tue, ...
    theme_text = weekday_themes.get(day_key, "")
    result = []
    for b in blocks:
        if b.kind == "theme" and theme_text:
            result.append(Block(b.time, f"{b.title} — {theme_text}", b.kind))
        else:
            result.append(b)
    return result


def load_day(today: date, config_path: Path, overrides_dir: Path) -> DaySchedule:
    raw = _load_raw(config_path)
    cal_entry = raw["calendar"].get(today.isoformat(), {})
    type_code = cal_entry.get("type", "A")
    template = raw["templates"].get(type_code, {"name": type_code, "blocks": []})
    type_name = template["name"]
    note = cal_entry.get("note")

    override_file = overrides_dir / f"{today.isoformat()}.json"
    raw_blocks = template.get("blocks", [])
    if override_file.exists():
        with open(override_file, encoding="utf-8") as f:
            override_data = json.load(f)
        if "blocks" in override_data:
            raw_blocks = override_data["blocks"]

    blocks = [Block(b["time"], b["title"], b["kind"], b.get("end_time", "")) for b in raw_blocks]

    if type_code == "A":
        blocks = _expand_theme(blocks, today, raw.get("weekday_themes", {}))

    raw_events = cal_entry.get("events", [])
    events = [Block(e["time"], e["title"], e.get("kind", "event")) for e in raw_events]

    return DaySchedule(
        date=today,
        type_code=type_code,
        type_name=type_name,
        blocks=blocks,
        events=events,
        note=note,
    )


def template_names(config_path: Path) -> dict[str, str]:
    raw = _load_raw(config_path)
    return {k: v["name"] for k, v in raw["templates"].items()}


def save_template(type_code: str, blocks: list[Block], config_path: Path) -> None:
    raw = _load_raw(config_path)
    raw["templates"][type_code]["blocks"] = [b.to_dict() for b in blocks]
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)


def save_calendar_type(date_: date, type_code: str, config_path: Path) -> None:
    raw = _load_raw(config_path)
    entry = raw["calendar"].setdefault(date_.isoformat(), {})
    entry["type"] = type_code
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)


def save_override(date_: date, blocks: list[Block], overrides_dir: Path) -> Path:
    overrides_dir.mkdir(parents=True, exist_ok=True)
    override_file = overrides_dir / f"{date_.isoformat()}.json"
    existing: dict = {}
    if override_file.exists():
        with open(override_file, encoding="utf-8") as f:
            existing = json.load(f)
    existing["blocks"] = [b.to_dict() for b in blocks]
    with open(override_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    return override_file
