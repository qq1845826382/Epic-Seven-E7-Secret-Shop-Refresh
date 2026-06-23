from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from app.core.constants import HISTORY_DIR
from app.core.models import ItemSelection, RunResult

HISTORY_FILE = HISTORY_DIR / "UnifiedHistory.csv"


def write_history(run_result: RunResult, selections: Iterable[ItemSelection]) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    headers = [
        "timestamp",
        "mode",
        "duration_seconds",
        "stop_reason",
        "refresh_count",
        "skystone_spent",
        "gold_spent",
        "error_message",
    ]
    headers.extend(selection.item.display_name for selection in selections if selection.enabled)

    if not HISTORY_FILE.exists():
        with HISTORY_FILE.open("w", newline="", encoding="utf-8-sig") as file:
            csv.writer(file).writerow(headers)

    row = [
        run_result.statistics.start_time.isoformat(timespec="seconds"),
        run_result.mode,
        round(run_result.duration_seconds, 2),
        run_result.stop_reason,
        run_result.statistics.refresh_count,
        run_result.statistics.skystone_spent,
        run_result.statistics.gold_spent,
        run_result.error_message or "",
    ]
    row.extend(run_result.item_counts.get(selection.item.key, 0) for selection in selections if selection.enabled)

    with HISTORY_FILE.open("a", newline="", encoding="utf-8-sig") as file:
        csv.writer(file).writerow(row)

    return HISTORY_FILE
