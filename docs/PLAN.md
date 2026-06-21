# Schedule Notifier — Build Plan

Source spec: `docs/SPEC.md` (do not re-read each step — use this doc).

## Decisions (locked)

- **OS**: Windows 10
- **Python**: 3.11+
- **TTS**: Edge-TTS primary, `pyttsx3` fallback on network/error
- **Toast**: `winotify`
- **Scheduler**: APScheduler
- **GUI**: PySide6
- **Config strategy**: `config.json` = templates (immutable). `overrides/YYYY-MM-DD.json` = daily edits (merged on top).
- **Timezone**: Asia/Seoul

## Directory layout

```
C:\planner\
├── config.json
├── overrides/                # YYYY-MM-DD.json per edited day
├── core/
│   ├── __init__.py
│   ├── config_loader.py
│   ├── tts.py
│   ├── notifier.py
│   └── scheduler.py
├── ui/
│   ├── __init__.py
│   ├── timeline_window.py
│   ├── block_editor.py
│   └── tray.py
├── tests/
├── docs/
│   ├── SPEC.md
│   └── PLAN.md
├── app.py                    # GUI entrypoint
├── notifier.py               # CLI entrypoint (spec §5)
└── requirements.txt
```

## Module contracts

### `core/config_loader.py`

```python
@dataclass(frozen=True)
class Block:
    time: str          # "HH:MM", "24:00" allowed
    title: str
    kind: str          # wake|workout|meal|buffer|deepwork|reading|theme|marketing|wrap|winddown|sleep|light

@dataclass(frozen=True)
class DaySchedule:
    date: date
    type_code: str     # "A"|"B"|"C"|"D"|"E"|"F"|"OFF"
    type_name: str
    blocks: list[Block]
    events: list[Block]      # extra one-off events
    note: str | None         # OFF / E note shown morning

def load_day(today: date, config_path: Path, overrides_dir: Path) -> DaySchedule: ...
def save_override(date_: date, blocks: list[Block], overrides_dir: Path) -> Path: ...
def settings(config_path: Path) -> dict: ...   # timezone, pre_alert_minutes, daily_refresh_time
```

**Merge rule**: if `overrides/YYYY-MM-DD.json` exists → use its `blocks` (full replacement). Else use `templates[type].blocks`. Events always from `config.json`.

**Theme expansion**: when `type == "A"`, find block with `kind == "theme"` and append `weekday_themes[Mon|Tue|...]` to title.

**24:00 handling**: kept as string "24:00" in storage. Conversion to datetime = (date + 1day, 00:00).

**Override file schema**:
```json
{"blocks": [{"time": "09:00", "title": "...", "kind": "workout"}]}
```

### `core/tts.py`

```python
class TTS:
    def __init__(self, voice: str = "ko-KR-SunHiNeural", rate: str = "+0%"): ...
    def speak(self, text: str) -> None:
        """Try Edge-TTS first; on any exception or timeout, fall back to pyttsx3."""
```

- Edge-TTS: synth to temp MP3 → play via `playsound` or `winsound`
- Fallback trigger: network error, timeout (>3s), Edge-TTS exception
- Silent hours: caller's responsibility (notifier checks before calling)

### `core/notifier.py`

```python
def notify(block: Block, next_block: Block | None, *, is_pre_alert: bool, tts: TTS, silent: bool) -> None
```

- Toast via `winotify` with title/body per spec §4
- If not silent → `tts.speak(body)`
- Buffer kind → special template

### `core/scheduler.py`

```python
class ScheduleEngine:
    def __init__(self, config_path, overrides_dir, tts): ...
    def start(self) -> None
    def refresh_today(self) -> None
    def now_block(self) -> Block | None
    def next_block(self) -> Block | None
    def today_blocks(self) -> list[Block]
```

- APScheduler `BackgroundScheduler` tz=Asia/Seoul
- Per block: register pre-alert (start - `pre_alert_minutes`) + main alert
- Daily cron at `daily_refresh_time` → clear jobs → re-register

### CLI: `notifier.py`

`run | now | next | today` — spec §5 exactly.

### GUI: `ui/timeline_window.py`

- Vertical timeline 0–24h, 1h = 40px
- Block = colored card (color per `kind`)
- Current time = red horizontal line, auto-updates every 60s
- Click card → open `BlockEditor`
- Header: today type + name + countdown to next block
- Left panel: 7-day mini-view (this week, color per type)

### `ui/block_editor.py`

QDialog: time-start, title, kind dropdown.
Save → `config_loader.save_override()` → emit signal → main window reloads.

### `ui/tray.py`

QSystemTrayIcon. Menu: Show / Now / Next / Today / Quit.
Close button → minimize to tray (not quit).

## Harness conventions

Each step ends with this report block:

```
status: success|warning|error
summary: <one line>
artifacts: <files>
next_actions: proceed to step N / blocked
```

## Recovery table (runtime)

| symptom | fix | stop_if |
|---|---|---|
| Edge-TTS network fail | auto pyttsx3 fallback | 2 consecutive falls → use fallback for session |
| winotify toast missing | check Focus Assist, console print | persistent → ask user |
| pyttsx3 no Korean voice | install SAPI5 Korean pack | warn once |
| APScheduler 24:00 | convert to next-day 00:00 in loader | test must pass |

## Step order (locked)

0. PLAN.md ← (this)
1. config_loader + tests
2. tts + notifier (single-shot test)
3. scheduler
4. CLI
5. GUI timeline (read-only)
6. Block editor + override
7. Tray + autostart helper
