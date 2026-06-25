from __future__ import annotations

import random
import time

import numpy as np
import pyautogui
import pygetwindow as gw
from PIL import ImageGrab

from app.backends.base import BaseBackend
from app.core.constants import ASSETS_DIR, ITEM_DEFINITIONS
from app.services.price_ocr_service import BASE_HEIGHT, BASE_WIDTH, price_ocr_service
from app.services.shop_flow_vision import (
    CONFIRM_BUTTON_POINT,
    FIRST_SHOP_ITEM_MARKER_COLOR,
    FIRST_SHOP_ITEM_MARKER_POINT,
    PendingPurchase,
    PURCHASE_DIALOG_ITEM_REGION,
    PurchaseTarget,
    REWARD_TOAST_ITEM_REGION,
    SCREEN_CENTER_POINT,
    SHOP_REFRESH_BUTTON_POINT,
    SHOP_REFRESH_CONFIRM_POINT,
    color_region_matches,
    match_item_icon,
    scale_point,
)


class MouseBackend(BaseBackend):
    def __init__(self, config, logger):
        super().__init__(config, logger)
        self.window = None
        self.scan_phase = "top"
        self._price_cache_phase: str | None = None
        self._price_cache_image = None
        self._price_cache = []
        # 价格命中后保存目标商品，buy_item() 再用它做购买弹窗和顶部获得提示复核。
        self.pending_purchase: PendingPurchase | None = None

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
        # 保持 BaseBackend 接口不变，但这里传递的是目标物品元数据而不是图像模板。
        for item in ITEM_DEFINITIONS:
            if item.file_name == file_name:
                return PurchaseTarget(
                    key=item.key,
                    file_name=item.file_name,
                    display_name=item.display_name,
                    price=str(item.price),
                )
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
        target: PurchaseTarget = template
        for recognized in self._scan_price_slots(screen_image):
            if recognized.price == target.price:
                position = self._scaled_random_point(recognized.slot.buy_x_range, recognized.slot.buy_y_range)
                # 记录当前命中的商品，供 buy_item() 判断弹窗和顶部提示是否是同一商品。
                self.pending_purchase = PendingPurchase(target=target, position=position, phase=self.scan_phase)
                return position
        return None

    def buy_item(self, position: tuple[float, float]) -> None:
        pending = self.pending_purchase
        if pending is None:
            raise RuntimeError("缺少待购买商品上下文，无法执行购买确认。")

        # 购买弹窗确认：点击购买后等待弹窗内出现同一商品图标，成功后才点击确认。
        # 如果这里抛出异常，RefreshEngine 不会执行购买计数。
        for attempt in range(1, 4):
            self._click_exact(position, clicks=2)
            time.sleep(self.config.mouse_sleep)
            if self._wait_for_item_icon(pending.target, PURCHASE_DIALOG_ITEM_REGION, timeout=5.0, interval=0.3):
                self._click_flow_point(CONFIRM_BUTTON_POINT)
                time.sleep(self.config.mouse_sleep)
                self._wait_after_confirm(pending.target)
                self.pending_purchase = None
                return
            self.logger.warning("购买确认弹窗未识别到 %s，第 %s/3 次重试。", pending.target.display_name, attempt)
            self._click_flow_point(SCREEN_CENTER_POINT)
            time.sleep(self.config.mouse_sleep)
        raise RuntimeError("购买确认弹窗未识别到目标商品，已终止。")

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
        # 商店刷新确认：刷新按钮、确认按钮和加载完成点都来自 1280x720 参考坐标，
        # _click_flow_point() 会把它们缩放到当前模拟器窗口。
        self._click_flow_point(SHOP_REFRESH_BUTTON_POINT)
        time.sleep(self.config.mouse_sleep)

        self._click_flow_point(SHOP_REFRESH_CONFIRM_POINT)
        time.sleep(self.config.screenshot_sleep)
        self._wait_for_first_item_after_refresh()
        time.sleep(1.0)
        self.scan_phase = "top"

    def _activate_window(self) -> None:
        try:
            self.window.activate()
        except Exception:
            # Some emulators refuse activation intermittently; the original script tolerated this.
            pass

    def _scan_price_slots(self, screen_image):
        # 一张截图会被多个已选物品复用，OCR 结果按截图对象和扫描阶段缓存。
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
        # 价格 OCR 的坐标基准是 1920x1080，因此这里和购买复核流程的 1280x720 缩放不同。
        return (
            self.window.left + x * self.window.width / BASE_WIDTH,
            self.window.top + y * self.window.height / BASE_HEIGHT,
        )

    def _wait_after_confirm(self, target: PurchaseTarget) -> None:
        # 顶部获得提示确认：确认后等待顶部区域出现同一商品图标，成功后额外等待 1.5 秒。
        for attempt in range(1, 4):
            if self._wait_for_item_icon(target, REWARD_TOAST_ITEM_REGION, timeout=5.0, interval=0.1):
                time.sleep(1.5)
                return
            self.logger.warning("确认购买后顶部未识别到 %s，第 %s/3 次重试。", target.display_name, attempt)
            self._click_flow_point(SCREEN_CENTER_POINT)
            time.sleep(self.config.mouse_sleep)
            self._click_flow_point(CONFIRM_BUTTON_POINT)
            time.sleep(self.config.mouse_sleep)
        raise RuntimeError("确认购买后顶部商品提示未出现，已终止。")

    def _wait_for_item_icon(
        self,
        target: PurchaseTarget,
        region: tuple[int, int, int, int],
        timeout: float,
        interval: float,
    ) -> bool:
        """在当前窗口截图中等待目标商品图标出现。"""

        deadline = time.time() + timeout
        template_path = ASSETS_DIR / target.file_name
        while time.time() <= deadline:
            screenshot = self.capture_screen()
            if match_item_icon(screenshot, template_path, region, color_order="rgb"):
                return True
            time.sleep(interval)
        return False

    def _wait_for_first_item_after_refresh(self) -> None:
        """刷新后等待首个商品行的蓝色标记出现。"""

        deadline = time.time() + 10.0
        while time.time() <= deadline:
            screenshot = self.capture_screen()
            if color_region_matches(
                screenshot,
                FIRST_SHOP_ITEM_MARKER_POINT,
                FIRST_SHOP_ITEM_MARKER_COLOR,
                color_order="rgb",
            ):
                return
            time.sleep(0.2)
        raise RuntimeError("刷新后未检测到首个商品，已终止。")

    def _click_flow_point(self, point: tuple[int, int]) -> None:
        # 将 1280x720 参考点缩放到桌面窗口的绝对屏幕坐标。
        self._click_exact(
            scale_point(
                point,
                self.window.width,
                self.window.height,
                origin=(self.window.left, self.window.top),
            )
        )

    def _click_exact(self, position: tuple[float, float], clicks: int = 1) -> None:
        pyautogui.moveTo(*position)
        pyautogui.click(clicks=clicks, interval=self.config.mouse_sleep)
