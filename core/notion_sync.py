"""Notion 단방향 동기화.

PC 로컬 일정 → Notion 데이터베이스로 push.
- 매핑 테이블(`data/notion_map.json`): block_key → notion page_id
- 페이지가 있으면 update, 없으면 create
- 해당 날짜에서 사라진 키는 Notion에서 archive

데이터베이스 스키마 (사용자가 Notion에서 생성):
- Title (title)         : 블록 제목
- Date (date)           : 날짜
- Time (rich_text)      : "HH:MM"
- Kind (select)         : kind 이름
- Done (checkbox)       : 완료 여부
- Note (rich_text)      : 메모
- BlockKey (rich_text)  : 고유 키 (date|HHMM|title)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from .config_loader import Block, load_day
from .completion import block_key, load_completions, load_notes

logger = logging.getLogger(__name__)

MAP_FILENAME = "notion_map.json"


@dataclass
class NotionConfig:
    token: str
    database_id: str
    enabled: bool = False

    @classmethod
    def from_settings(cls, config_path: Path) -> Optional["NotionConfig"]:
        try:
            with open(config_path, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            return None
        nt = (raw.get("settings", {}) or {}).get("notion", {}) or {}
        token = (os.environ.get("NOTION_TOKEN") or nt.get("token", "")).strip()
        db_id = (os.environ.get("NOTION_DATABASE_ID") or nt.get("database_id", "")).strip()
        enabled = bool(nt.get("enabled", False))
        if not token or not db_id:
            return None
        return cls(token=token, database_id=db_id, enabled=enabled)


def save_notion_settings(
    config_path: Path,
    token: str,
    database_id: str,
    enabled: bool,
) -> None:
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        raw = {}
    settings = raw.setdefault("settings", {})
    settings["notion"] = {
        "token": token.strip(),
        "database_id": database_id.strip(),
        "enabled": bool(enabled),
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)


def _load_map(data_dir: Path) -> dict[str, str]:
    path = data_dir / MAP_FILENAME
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_map(data_dir: Path, mapping: dict[str, str]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / MAP_FILENAME
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


def _rich(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text or ""}}]


def _properties(d: date, block: Block, done: bool, note: str) -> dict:
    return {
        "Title":    {"title": _rich(block.title)},
        "Date":     {"date": {"start": d.isoformat()}},
        "Time":     {"rich_text": _rich(block.time)},
        "Kind":     {"select": {"name": block.kind or "event"}},
        "Done":     {"checkbox": bool(done)},
        "Note":     {"rich_text": _rich(note or "")},
        "BlockKey": {"rich_text": _rich(block_key(block))},
    }


class NotionSync:
    """Notion API 호출 래퍼. notion-client 패키지를 lazy import."""

    def __init__(self, cfg: NotionConfig, data_dir: Path):
        self._cfg = cfg
        self._data_dir = data_dir
        self._client = None

    def _get_client(self):
        if self._client is None:
            from notion_client import Client  # lazy
            self._client = Client(auth=self._cfg.token)
        return self._client

    def _get_data_source_id(self) -> str:
        """새 Notion API는 page 생성 시 data_source_id를 요구.
        database_id로부터 첫 data_source의 id를 조회 (캐시)."""
        if getattr(self, "_ds_id", None):
            return self._ds_id
        client = self._get_client()
        db = client.databases.retrieve(self._cfg.database_id)
        ds = (db.get("data_sources") or [{}])[0]
        self._ds_id = ds.get("id", "")
        return self._ds_id

    # ─────────────────────────────────────────────────────
    # 단일 블록 upsert
    # ─────────────────────────────────────────────────────
    def upsert_block(
        self,
        d: date,
        block: Block,
        done: bool,
        note: str,
        mapping: dict[str, str] | None = None,
    ) -> None:
        if mapping is None:
            mapping = _load_map(self._data_dir)
            save_after = True
        else:
            save_after = False

        client = self._get_client()
        key = f"{d.isoformat()}|{block_key(block)}"
        props = _properties(d, block, done, note)

        page_id = mapping.get(key)
        try:
            if page_id:
                client.pages.update(page_id=page_id, properties=props)
            else:
                ds_id = self._get_data_source_id()
                parent = (
                    {"type": "data_source_id", "data_source_id": ds_id}
                    if ds_id else
                    {"database_id": self._cfg.database_id}
                )
                resp = client.pages.create(parent=parent, properties=props)
                mapping[key] = resp["id"]
        except Exception as e:
            logger.warning("Notion upsert 실패 (%s): %s", key, e)
            return

        if save_after:
            _save_map(self._data_dir, mapping)

    # ─────────────────────────────────────────────────────
    # 하루치 전체 push (변경분 + 사라진 키 archive)
    # ─────────────────────────────────────────────────────
    def push_day(self, d: date, config_path: Path, overrides_dir: Path) -> int:
        try:
            sched = load_day(d, config_path, overrides_dir)
        except Exception as e:
            logger.warning("Notion push_day load 실패: %s", e)
            return 0

        completions = load_completions(d, overrides_dir)
        notes = load_notes(d, overrides_dir)
        mapping = _load_map(self._data_dir)

        current_keys: set[str] = set()
        count = 0
        for block in sched.blocks:
            bk = block_key(block)
            full_key = f"{d.isoformat()}|{bk}"
            current_keys.add(full_key)
            done = bk in completions
            note = notes.get(bk, "")
            self.upsert_block(d, block, done, note, mapping=mapping)
            count += 1

        # 이 날짜의 사라진 키 archive
        prefix = f"{d.isoformat()}|"
        stale = [k for k in mapping if k.startswith(prefix) and k not in current_keys]
        client = self._get_client()
        for k in stale:
            try:
                client.pages.update(page_id=mapping[k], archived=True)
            except Exception as e:
                logger.warning("Notion archive 실패 (%s): %s", k, e)
            mapping.pop(k, None)

        _save_map(self._data_dir, mapping)
        return count

    def push_range(
        self,
        start: date,
        end: date,
        config_path: Path,
        overrides_dir: Path,
    ) -> int:
        from datetime import timedelta
        total = 0
        current = start
        while current <= end:
            total += self.push_day(current, config_path, overrides_dir)
            current += timedelta(days=1)
        return total


def autosync_in_background(
    config_path: Path,
    overrides_dir: Path,
    target_date: date | None = None,
    days_ahead: int = 2,
) -> None:
    """설정에서 enabled 시 background thread로 오늘~+days_ahead 범위 push.
    target_date가 범위 밖이면 그 날짜도 추가 push. 실패는 조용히 무시."""
    if not config_path or not overrides_dir:
        return
    try:
        from datetime import date as _date, timedelta as _td
        cfg = NotionConfig.from_settings(config_path)
        if cfg is None or not cfg.enabled:
            return
        import threading
        data_dir = config_path.parent / "data"

        def _run():
            try:
                sync = NotionSync(cfg, data_dir)
                today = _date.today()
                end = today + _td(days=days_ahead)
                sync.push_range(today, end, config_path, overrides_dir)
                if target_date is not None and (target_date < today or target_date > end):
                    sync.push_day(target_date, config_path, overrides_dir)
            except Exception:
                pass

        threading.Thread(target=_run, daemon=True).start()
    except Exception:
        pass
