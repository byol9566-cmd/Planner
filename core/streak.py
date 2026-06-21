from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .completion import day_completion_ratio


def current_streak(
    today: date,
    config_path: Path,
    overrides_dir: Path,
    threshold_pct: float = 70.0,
) -> int:
    """오늘부터 거꾸로 가며 time_pct >= threshold_pct인 연속일 수.

    오늘이 아직 진행 중일 수 있으므로:
    - 오늘이 threshold 미달이면 어제부터 카운트 시작.
    - 오늘이 threshold 이상이면 오늘을 1로 시작.
    """
    def _qualifies(d: date) -> bool:
        stats = day_completion_ratio(d, config_path, overrides_dir)
        if stats is None:
            return False
        return stats["time_pct"] >= threshold_pct

    # 오늘 달성 여부 확인 → 미달이면 어제부터 시작
    start_day = today if _qualifies(today) else today - timedelta(days=1)

    count = 0
    current = start_day
    while True:
        if _qualifies(current):
            count += 1
            current -= timedelta(days=1)
        else:
            break

    return count


def longest_streak(
    start: date,
    end: date,
    config_path: Path,
    overrides_dir: Path,
    threshold_pct: float = 70.0,
) -> int:
    """start~end 범위 내 최장 연속 달성일 수."""
    best = 0
    current_run = 0
    current = start

    while current <= end:
        stats = day_completion_ratio(current, config_path, overrides_dir)
        qualifies = stats is not None and stats["time_pct"] >= threshold_pct

        if qualifies:
            current_run += 1
            if current_run > best:
                best = current_run
        else:
            current_run = 0

        current += timedelta(days=1)

    return best
