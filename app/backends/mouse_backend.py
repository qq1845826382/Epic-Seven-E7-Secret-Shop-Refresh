from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui
import pygetwindow as gw
from PIL import ImageGrab

from app.backends.base import BaseBackend
from app.core.constants import ASSETS_DIR


class MouseBackend(BaseBackend):
    def __init__(self, config, logger):
        super().__init__(config, logger)
        self.window = None

    @property
    def page_settle_delay(self) -> float:
        return max(0.7 + self.config.screenshot_sleep, 1.0)

    @property
    def scroll_settle_delay(self) -> float:
        return max(0.3, self.config.screenshot_sleep)

    def prepare(self) -> None:
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
        path = Path(ASSETS_DIR) / file_name
        image = cv2.imread(str(path))
        if image is None:
            raise RuntimeError(f"无法读取模板图片：{path}")
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

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
        result = cv2.matchTemplate(screen_image, template, cv2.TM_CCOEFF_NORMED)
        loc = np.where(result >= 0.70)
        if loc[0].size > 0:
            x = self.window.left + self.window.width * 0.90
            y = self.window.top + loc[0][0] + self.window.height * 0.085
            return x, y
        return None

    def buy_item(self, position: tuple[float, float]) -> None:
        x, y = position
        pyautogui.moveTo(x, y)
        pyautogui.click(clicks=2, interval=self.config.mouse_sleep)
        time.sleep(self.config.mouse_sleep)

        x = self.window.left + self.window.width * 0.55
        y = self.window.top + self.window.height * 0.70
        pyautogui.moveTo(x, y)
        pyautogui.click(clicks=2, interval=self.config.mouse_sleep)
        time.sleep(self.config.mouse_sleep)
        time.sleep(self.config.screenshot_sleep)

    def scroll_shop(self) -> None:
        x = self.window.left + self.window.width * 0.58
        y = self.window.top + self.window.height * 0.65
        pyautogui.moveTo(x, y)
        time.sleep(0.05)
        pyautogui.mouseDown(button="left")
        time.sleep(0.05)
        pyautogui.moveTo(x, y - self.window.height * 0.277)
        time.sleep(0.05)
        pyautogui.mouseUp(button="left")
        time.sleep(0.05)

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

    def _activate_window(self) -> None:
        try:
            self.window.activate()
        except Exception:
            # Some emulators refuse activation intermittently; the original script tolerated this.
            pass
