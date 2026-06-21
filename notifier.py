#!/usr/bin/env python
"""CLI entrypoint for Schedule Notifier."""
from __future__ import annotations

import argparse
import signal
import sys
import time
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
OVERRIDES_DIR = BASE_DIR / "overrides"


def cmd_run(args) -> None:
    from core.scheduler import ScheduleEngine

    engine = ScheduleEngine(CONFIG_PATH, OVERRIDES_DIR)
    engine.start()

    def _shutdown(sig, frame):
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    print("Schedule Notifier running. Press Ctrl+C to stop.")
    while True:
        time.sleep(60)


def cmd_today(args) -> None:
    from core.config_loader import load_day

    sched = load_day(date.today(), CONFIG_PATH, OVERRIDES_DIR)
    print(f"[{sched.type_name}] {sched.date.isoformat()}")
    if sched.note:
        print(f"  메모: {sched.note}")
    for b in sched.blocks:
        print(f"  {b.time}  {b.title}")
    if sched.events:
        print("  --- 일정 ---")
        for e in sched.events:
            print(f"  {e.time}  {e.title}")


def cmd_next(args) -> None:
    from core.config_loader import load_day

    sched = load_day(date.today(), CONFIG_PATH, OVERRIDES_DIR)
    now = datetime.now()
    upcoming = [b for b in sched.blocks + sched.events if b.to_datetime(sched.date) > now]
    if not upcoming:
        print("오늘 남은 블록이 없습니다.")
        return
    nxt = upcoming[0]
    dt = nxt.to_datetime(sched.date)
    diff = int((dt - now).total_seconds() / 60)
    print(f"다음: {nxt.time}  {nxt.title}  ({diff}분 후)")


def cmd_now(args) -> None:
    from core.config_loader import Block, load_day
    from core.notifier import Notifier
    from core.config_loader import settings
    from core.tts import TTS

    sched = load_day(date.today(), CONFIG_PATH, OVERRIDES_DIR)
    now = datetime.now()
    past = [b for b in sched.blocks + sched.events if b.to_datetime(sched.date) <= now]
    if not past:
        print("아직 시작된 블록이 없습니다.")
        return
    current = past[-1]

    cfg = settings(CONFIG_PATH)
    tts = TTS(voice=cfg.get("tts_voice", "ko-KR-SunHiNeural"))
    notifier = Notifier(tts=tts, silent_start="00:00", silent_end="00:00")
    notifier.notify(current, now)
    print(f"알림 발송: {current.time}  {current.title}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="notifier", description="Schedule Notifier")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("run", help="알림 데몬 실행")
    sub.add_parser("today", help="오늘 일정 출력")
    sub.add_parser("next", help="다음 블록 확인")
    sub.add_parser("now", help="현재 블록 즉시 알림")

    args = parser.parse_args()
    dispatch = {"run": cmd_run, "today": cmd_today, "next": cmd_next, "now": cmd_now}
    fn = dispatch.get(args.cmd)
    if fn is None:
        parser.print_help()
    else:
        fn(args)


if __name__ == "__main__":
    main()
