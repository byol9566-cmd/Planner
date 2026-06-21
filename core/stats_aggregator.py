from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .config_loader import load_day
from .completion import load_completions, block_key, _block_minutes


def aggregate_range(
    start: date,
    end: date,
    config_path: Path,
    overrides_dir: Path,
) -> dict:
    """start~end (inclusive) 범위 일정 집계.

    Returns:
        {
            "by_kind": {kind: {"done_min": int, "total_min": int, "done_count": int, "total_count": int}},
            "by_weekday": {0..6: {"done_pct": float, "days": int}},  # 0=월요일
            "daily": [{"date": date, "done_pct": float, "done_min": int, "total_min": int}],
            "totals": {"done_min": int, "total_min": int, "done_count": int, "total_count": int, "days": int},
        }
    """
    by_kind: dict[str, dict] = defaultdict(lambda: {
        "done_min": 0, "total_min": 0, "done_count": 0, "total_count": 0
    })
    # 요일별 달성률 합산 (평균 계산용)
    weekday_pct_sum: dict[int, float] = defaultdict(float)
    weekday_days: dict[int, int] = defaultdict(int)

    daily: list[dict] = []
    totals = {"done_min": 0, "total_min": 0, "done_count": 0, "total_count": 0, "days": 0}

    current = start
    while current <= end:
        try:
            sched = load_day(current, config_path, overrides_dir)
        except Exception:
            current += timedelta(days=1)
            continue

        # 블록 없는 날 건너뜀
        if not sched.blocks:
            current += timedelta(days=1)
            continue

        completions = load_completions(current, overrides_dir)
        items = _block_minutes(sched.blocks)  # [(Block, duration_minutes)]

        day_done_min = 0
        day_total_min = 0
        day_done_count = 0

        for block, duration in items:
            key = block_key(block)
            kind = block.kind

            by_kind[kind]["total_min"] += duration
            by_kind[kind]["total_count"] += 1
            day_total_min += duration

            if key in completions:
                by_kind[kind]["done_min"] += duration
                by_kind[kind]["done_count"] += 1
                day_done_min += duration
                day_done_count += 1

        day_done_pct = (day_done_min / day_total_min * 100) if day_total_min else 0.0

        daily.append({
            "date": current,
            "done_pct": day_done_pct,
            "done_min": day_done_min,
            "total_min": day_total_min,
        })

        wd = current.weekday()  # 0=월, 6=일
        weekday_pct_sum[wd] += day_done_pct
        weekday_days[wd] += 1

        totals["done_min"] += day_done_min
        totals["total_min"] += day_total_min
        totals["done_count"] += day_done_count
        totals["total_count"] += len(items)
        totals["days"] += 1

        current += timedelta(days=1)

    by_weekday: dict[int, dict] = {}
    for wd in range(7):
        days_cnt = weekday_days[wd]
        avg_pct = (weekday_pct_sum[wd] / days_cnt) if days_cnt else 0.0
        by_weekday[wd] = {"done_pct": avg_pct, "days": days_cnt}

    return {
        "by_kind": dict(by_kind),
        "by_weekday": by_weekday,
        "daily": daily,
        "totals": totals,
    }
