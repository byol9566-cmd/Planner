from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def log_notification(
    block_time: str,
    title: str,
    kind: str,
    data_dir: Path,
    when: datetime | None = None,
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "notify_history.jsonl"
    rec = {
        "ts": (when or datetime.now()).isoformat(timespec="seconds"),
        "time": block_time,
        "title": title,
        "kind": kind,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_history(data_dir: Path, limit: int = 200) -> list[dict]:
    path = data_dir / "notify_history.jsonl"
    if not path.exists():
        return []
    records: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    records.reverse()
    return records[:limit]


def clear_history(data_dir: Path) -> None:
    path = data_dir / "notify_history.jsonl"
    if path.exists():
        path.unlink()
