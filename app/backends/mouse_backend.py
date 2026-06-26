from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random
import shutil
import time
from typing import Callable

import cv2
import numpy as np
import pyautogui
import pygetwindow as gw

from app.backends.base import BaseBackend, StopRequested
from app.core.constants import ITEM_DEFINITIONS, PROJECT_ROOT
from app.services.price_ocr_service import (
    BASE_HEIGHT,
    BASE_WIDTH,
    PRICE_SLOTS,
    PriceSlot,
    price_ocr_service,
)
from app.services.window_capture_service import window_capture_service


BUY_RETRY_LIMIT = 3
RECOVERY_WAIT_SECONDS = 5.0
POST_CONFIRM_VERIFY_WAIT_SECONDS = 0.5
GRAY_MEAN_DIFF_THRESHOLD = 25.0
POST_BUY_CHANGE_TIMEOUT_SECONDS = 2.0
FRESH_FRAME_POLL_SECONDS = 0.25
DEBUG_CAPTURE_DIR = PROJECT_ROOT / "debug_captures"
DEBUG_PRICE_REGION_FILES = {f"{slot.key}.png" for slot in PRICE_SLOTS}


@dataclass(frozen=True)
class PurchaseTarget:
    slot: PriceSlot
    price: str
    buy_position: tuple[float, float]


