from __future__ import annotations

import random
import time

import pyautogui
import pygetwindow as gw

from app.backends.base import BaseBackend
from app.core.constants import ITEM_DEFINITIONS
from app.services.price_ocr_service import (
    BASE_HEIGHT,
    BASE_WIDTH,
    PRICE_SLOTS,
    price_ocr_service,
)
from app.services.window_capture_service import window_capture_service


class MouseBackend(BaseBackend):
    def __init__(self, config, logger):
        super().__init__(config, logger)
        self.window = None
        self.hwnd: int | None = None
        self.scan_phase = "top"
        self._price_cache_phase: str | None = None
        self._price_cache_image = None
        self._price_cache = []

    @property
    def page_settle_delay(self) -> float:
        return max(0.7 + self.config.screenshot_sleep, 1.0)

    @property
    def scroll_settle_delay(self) -> float:
        return 1.0

    def prepare(self) -> None:
        price_ocr_service.ensure_ready()

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
        self._activate_window()

        x, y = self._relative_point(0.05, 0.41)
        pyautogui.moveTo(x, y)
        pyautogui.click()
        time.sleep(self.config.mouse_sleep)

        x, y = self._relative_point(0.44, 0.26)
        pyautogui.moveTo(x, y)
        pyautogui.click()
        time.sleep(self.config.mouse_sleep)

        x, y = self._relative_point(0.05, 0.41)
        pyautogui.moveTo(x, y)
        pyautogui.click()
        self.scan_phase = "top"
        self.logger.info("已进入神秘商店页面。")

    def capture_screen(self):
        if self.hwnd is None:
            raise RuntimeError("窗口尚未初始化。")
        return window_capture_service.capture_client(self.hwnd)

    def cleanup(self) -> None:
        window_capture_service.stop()

    def find_item_position(self, screen_image, template) -> tuple[float, float] | None:
        target_price = str(template)
        for recognized in self._scan_price_slots(screen_image):
            if recognized.price == target_price:
                return self._scaled_random_point(recognized.slot.buy_x_range, recognized.slot.buy_y_range)
        return None

    def buy_item(self, position: tuple[float, float]) -> None:
        x, y = position
        pyautogui.moveTo(x, y)
        pyautogui.click(clicks=2, interval=self.config.mouse_sleep)
        time.sleep(self.config.mouse_sleep)

        x, y = self._scaled_random_point((1000, 1275), (740, 790))
        pyautogui.moveTo(x, y)
        pyautogui.click(clicks=2, interval=self.config.mouse_sleep)
        time.sleep(self.config.mouse_sleep)
        time.sleep(self.config.screenshot_sleep)

    def scroll_shop(self) -> None:
        # Keep the stable vertical swipe used by the original mouse flow:
        # start around 65% of the client height and move upward by 27.7%.
        # A larger diagonal swipe can overscroll the list or fail to expose
        # item 5 and item 6 consistently on different emulator sizes.
        x, start_y = self._relative_point(0.58, 0.65)
        _, end_y = self._relative_point(0.58, 0.65 - 0.277)
        pyautogui.moveTo(x, start_y)
        time.sleep(0.05)
        pyautogui.mouseDown(button="left")
        time.sleep(0.05)
        pyautogui.moveTo(x, end_y)
        time.sleep(0.05)
        pyautogui.mouseUp(button="left")
        time.sleep(0.05)
        self.scan_phase = "bottom"
        self._clear_price_cache()
        self.logger.info("已向上滑动商店，将固定等待 1 秒后识别 item_5 和 item_6。")

    def refresh_shop(self) -> None:
        x, y = self._relative_point(0.20, 0.90)
        pyautogui.moveTo(x, y)
        pyautogui.click(clicks=2, interval=self.config.mouse_sleep)
        time.sleep(self.config.mouse_sleep)

        x, y = self._relative_point(0.58, 0.65)
        pyautogui.moveTo(x, y)
        pyautogui.click(clicks=2, interval=self.config.mouse_sleep)
        time.sleep(self.config.screenshot_sleep)
        self.scan_phase = "top"
        self._clear_price_cache()

    def _activate_window(self) -> None:
        try:
            self.window.activate()
        except Exception:
            # Some emulators refuse activation intermittently; the original script tolerated this.
            pass

    def _scan_price_slots(self, screen_image):
        if self._price_cache_image is not screen_image or self._price_cache_phase != self.scan_phase:
            scale_x = screen_image.shape[1] / BASE_WIDTH
            scale_y = screen_image.shape[0] / BASE_HEIGHT
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
