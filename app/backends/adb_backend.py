from __future__ import annotations

import random
import subprocess
import time
from io import BytesIO

import cv2
import numpy as np
from PIL import Image

from app.backends.base import BaseBackend
from app.core.constants import (
    ADB_ASSETS_DIR,
    ADB_EXECUTABLE,
    ITEM_DEFINITIONS,
    SUPPORTED_ADB_HEIGHT,
    SUPPORTED_ADB_WIDTH,
)
from app.services.adb_service import ADBService
from app.services.price_ocr_service import price_ocr_service
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


class ADBBackend(BaseBackend):
    def __init__(self, config, logger):
        super().__init__(config, logger)
        self.adb_service = ADBService(ADB_EXECUTABLE)
        self.device_id = ""
        self.screenwidth = SUPPORTED_ADB_WIDTH
        self.screenheight = SUPPORTED_ADB_HEIGHT
        self.x_offset = 75 if self.config.adb_random_offset else 0
        self.y_offset = 25 if self.config.adb_random_offset else 0
        self.scan_phase = "top"
        self._price_cache_phase: str | None = None
        self._price_cache_image = None
        self._price_cache = []
        # find_item_position() 只负责找到“应该买哪一行”。
        # buy_item() 需要知道这行对应的商品，才能复核购买弹窗和顶部获得提示。
        self.pending_purchase: PendingPurchase | None = None

    @property
    def page_settle_delay(self) -> float:
        return 1.5

    @property
    def scroll_settle_delay(self) -> float:
        return 1.0

    def prepare(self) -> None:
        price_ocr_service.ensure_ready()

        if self.config.adb_manual_address.strip():
            success, message = self.adb_service.connect_device(self.config.adb_manual_address.strip())
            self.logger.info(message or "ADB 连接命令已执行。")
            if not success:
                raise RuntimeError("ADB 地址连接失败，请检查模拟器调试开关和地址。")

        devices = self.adb_service.list_devices()
        if not devices:
            raise RuntimeError("当前没有检测到任何 ADB 设备。")

        if self.config.adb_device_id:
            if self.config.adb_device_id not in devices:
                raise RuntimeError("所选 ADB 设备当前不可用，请重新刷新设备列表。")
            self.device_id = self.config.adb_device_id
        elif len(devices) == 1:
            self.device_id = devices[0]
        else:
            raise RuntimeError("检测到多个 ADB 设备，请先在界面中明确选择一个设备。")

        self._check_screen_dimension()
        self.logger.info("已连接 ADB 设备：%s", self.device_id)

    def load_template(self, file_name: str):
        # RefreshEngine 仍叫它 template，但现在传递的是目标物品元数据：
        # 价格用于 OCR 命中，文件名用于后续弹窗和顶部提示的图标复核。
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
        self._tap(self.screenwidth * 0.0411, self.screenheight * 0.3835, fixed=True)
        time.sleep(0.5)
        self._tap(self.screenwidth * 0.4406, self.screenheight * 0.2462, fixed=True)
        time.sleep(0.5)
        self._tap(self.screenwidth * 0.0411, self.screenheight * 0.3835, fixed=True)
        time.sleep(0.5)
        self.scan_phase = "top"
        self.logger.info("已进入神秘商店页面。")

    def capture_screen(self):
        completed = self._run_adb(["exec-out", "screencap", "-p"], capture_output=True)
        img_array = np.frombuffer(completed.stdout, dtype=np.uint8)
        screenshot = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
        if screenshot is None:
            raise RuntimeError("ADB 截图失败。")
        return screenshot

    def find_item_position(self, screen_image, template) -> tuple[float, float] | None:
        target: PurchaseTarget = template
        for recognized in self._scan_price_slots(screen_image):
            if recognized.price == target.price:
                slot = recognized.slot
                position = (
                    random.randint(*slot.buy_x_range),
                    random.randint(*slot.buy_y_range),
                )
                # 保存购买上下文。引擎随后会调用 buy_item(position)，此处不能直接点击，
                # 否则会改变原始购买统计的触发时机。
                self.pending_purchase = PendingPurchase(target=target, position=position, phase=self.scan_phase)
                return position
        return None

    def buy_item(self, position: tuple[float, float]) -> None:
        pending = self.pending_purchase
        if pending is None:
            raise RuntimeError("缺少待购买商品上下文，无法执行购买确认。")

        # 购买弹窗确认：先点击商品行购买按钮，再确认弹窗中确实出现了同一商品图标。
        # 顶部获得提示确认也成功后，buy_item() 才返回，原引擎才会计数。
        for attempt in range(1, 4):
            self._tap_exact(position)
            self._tap_exact(position)
            time.sleep(self.config.adb_tap_sleep)
            if self._wait_for_item_icon(pending.target, PURCHASE_DIALOG_ITEM_REGION, timeout=5.0, interval=0.3):
                self._tap_flow_point(CONFIRM_BUTTON_POINT)
                time.sleep(self.config.adb_tap_sleep)
                self._wait_after_confirm(pending.target)
                self.pending_purchase = None
                return
            self.logger.warning("购买确认弹窗未识别到 %s，第 %s/3 次重试。", pending.target.display_name, attempt)
            self._tap_flow_point(SCREEN_CENTER_POINT)
            time.sleep(self.config.adb_tap_sleep)
        raise RuntimeError("购买确认弹窗未识别到目标商品，已终止。")

    def scroll_shop(self) -> None:
        x1 = 1050
        y1 = 500
        x2 = 1250
        y2 = 50
        if self.config.adb_debug:
            self._show_offset_area(x1, y1, "起始滑动区域", "请确认红框位于可滑动区域")
        x1_offset = random.randint(-50, 50)
        y1_offset = random.randint(-50, 50)
        x2_offset = random.randint(-50, 50)
        y2_offset = random.randint(-50, 50)
        self._run_adb(
            [
                "shell",
                "input",
                "swipe",
                str(x1 + x1_offset),
                str(y1 + y1_offset),
                str(x2 + x2_offset),
                str(y2 + y2_offset),
            ]
        )
        self.scan_phase = "bottom"

    def refresh_shop(self) -> None:
        # 商店刷新确认：使用 e7Helper 的刷新坐标，并等待首个商品点出现，避免新一轮过早截图。
        self._tap_flow_point(SHOP_REFRESH_BUTTON_POINT)
        time.sleep(self.config.adb_tap_sleep)
        self._tap_flow_point(SHOP_REFRESH_CONFIRM_POINT)
        time.sleep(self.config.adb_tap_sleep)
        self._wait_for_first_item_after_refresh()
        time.sleep(1.0)
        self.scan_phase = "top"

    def _tap(self, x: float, y: float, fixed: bool = False, prompt: str = "") -> None:
        x_offset, y_offset = (0, 0) if fixed else self._generate_offset()
        if self.config.adb_debug and not fixed:
            self._show_offset_area(x, y, "ADB 调试", prompt)
        self._run_adb(["shell", "input", "tap", str(x + x_offset), str(y + y_offset)])

    def _generate_offset(self) -> tuple[int, int]:
        if not self.config.adb_random_offset:
            return 0, 0
        return (
            random.randint(-self.x_offset, self.x_offset),
            random.randint(-self.y_offset, self.y_offset),
        )

    def _check_screen_dimension(self) -> None:
        completed = self._run_adb(["exec-out", "screencap", "-p"], capture_output=True)
        image_bytes = BytesIO(completed.stdout)
        pil_image = Image.open(image_bytes)
        pil_array = np.array(pil_image)
        height, width = pil_array.shape[:2]
        if (width, height) != (self.screenwidth, self.screenheight):
            raise RuntimeError(
                f"当前设备分辨率为 {width} x {height}，仅支持 {self.screenwidth} x {self.screenheight}。"
            )

    def _run_adb(self, args: list[str], capture_output: bool = False) -> subprocess.CompletedProcess:
        command = [str(ADB_EXECUTABLE)]
        if self.device_id:
            command.extend(["-s", self.device_id])
        completed = subprocess.run(
            command + args,
            stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(stderr or "ADB 命令执行失败。")
        return completed

    def _capture_color_screen(self):
        # 价格 OCR 用灰度图即可；图标模板和颜色点判定需要保留颜色通道。
        completed = self._run_adb(["exec-out", "screencap", "-p"], capture_output=True)
        img_array = np.frombuffer(completed.stdout, dtype=np.uint8)
        screenshot = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if screenshot is None:
            raise RuntimeError("ADB 截图失败。")
        return screenshot

    def _scan_price_slots(self, screen_image):
        # 同一张截图里，RefreshEngine 会按选择物品逐个调用 find_item_position()。
        # 缓存 OCR 结果可以避免对同一组价格框重复识别。
        if self._price_cache_image is not screen_image or self._price_cache_phase != self.scan_phase:
            self._price_cache = price_ocr_service.scan_prices(screen_image, self.scan_phase)
            self._price_cache_image = screen_image
            self._price_cache_phase = self.scan_phase
            for recognized in self._price_cache:
                self.logger.info("OCR 识别到 %s 价格：%s", recognized.slot.key, recognized.price)
        return self._price_cache

    def _wait_after_confirm(self, target: PurchaseTarget) -> None:
        # 顶部获得提示确认：确认点击后等待顶部获得提示出现；失败时点中心清理可能的遮挡，
        # 再重复购买弹窗末尾的确认点击。
        for attempt in range(1, 4):
            if self._wait_for_item_icon(target, REWARD_TOAST_ITEM_REGION, timeout=5.0, interval=0.1):
                time.sleep(1.5)
                return
            self.logger.warning("确认购买后顶部未识别到 %s，第 %s/3 次重试。", target.display_name, attempt)
            self._tap_flow_point(SCREEN_CENTER_POINT)
            time.sleep(self.config.adb_tap_sleep)
            self._tap_flow_point(CONFIRM_BUTTON_POINT)
            time.sleep(self.config.adb_tap_sleep)
        raise RuntimeError("确认购买后顶部商品提示未出现，已终止。")

    def _wait_for_item_icon(
        self,
        target: PurchaseTarget,
        region: tuple[int, int, int, int],
        timeout: float,
        interval: float,
    ) -> bool:
        """在指定参考区域内等待目标商品图标出现。"""

        deadline = time.time() + timeout
        template_path = ADB_ASSETS_DIR / target.file_name
        while time.time() <= deadline:
            screenshot = self._capture_color_screen()
            if match_item_icon(screenshot, template_path, region, color_order="bgr"):
                return True
            time.sleep(interval)
        return False

    def _wait_for_first_item_after_refresh(self) -> None:
        """刷新后等待商店首个商品行加载完成。"""

        deadline = time.time() + 10.0
        while time.time() <= deadline:
            screenshot = self._capture_color_screen()
            if color_region_matches(
                screenshot,
                FIRST_SHOP_ITEM_MARKER_POINT,
                FIRST_SHOP_ITEM_MARKER_COLOR,
                color_order="bgr",
            ):
                return
            time.sleep(0.2)
        raise RuntimeError("刷新后未检测到首个商品，已终止。")

    def _tap_flow_point(self, point: tuple[int, int]) -> None:
        # 将 1280x720 参考点缩放到 ADB 的 1920x1080 实际坐标。
        x, y = scale_point(point, self.screenwidth, self.screenheight)
        self._tap_exact((x, y))

    def _tap_exact(self, position: tuple[float, float]) -> None:
        if self.config.adb_debug:
            self._show_offset_area(*position, "ADB 调试", "请确认点击位置是否正确。")
        self._run_adb(["shell", "input", "tap", str(int(position[0])), str(int(position[1]))])

    def _show_offset_area(self, x: float, y: float, title: str, description: str) -> None:
        completed = self._run_adb(["exec-out", "screencap", "-p"], capture_output=True)
        img_array = np.frombuffer(completed.stdout, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        cv2.rectangle(
            image,
            (int(x - self.x_offset), int(y - self.y_offset)),
            (int(x + self.x_offset), int(y + self.y_offset)),
            (0, 0, 255),
            2,
        )
        if description:
            cv2.putText(
                image,
                description,
                (max(0, int(x - self.x_offset)), min(self.screenheight - 20, int(y + self.y_offset + 30))),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )
        preview = cv2.resize(image, (960, 540))
        cv2.imshow(f"{title} - 按任意键继续", preview)
        self.logger.info("ADB 调试图像已弹出，请在任务栏中查看。")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
