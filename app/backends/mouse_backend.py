from __future__ import annotations

import random
import time

import numpy as np
import pyautogui
import pygetwindow as gw
from PIL import ImageGrab

from app.backends.base import BaseBackend
from app.core.constants import ITEM_DEFINITIONS
from app.services.price_ocr_service import BASE_HEIGHT, BASE_WIDTH, price_ocr_service


class MouseBackend(BaseBackend):
    def __init__(self, config, logger):
        super().__init__(config, logger)
        self.window = None
        self.scan_phase = "top"
        self._price_cache_phase: str | None = None
        self._price_cache_image = None
        self._price_cache = []

    @property
    def page_settle_delay(self) -> float:
        return max(0.7 + self.config.screenshot_sleep, 1.0)

    @property
    def scroll_settle_delay(self) -> float:
        return max(0.3, self.config.screenshot_sleep)

    def prepare(self) -> None:
        price_ocr_service.ensure_ready()

        title = self.config.mouse_window_title.strip()
        if not title:
            raise RuntimeError("请选择或输入模拟器窗口标题。")

        windows = gw.getWindowsWithTitle(title)
        self.window = next((window for window in windows if window.title == title), None)
        if self.window is None:
            raise RuntimeError(f'未找到窗口标题为“{title}”的模拟器。')

        try:
            if self.window.isMaximized or self.window.isMinimized:
                self.window.restore()
            if self.config.auto_move_window:
                self.window.moveTo(0, 0)
            self.window.resizeTo(906, 539)
            self._activate_window()
            self.logger.info("已连接鼠标模式窗口：%s", title)
        except Exception as exc:  # pragma: no cover - pygetwindow depends on host environment
            raise RuntimeError(f"初始化模拟器窗口失败：{exc}") from exc

    def load_template(self, file_name: str):
        for item in ITEM_DEFINITIONS:
            if item.file_name == file_name:
                return str(item.price)
        raise RuntimeError(f"未找到物品价格定义：{file_name}")

    def open_shop(self) -> None:
        self._activate_window()

        x = self.window.left + self.window.width * 0.05
        y = self.window.top + self.window.height * 0.41
        pyautogui.moveTo(x, y)
        pyautogui.click()
        time.sleep(self.config.mouse_sleep)

        x = self.window.left + self.window.width * 0.44
        y = self.window.top + self.window.height * 0.26
        pyautogui.moveTo(x, y)
        pyautogui.click()
        time.sleep(self.config.mouse_sleep)

        x = self.window.left + self.window.width * 0.05
        y = self.window.top + self.window.height * 0.41
        pyautogui.moveTo(x, y)
        pyautogui.click()
        self.scan_phase = "top"
        self.logger.info("已进入神秘商店页面。")

    def capture_screen(self):
        self._activate_window()
        region = [self.window.left, self.window.top, self.window.width, self.window.height]
        screenshot = ImageGrab.grab(
            bbox=(region[0], region[1], region[2] + region[0], region[3] + region[1]),
            all_screens=True,
        )
        return np.array(screenshot)

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
        x1, y1 = self._scaled_point(
            1050 + random.randint(-50, 50),
            500 + random.randint(-50, 50),
        )
        x2, y2 = self._scaled_point(
            1250 + random.randint(-50, 50),
            50 + random.randint(-50, 50),
        )
        pyautogui.moveTo(x1, y1)
        time.sleep(0.05)
        pyautogui.mouseDown(button="left")
        time.sleep(0.05)
        pyautogui.moveTo(x2, y2)
        time.sleep(0.05)
        pyautogui.mouseUp(button="left")
        time.sleep(0.05)
        self.scan_phase = "bottom"

    def refresh_shop(self) -> None:
        x = self.window.left + self.window.width * 0.20
        y = self.window.top + self.window.height * 0.90
        pyautogui.moveTo(x, y)
        pyautogui.click(clicks=2, interval=self.config.mouse_sleep)
        time.sleep(self.config.mouse_sleep)

        x = self.window.left + self.window.width * 0.58
        y = self.window.top + self.window.height * 0.65
        pyautogui.moveTo(x, y)
        pyautogui.click(clicks=2, interval=self.config.mouse_sleep)
        time.sleep(self.config.screenshot_sleep)
        self.scan_phase = "top"

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
            for recognized in self._price_cache:
                self.logger.info("OCR 识别到 %s 价格：%s", recognized.slot.key, recognized.price)
        return self._price_cache

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
        return (
            self.window.left + x * self.window.width / BASE_WIDTH,
            self.window.top + y * self.window.height / BASE_HEIGHT,
        )
