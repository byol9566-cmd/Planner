from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from .config_loader import Block, load_day


def block_key(block: Block) -> str:
    return f"{block.time}|{block.title}"


def _override_path(date_: date, overrides_dir: Path) -> Path:
    return overrides_dir / f"{date_.isoformat()}.json"


def _read_override(date_: date, overrides_dir: Path) -> dict:
    f = _override_path(date_, overrides_dir)
    if not f.exists():
        return {}
    with open(f, encoding="utf-8") as fp:
        return json.load(fp)


def _write_override(date_: date, data: dict, overrides_dir: Path) -> None:
    overrides_dir.mkdir(parents=True, exist_ok=True)
    f = _override_path(date_, overrides_dir)
    with open(f, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)


def load_completions(date_: date, overrides_dir: Path) -> set[str]:
    data = _read_override(date_, overrides_dir)
    return set(data.get("completions", []))


def set_completion(date_: date, key: str, done: bool, overrides_dir: Path) -> set[str]:
    data = _read_override(date_, overrides_dir)
    items = set(data.get("completions", []))
    if done:
        items.add(key)
    else:
        items.discard(key)
    data["completions"] = sorted(items)
    _write_override(date_, data, overrides_dir)
    return items


def toggle_completion(date_: date, key: str, overrides_dir: Path) -> bool:
    current = load_completions(date_, overrides_dir)
    new_state = key not in current
    set_completion(date_, key, new_state, overrides_dir)
    return new_state


def _block_minutes(blocks: list[Block]) -> list[tuple[Block, int]]:
    """Return [(block, duration_minutes)] sorted by start time."""
    def mins(t: str) -> int:
        if t == "24:00":
            return 24 * 60
        h, m = map(int, t.split(":"))
        return h * 60 + m

    items = sorted(blocks, key=lambda b: mins(b.time))
    result = []
    for i, b in enumerate(items):
        start = mins(b.time)
        if i + 1 < len(items):
            end = mins(items[i + 1].time)
        elif b.end_time:
            end = mins(b.end_time)
        else:
            end = min(start + 60, 24 * 60)
        result.append((b, max(end - start, 1)))
    return result


def compute_stats(blocks: list[Block], completions: set[str]) -> dict:
    """Return stats dict with both time-weighted and count-based metrics."""
    items = _block_minutes(blocks)
    total_blocks = len(items)
    total_min = sum(d for _, d in items)
    done_blocks = sum(1 for b, _ in items if block_key(b) in completions)
    done_min = sum(d for b, d in items if block_key(b) in completions)

    count_pct = (done_blocks / total_blocks * 100) if total_blocks else 0.0
    time_pct = (done_min / total_min * 100) if total_min else 0.0
    return {
        "done_blocks": done_blocks,
        "total_blocks": total_blocks,
        "done_minutes": done_min,
        "total_minutes": total_min,
        "count_pct": count_pct,
        "time_pct": time_pct,
    }


def load_notes(date_: date, overrides_dir: Path) -> dict[str, str]:
    """overrides JSON의 notes 필드 반환. {block_key: note_text}"""
    data = _read_override(date_, overrides_dir)
    return dict(data.get("notes", {}))


def get_note(date_: date, key: str, overrides_dir: Path) -> str:
    """단일 블록의 메모. 없으면 빈 문자열."""
    return load_notes(date_, overrides_dir).get(key, "")


def set_note(date_: date, key: str, note: str, overrides_dir: Path) -> None:
    """note가 빈 문자열이면 키 삭제, 아니면 저장. 기존 completions/blocks 보존."""
    data = _read_override(date_, overrides_dir)
    notes: dict = dict(data.get("notes", {}))
    if note:
        notes[key] = note
    else:
        notes.pop(key, None)
    if notes:
        data["notes"] = notes
    else:
        data.pop("notes", None)
    _write_override(date_, data, overrides_dir)


def day_completion_ratio(date_: date, config_path: Path, overrides_dir: Path) -> dict | None:
    """Lightweight stats for a calendar cell. Returns None if the day has no blocks."""
    try:
        sched = load_day(date_, config_path, overrides_dir)
    except Exception:
        return None
    if not sched.blocks:
        return None
    completions = load_completions(date_, overrides_dir)
    return compute_stats(sched.blocks, completions)
