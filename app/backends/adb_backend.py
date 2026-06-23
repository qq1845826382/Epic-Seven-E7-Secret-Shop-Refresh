from __future__ import annotations

import random
import subprocess
import time
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.backends.base import BaseBackend
from app.core.constants import (
    ADB_ASSETS_DIR,
    ADB_EXECUTABLE,
    SUPPORTED_ADB_HEIGHT,
    SUPPORTED_ADB_WIDTH,
)
from app.services.adb_service import ADBService


class ADBBackend(BaseBackend):
    def __init__(self, config, logger):
        super().__init__(config, logger)
        self.adb_service = ADBService(ADB_EXECUTABLE)
        self.device_id = ""
        self.screenwidth = SUPPORTED_ADB_WIDTH
        self.screenheight = SUPPORTED_ADB_HEIGHT
        self.x_offset = 75 if self.config.adb_random_offset else 0
        self.y_offset = 25 if self.config.adb_random_offset else 0

    @property
    def page_settle_delay(self) -> float:
        return 1.5

    @property
    def scroll_settle_delay(self) -> float:
        return 1.0

    def prepare(self) -> None:
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
        path = Path(ADB_ASSETS_DIR) / file_name
        image = cv2.imread(str(path))
        if image is None:
            raise RuntimeError(f"无法读取 ADB 模板图片：{path}")
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    def open_shop(self) -> None:
        self._tap(self.screenwidth * 0.0411, self.screenheight * 0.3835, fixed=True)
        time.sleep(0.5)
        self._tap(self.screenwidth * 0.4406, self.screenheight * 0.2462, fixed=True)
        time.sleep(0.5)
        self._tap(self.screenwidth * 0.0411, self.screenheight * 0.3835, fixed=True)
        time.sleep(0.5)
        self.logger.info("已进入神秘商店页面。")

    def capture_screen(self):
        completed = self._run_adb(["exec-out", "screencap", "-p"], capture_output=True)
        img_array = np.frombuffer(completed.stdout, dtype=np.uint8)
        screenshot = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
        if screenshot is None:
            raise RuntimeError("ADB 截图失败。")
        return screenshot

    def find_item_position(self, screen_image, template) -> tuple[float, float] | None:
        result = cv2.matchTemplate(screen_image, template, cv2.TM_CCOEFF_NORMED)
        loc = np.where(result >= 0.75)
        if loc[0].size > 0:
            x = loc[1][0] + self.screenwidth * 0.4718
            y = loc[0][0] + self.screenheight * 0.1000
            return x, y
        return None

    def buy_item(self, position: tuple[float, float]) -> None:
        self._tap(*position, prompt="请确认红框位于购买按钮范围内。")
        time.sleep(self.config.adb_tap_sleep)
        self._tap(
            self.screenwidth * 0.5677,
            self.screenheight * 0.7037,
            prompt="请确认红框位于购买确认按钮范围内。",
        )
        time.sleep(self.config.adb_tap_sleep)
        time.sleep(1.0)

    def scroll_shop(self) -> None:
        x = self.screenwidth * 0.6250
        y1 = self.screenheight * 0.7481
        y2 = self.screenheight * 0.3629
        if self.config.adb_debug:
            self._show_offset_area(x, y1, "起始滑动区域", "请确认红框位于可滑动区域")
        x_offset, y_offset = self._generate_offset()
        self._run_adb(
            [
                "shell",
                "input",
                "swipe",
                str(x + x_offset),
                str(y1 + y_offset),
                str(x + x_offset),
                str(y2 + y_offset),
            ]
        )

    def refresh_shop(self) -> None:
        self._tap(
            self.screenwidth * 0.1698,
            self.screenheight * 0.9138,
            prompt="请确认红框位于刷新按钮范围内。",
        )
        time.sleep(self.config.adb_tap_sleep)
        self._tap(
            self.screenwidth * 0.5828,
            self.screenheight * 0.6411,
            prompt="请确认红框位于刷新确认按钮范围内。",
        )
        time.sleep(self.config.adb_tap_sleep)

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
