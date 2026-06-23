from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Iterable

import keyboard

from app.backends.adb_backend import ADBBackend
from app.backends.base import BaseBackend
from app.backends.mouse_backend import MouseBackend
from app.core.history import write_history
from app.core.models import ItemSelection, RunConfig, RunResult, RunStatistics

StatisticsCallback = Callable[[RunStatistics], None]


class RefreshEngine:
    def __init__(
        self,
        config: RunConfig,
        selections: Iterable[ItemSelection],
        on_statistics: StatisticsCallback | None = None,
        logger: logging.Logger | None = None,
    ):
        self.config = config
        self.selections = [selection for selection in selections if selection.enabled]
        self.on_statistics = on_statistics
        self.logger = logger or logging.getLogger("e7shop")
        self.stop_requested = False
        self.statistics = RunStatistics(mode=config.mode, budget=config.budget)
        self.backend: BaseBackend = self._build_backend()

    def request_stop(self) -> None:
        self.stop_requested = True

    def run(self) -> RunResult:
        if not self.selections:
            raise RuntimeError("请至少选择一个要购买的物品。")
        if self.config.budget is None and not any(item.target_count for item in self.selections):
            raise RuntimeError("请至少设置一个停止条件：预算或目标数量。")

        self._load_templates()
        keyboard_thread = threading.Thread(target=self._watch_stop_key, daemon=True)
        keyboard_thread.start()

        start_time = time.time()
        error_message: str | None = None
        stop_reason = "已完成"
        try:
            self.backend.prepare()
            self.backend.open_shop()
            while not self.stop_requested:
                time.sleep(self.backend.page_settle_delay)
                purchased_keys = set()
                self._scan_page(purchased_keys)
                if self.stop_requested:
                    stop_reason = "用户手动停止"
                    break
                if self._all_targets_reached():
                    stop_reason = "已达到全部目标数量"
                    break

                self.backend.scroll_shop()
                time.sleep(self.backend.scroll_settle_delay)

                self._scan_page(purchased_keys, skip_purchased=True)
                if self.stop_requested:
                    stop_reason = "用户手动停止"
                    break
                if self._all_targets_reached():
                    stop_reason = "已达到全部目标数量"
                    break
                if self._budget_reached():
                    stop_reason = "已达到天空石预算"
                    break

                self.backend.refresh_shop()
                self.statistics.refresh_count += 1
                self._emit_statistics(stop_reason="运行中")
                self.logger.info(
                    "已完成第 %s 次刷新，已消耗 %s 天空石。",
                    self.statistics.refresh_count,
                    self.statistics.skystone_spent,
                )
        except Exception as exc:
            stop_reason = "运行异常结束"
            error_message = str(exc)
            self.logger.exception("运行过程中出现异常：%s", exc)
        finally:
            self.stop_requested = True
            duration = time.time() - start_time
            self.statistics.stop_reason = stop_reason
            result = RunResult(
                mode=self.config.mode,
                statistics=self.statistics.clone(),
                duration_seconds=duration,
                stop_reason=stop_reason,
                item_counts={selection.item.key: selection.count for selection in self.selections},
                error_message=error_message,
            )
            write_history(result, self.selections)
            self.backend.cleanup()

        self._log_summary(result)
        self._emit_statistics(stop_reason=stop_reason)
        return result

    def _build_backend(self) -> BaseBackend:
        if self.config.mode == "mouse":
            return MouseBackend(self.config, self.logger)
        if self.config.mode == "adb":
            return ADBBackend(self.config, self.logger)
        raise RuntimeError(f"未知模式：{self.config.mode}")

    def _load_templates(self) -> None:
        for selection in self.selections:
            selection.template = self.backend.load_template(selection.item.file_name)

    def _scan_page(self, purchased_keys: set[str], skip_purchased: bool = False) -> None:
        screenshot = self.backend.capture_screen()
        for selection in self.selections:
            if skip_purchased and selection.item.key in purchased_keys:
                continue
            position = self.backend.find_item_position(screenshot, selection.template)
            if position is None:
                continue
            self.backend.buy_item(position)
            selection.count += 1
            self.statistics.gold_spent += selection.item.price
            purchased_keys.add(selection.item.key)
            self.logger.info(
                "已购买 %s，当前数量 %s%s。",
                selection.item.display_name,
                selection.count,
                f"/{selection.target_count}" if selection.target_count else "",
            )
            self._emit_statistics(stop_reason="运行中")
            if self._all_targets_reached():
                break
            if self.stop_requested:
                break

    def _all_targets_reached(self) -> bool:
        has_target = False
        for selection in self.selections:
            if selection.target_count is None:
                continue
            has_target = True
            if selection.count < selection.target_count:
                return False
        return has_target

    def _budget_reached(self) -> bool:
        return self.config.budget is not None and self.statistics.refresh_count >= self.config.budget // 3

    def _watch_stop_key(self) -> None:
        if not self.config.stop_key:
            return
        while not self.stop_requested:
            try:
                if keyboard.is_pressed(self.config.stop_key):
                    self.logger.info("检测到停止热键“%s”，准备结束本次运行。", self.config.stop_key)
                    self.stop_requested = True
                    return
            except Exception:
                return
            time.sleep(0.1)

    def _emit_statistics(self, stop_reason: str) -> None:
        self.statistics.item_counts = {selection.item.key: selection.count for selection in self.selections}
        self.statistics.stop_reason = stop_reason
        if self.on_statistics:
            self.on_statistics(self.statistics.clone())

    def _log_summary(self, result: RunResult) -> None:
        self.logger.info("运行结束：%s。", result.stop_reason)
        self.logger.info("总耗时：%.2f 秒。", result.duration_seconds)
        self.logger.info("刷新次数：%s。", result.statistics.refresh_count)
        self.logger.info("天空石消耗：%s。", result.statistics.skystone_spent)
        self.logger.info("金币消耗：%s。", result.statistics.gold_spent)
        for selection in self.selections:
            self.logger.info("%s：%s", selection.item.display_name, selection.count)