class MouseBackend(BaseBackend):
    def __init__(
        self,
        config,
        logger,
        should_stop: Callable[[], bool] | None = None,
    ):
        super().__init__(config, logger)
        self._should_stop_callback = should_stop or (lambda: False)
        self.window = None
        self.hwnd: int | None = None
        self.scan_phase = "top"
        self._price_cache_phase: str | None = None
        self._price_cache_image = None
        self._price_cache = []

    def _raise_if_stop_requested(self) -> None:
        if self._should_stop_callback():
            raise StopRequested()

    def _sleep_interruptibly(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while True:
            self._raise_if_stop_requested()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.05, remaining))

    @property
    def page_settle_delay(self) -> float:
        return max(0.7 + self.config.screenshot_sleep, 1.0)

    @property
    def scroll_settle_delay(self) -> float:
        return 1.0

    def prepare(self) -> None:
        self._raise_if_stop_requested()
        price_ocr_service.ensure_ready()
        self._raise_if_stop_requested()

        title = self.config.mouse_window_title.strip()
        if not title:
            raise RuntimeError("请选择或输入模拟器窗口标题。")

        windows = gw.getWindowsWithTitle(title)
        self.window = next((window for window in windows if window.title == title), None)
        if self.window is None:
            raise RuntimeError(f'未找到窗口标题为“{title}”的模拟器。')

        self.hwnd = window_capture_service.find_window(title)

        try:
            if self.window.isMaximized or self.window.isMinimized:
                self.window.restore()
            if self.config.auto_move_window:
                self.window.moveTo(0, 0)
            self.window.resizeTo(906, 539)
            self._activate_window()
            window_capture_service.start_client_capture(self.hwnd)
            self.logger.info("已连接模拟器窗口：%s", title)
        except Exception as exc:  # pragma: no cover - pygetwindow depends on host environment
            raise RuntimeError(f"初始化模拟器窗口失败：{exc}") from exc

    def load_template(self, file_name: str):
        for item in ITEM_DEFINITIONS:
            if item.file_name == file_name:
                return str(item.price)
        raise RuntimeError(f"未找到物品价格定义：{file_name}")

    def open_shop(self) -> None:
        self._raise_if_stop_requested()
        self._activate_window()

        x, y = self._relative_point(0.05, 0.41)
        self._raise_if_stop_requested()
        pyautogui.moveTo(x, y)
        pyautogui.click()
        self._sleep_interruptibly(self.config.mouse_sleep)

        x, y = self._relative_point(0.44, 0.26)
        self._raise_if_stop_requested()
        pyautogui.moveTo(x, y)
        pyautogui.click()
        self._sleep_interruptibly(self.config.mouse_sleep)

        x, y = self._relative_point(0.05, 0.41)
        self._raise_if_stop_requested()
        pyautogui.moveTo(x, y)
        pyautogui.click()
        self.scan_phase = "top"
        self.logger.info("已进入神秘商店页面。")

    def capture_screen(self):
        self._raise_if_stop_requested()
        if self.hwnd is None:
            raise RuntimeError("窗口尚未初始化。")
        return window_capture_service.capture_client(self.hwnd)

    def _capture_screen_frame(self) -> tuple[np.ndarray, int]:
        self._raise_if_stop_requested()
        if self.hwnd is None:
            raise RuntimeError("Window has not been initialized.")
        return window_capture_service.capture_client_frame(self.hwnd)

    def _capture_screen_after_frame(
        self,
        previous_frame_seq: int,
        timeout_seconds: float = 2.0,
    ) -> tuple[np.ndarray, int]:
        self._raise_if_stop_requested()
        if self.hwnd is None:
            raise RuntimeError("Window has not been initialized.")
        deadline = time.monotonic() + timeout_seconds
        while True:
            self._raise_if_stop_requested()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Timed out waiting for a fresh window frame.")
            try:
                return window_capture_service.capture_client_after_frame(
                    self.hwnd,
                    previous_frame_seq,
                    min(0.1, remaining),
                )
            except RuntimeError as exc:
                if "fresh window frame" not in str(exc):
                    raise

    def _capture_changed_screen_after_frame(
        self,
        before_image: np.ndarray,
        previous_frame_seq: int,
        threshold: float,
        timeout_seconds: float,
    ) -> tuple[np.ndarray, int, float]:
        deadline = time.monotonic() + timeout_seconds
        last_frame_seq = previous_frame_seq
        best_image: np.ndarray | None = None
        best_frame_seq = previous_frame_seq
        best_diff = -1.0

        while True:
            self._raise_if_stop_requested()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            try:
                image, frame_seq = self._capture_screen_after_frame(
                    last_frame_seq,
                    min(FRESH_FRAME_POLL_SECONDS, remaining),
                )
            except RuntimeError:
                break

            gray_diff = self._gray_mean_diff(before_image, image)
            if gray_diff > best_diff:
                best_image = image
                best_frame_seq = frame_seq
                best_diff = gray_diff
            if gray_diff >= threshold:
                return image, frame_seq, gray_diff
            last_frame_seq = frame_seq

        if best_image is None:
            image, frame_seq = self._capture_screen_after_frame(
                previous_frame_seq,
                timeout_seconds,
            )
            return image, frame_seq, self._gray_mean_diff(before_image, image)

        return best_image, best_frame_seq, best_diff

    def cleanup(self) -> None:
        window_capture_service.stop()

    def validate_top_prices(self, screen_image) -> bool:
        self._raise_if_stop_requested()
        original_phase = self.scan_phase
        self.scan_phase = "top"
        try:
            recognized = self._scan_price_slots(screen_image)
        finally:
            self.scan_phase = original_phase
        self._raise_if_stop_requested()

        prices_by_key = {
            item.slot.key: item.price
            for item in recognized
            if item.slot.phase == "top"
        }
        return all(
            len(prices_by_key.get(f"item_{index}", "")) > 4
            for index in range(1, 5)
        )

    def find_item_position(self, screen_image, template) -> PurchaseTarget | None:
        self._raise_if_stop_requested()
        target_price = str(template)
        for recognized in self._scan_price_slots(screen_image):
            self._raise_if_stop_requested()
            if recognized.price == target_price:
                return PurchaseTarget(
                    slot=recognized.slot,
                    price=recognized.price,
                    buy_position=self._scaled_random_point(
                        recognized.slot.buy_x_range,
                        recognized.slot.buy_y_range,
                    ),
                )
        return None

    def buy_item(self, target: PurchaseTarget) -> None:
        last_reason = "未知错误"
        for attempt in range(1, BUY_RETRY_LIMIT + 1):
            self._raise_if_stop_requested()
            before_image, before_frame_seq = self._capture_screen_frame()
            before_button = self._crop_buy_button(before_image, target.slot)
            before_text = price_ocr_service.recognize_text(before_button)
            self._raise_if_stop_requested()
            self.logger.info(
                "购买前按钮 OCR：%s 为“%s”。",
                target.slot.key,
                before_text or "空",
            )
            if "1/1" not in before_text:
                last_reason = f"{target.slot.key} 购买前按钮未识别到 1/1"
                self._log_retry_and_recover(last_reason, attempt, before_image, before_button)
                continue

            x, y = target.buy_position
            self._raise_if_stop_requested()
            pyautogui.moveTo(x, y)
            pyautogui.click(clicks=2, interval=self.config.mouse_sleep)
            self._sleep_interruptibly(self.config.mouse_sleep)

            try:
                after_buy_image, after_buy_frame_seq, gray_diff = self._capture_changed_screen_after_frame(
                    before_image,
                    before_frame_seq,
                    GRAY_MEAN_DIFF_THRESHOLD,
                    POST_BUY_CHANGE_TIMEOUT_SECONDS,
                )
            except RuntimeError as exc:
                last_reason = f"点击购买后未获取到新截图：{exc}"
                self._log_retry_and_recover(
                    last_reason,
                    attempt,
                    before_image,
                    before_button,
                )
                continue
            self.logger.info(
                "购买点击前后截图帧号：%s -> %s。",
                before_frame_seq,
                after_buy_frame_seq,
            )
            self.logger.info("点击购买后灰度均值差：%.2f。", gray_diff)
            if gray_diff < GRAY_MEAN_DIFF_THRESHOLD:
                last_reason = (
                    f"点击购买后画面灰度变化不足 "
                    f"({gray_diff:.2f} < {GRAY_MEAN_DIFF_THRESHOLD:.2f})"
                )
                self._log_retry_and_recover(
                    last_reason,
                    attempt,
                    before_image,
                    before_button,
                    after_buy_image,
                )
                continue

            x, y = self._scaled_random_point((1000, 1275), (740, 790))
            self._raise_if_stop_requested()
            pyautogui.moveTo(x, y)
            pyautogui.click(clicks=2, interval=self.config.mouse_sleep)
            self._sleep_interruptibly(POST_CONFIRM_VERIFY_WAIT_SECONDS)

            after_confirm_image, after_confirm_frame_seq = self._capture_screen_after_frame(
                after_buy_frame_seq,
            )
            self.logger.info(
                "确认点击前后截图帧号：%s -> %s。",
                after_buy_frame_seq,
                after_confirm_frame_seq,
            )
            after_confirm_button = self._crop_buy_button(after_confirm_image, target.slot)
            after_confirm_text = price_ocr_service.recognize_text(after_confirm_button)
            self.logger.info(
                "确认购买后按钮 OCR：%s 为“%s”。",
                target.slot.key,
                after_confirm_text or "空",
            )
            if "0/1" in after_confirm_text:
                return

            last_reason = f"{target.slot.key} 确认购买后未识别到 0/1"
            self._log_retry_and_recover(
                last_reason,
                attempt,
                after_confirm_image,
                after_confirm_button,
            )

        raise RuntimeError(f"购买失败，已重试 {BUY_RETRY_LIMIT} 次：{last_reason}")

    def scroll_shop(self) -> None:
        self._raise_if_stop_requested()
        # Keep the stable vertical swipe used by the original mouse flow:
        # start around 65% of the client height and move upward by 27.7%.
        # A larger diagonal swipe can overscroll the list or fail to expose
        # item 5 and item 6 consistently on different emulator sizes.
        x, start_y = self._relative_point(0.58, 0.65)
        _, end_y = self._relative_point(0.58, 0.65 - 0.277)
        self._raise_if_stop_requested()
        pyautogui.moveTo(x, start_y)
        self._sleep_interruptibly(0.05)
        pyautogui.mouseDown(button="left")
        try:
            self._sleep_interruptibly(0.05)
            pyautogui.moveTo(x, end_y)
            self._sleep_interruptibly(0.05)
        finally:
            pyautogui.mouseUp(button="left")
        self._sleep_interruptibly(0.05)
        self.scan_phase = "bottom"
        self._clear_price_cache()
        self.logger.info("已向上滑动商店，将固定等待 1 秒后识别 item_5 和 item_6。")

    def refresh_shop(self) -> None:
        self._raise_if_stop_requested()
        x, y = self._relative_point(0.20, 0.90)
        pyautogui.moveTo(x, y)
        pyautogui.click(clicks=2, interval=self.config.mouse_sleep)
        self._sleep_interruptibly(self.config.mouse_sleep)

        self._raise_if_stop_requested()
        x, y = self._relative_point(0.58, 0.65)
        pyautogui.moveTo(x, y)
        pyautogui.click(clicks=2, interval=self.config.mouse_sleep)
        self._sleep_interruptibly(self.config.screenshot_sleep)
        self.scan_phase = "top"
        self._clear_price_cache()

    def click_screen_center(self) -> None:
        self._raise_if_stop_requested()
        x, y = self._relative_point(0.5, 0.5)
        pyautogui.moveTo(x, y)
        pyautogui.click()

    def save_debug_screenshot(self, reason: str, image) -> str:
        return str(self._save_debug_images(reason, image))

    def _activate_window(self) -> None:
        try:
            self.window.activate()
        except Exception:
            # Some emulators refuse activation intermittently; the original script tolerated this.
            pass

    def _log_retry_and_recover(
        self,
        reason: str,
        attempt: int,
        full_image: np.ndarray,
        button_image: np.ndarray,
        after_image: np.ndarray | None = None,
    ) -> None:
        debug_dir = self._save_debug_images(reason, full_image, button_image, after_image)
        if attempt >= BUY_RETRY_LIMIT:
            self.logger.error(
                "%s，第 %s/%s 次尝试失败，异常截图目录：%s。",
                reason,
                attempt,
                BUY_RETRY_LIMIT,
                debug_dir,
            )
            return

        self.logger.warning(
            "%s，第 %s/%s 次尝试失败，异常截图目录：%s。等待 %.0f 秒后点击屏幕中心并重试。",
            reason,
            attempt,
            BUY_RETRY_LIMIT,
            debug_dir,
            RECOVERY_WAIT_SECONDS,
        )
        self._sleep_interruptibly(RECOVERY_WAIT_SECONDS)
        self.click_screen_center()

    def _save_debug_images(
        self,
        reason: str,
        full_image: np.ndarray,
        button_image: np.ndarray | None = None,
        after_image: np.ndarray | None = None,
    ) -> Path:
        self._save_latest_price_regions(full_image, self.scan_phase)
        return DEBUG_CAPTURE_DIR

    def _save_latest_price_regions(self, screen_image: np.ndarray, phase: str) -> Path:
        DEBUG_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        self._clear_stale_debug_captures()
        for slot in PRICE_SLOTS:
            if slot.phase != phase:
                continue
            self._write_rgb_image(
                DEBUG_CAPTURE_DIR / f"{slot.key}.png",
                self._crop_price_region(screen_image, slot),
            )
        return DEBUG_CAPTURE_DIR

    @staticmethod
    def _clear_stale_debug_captures() -> None:
        if not DEBUG_CAPTURE_DIR.exists():
            return
        for path in DEBUG_CAPTURE_DIR.iterdir():
            if path.is_file() and path.name in DEBUG_PRICE_REGION_FILES:
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    @staticmethod
    def _write_rgb_image(path: Path, image: np.ndarray) -> None:
        cv2.imwrite(str(path), cv2.cvtColor(image, cv2.COLOR_RGB2BGR))

    @staticmethod
    def _gray_mean_diff(before_image: np.ndarray, after_image: np.ndarray) -> float:
        if before_image.shape[:2] != after_image.shape[:2]:
            after_image = cv2.resize(
                after_image,
                (before_image.shape[1], before_image.shape[0]),
                interpolation=cv2.INTER_AREA,
            )
        before_gray = cv2.cvtColor(before_image, cv2.COLOR_RGB2GRAY)
        after_gray = cv2.cvtColor(after_image, cv2.COLOR_RGB2GRAY)
        return float(abs(before_gray.mean() - after_gray.mean()))

    @staticmethod
    def _crop_price_region(screen_image: np.ndarray, slot: PriceSlot) -> np.ndarray:
        height, width = screen_image.shape[:2]
        scale_x = width / BASE_WIDTH
        scale_y = height / BASE_HEIGHT
        left = max(0, min(round(slot.crop[0] * scale_x), width))
        top = max(0, min(round(slot.crop[1] * scale_y), height))
        right = max(left + 1, min(round(slot.crop[2] * scale_x), width))
        bottom = max(top + 1, min(round(slot.crop[3] * scale_y), height))
        return screen_image[top:bottom, left:right].copy()

    @staticmethod
    def _crop_buy_button(screen_image: np.ndarray, slot: PriceSlot) -> np.ndarray:
        height, width = screen_image.shape[:2]
        scale_x = width / BASE_WIDTH
        scale_y = height / BASE_HEIGHT
        left = max(0, min(round(slot.buy_x_range[0] * scale_x), width))
        right = max(left + 1, min(round(slot.buy_x_range[1] * scale_x), width))
        top = max(0, min(round(slot.buy_y_range[0] * scale_y), height))
        bottom = max(top + 1, min(round(slot.buy_y_range[1] * scale_y), height))
        return screen_image[top:bottom, left:right].copy()

    def _scan_price_slots(self, screen_image):
        if self._price_cache_image is not screen_image or self._price_cache_phase != self.scan_phase:
            scale_x = screen_image.shape[1] / BASE_WIDTH
            scale_y = screen_image.shape[0] / BASE_HEIGHT
            self._save_latest_price_regions(screen_image, self.scan_phase)
            self._price_cache = price_ocr_service.scan_prices(screen_image, self.scan_phase, scale_x, scale_y)
            self._price_cache_image = screen_image
            self._price_cache_phase = self.scan_phase
            self._log_price_scan_result()
        return self._price_cache

    def _log_price_scan_result(self) -> None:
        recognized_by_key = {
            recognized.slot.key: recognized.price
            for recognized in self._price_cache
        }
        phase_slots = [
            slot
            for slot in PRICE_SLOTS
            if slot.phase == self.scan_phase
        ]
        for slot in phase_slots:
            price = recognized_by_key.get(slot.key)
            if price:
                self.logger.info("OCR 识别成功：%s 价格为 %s", slot.key, price)
            else:
                self.logger.warning(
                    "OCR 识别失败：%s 未识别到有效价格。",
                    slot.key,
                )

        if self.scan_phase == "bottom":
            success_count = sum(
                slot.key in recognized_by_key
                for slot in phase_slots
            )
            self.logger.info(
                "底部识别完成：item_5/item_6 成功 %s 个，失败 %s 个。",
                success_count,
                len(phase_slots) - success_count,
            )

    def _clear_price_cache(self) -> None:
        self._price_cache_phase = None
        self._price_cache_image = None
        self._price_cache = []

    def _scaled_random_point(
        self,
        x_range: tuple[int, int],
        y_range: tuple[int, int],
    ) -> tuple[float, float]:
        return self._scaled_point(
            random.randint(*x_range),
            random.randint(*y_range),
        )

    def _scaled_point(self, x: float, y: float) -> tuple[float, float]:
        if self.hwnd is None:
            raise RuntimeError("窗口尚未初始化。")
        client_left, client_top, client_width, client_height = (
            window_capture_service.get_client_bounds(self.hwnd)
        )
        return (
            client_left + x * client_width / BASE_WIDTH,
            client_top + y * client_height / BASE_HEIGHT,
        )

    def _relative_point(self, x_ratio: float, y_ratio: float) -> tuple[float, float]:
        return self._scaled_point(BASE_WIDTH * x_ratio, BASE_HEIGHT * y_ratio)
