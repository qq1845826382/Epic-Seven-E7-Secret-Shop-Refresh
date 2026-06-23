from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

RunMode = Literal["mouse", "adb"]


@dataclass(frozen=True)
class ItemDefinition:
    key: str
    file_name: str
    display_name: str
    english_name: str
    price: int
    default_enabled: bool = True


@dataclass
class ItemSelection:
    item: ItemDefinition
    enabled: bool = True
    target_count: int | None = None
    count: int = 0
    template: Any = None

    @property
    def reached_target(self) -> bool:
        return self.target_count is not None and self.count >= self.target_count


@dataclass
class RunConfig:
    mode: RunMode
    budget: int | None
    stop_key: str = "esc"
    mouse_window_title: str = ""
    auto_move_window: bool = True
    mouse_sleep: float = 0.3
    screenshot_sleep: float = 0.3
    adb_device_id: str = ""
    adb_manual_address: str = ""
    adb_random_offset: bool = False
    adb_debug: bool = False
    adb_tap_sleep: float = 0.3
    from_legacy_entry: bool = False


@dataclass
class RunStatistics:
    mode: RunMode
    budget: int | None
    start_time: datetime = field(default_factory=datetime.now)
    refresh_count: int = 0
    gold_spent: int = 0
    item_counts: dict[str, int] = field(default_factory=dict)
    stop_reason: str = "未开始"

    @property
    def skystone_spent(self) -> int:
        return self.refresh_count * 3

    @property
    def remaining_refresh_count(self) -> int | None:
        if self.budget is None:
            return None
        return max(0, self.budget // 3 - self.refresh_count)

    def clone(self) -> "RunStatistics":
        return RunStatistics(
            mode=self.mode,
            budget=self.budget,
            start_time=self.start_time,
            refresh_count=self.refresh_count,
            gold_spent=self.gold_spent,
            item_counts=dict(self.item_counts),
            stop_reason=self.stop_reason,
        )


@dataclass
class RunResult:
    mode: RunMode
    statistics: RunStatistics
    duration_seconds: float
    stop_reason: str
    item_counts: dict[str, int]
    error_message: str | None = None
