from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np
import win32gui
from windows_capture import Frame, InternalCaptureControl, WindowsCapture


class WindowCaptureService:
    """Capture a window client area with Windows Graphics Capture."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._hwnd: int | None = None
        self._capture: WindowsCapture | None = None
        self._capture_control: Any | None = None
        self._latest_bgra: np.ndarray | None = None
        self._frame_seq = 0
        self._closed = False

    @staticmethod
    def find_window(window_title: str) -> int:
        hwnd = win32gui.FindWindow(None, window_title)
        if not hwnd:
            raise RuntimeError(f"没有找到窗口：{window_title}")
        return hwnd

    @staticmethod
    def get_client_bounds(hwnd: int) -> tuple[int, int, int, int]:
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        screen_left, screen_top = win32gui.ClientToScreen(hwnd, (left, top))
        screen_right, screen_bottom = win32gui.ClientToScreen(hwnd, (right, bottom))
        width = screen_right - screen_left
        height = screen_bottom - screen_top
        if width <= 0 or height <= 0:
            raise RuntimeError("窗口客户区尺寸无效，请确认窗口未最小化。")
        return screen_left, screen_top, width, height

    def start_client_capture(self, hwnd: int) -> None:
        self._ensure_capture(hwnd)

    def stop(self) -> None:
        control = self._detach_capture()
        self._stop_control(control)

    def capture_client(self, hwnd: int, timeout_seconds: float = 2.0) -> np.ndarray:
        bgra_image = self._latest_frame(hwnd, timeout_seconds)
        client_bgra = self._crop_client_area(bgra_image, hwnd)
        return client_bgra[:, :, [2, 1, 0]].copy()

    def _latest_frame(self, hwnd: int, timeout_seconds: float) -> np.ndarray:
        for _ in range(2):
            self._ensure_capture(hwnd)
            deadline = time.monotonic() + timeout_seconds
            with self._condition:
                while (
                    self._hwnd == hwnd
                    and self._latest_bgra is None
                    and not self._closed
                ):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._condition.wait(remaining)

                if self._hwnd == hwnd and self._latest_bgra is not None:
                    return self._latest_bgra.copy()
                closed = self._closed

            if closed:
                self._detach_capture()
                continue

            raise RuntimeError("没有获取到窗口画面。")

        raise RuntimeError("窗口捕获会话已关闭，无法获取窗口画面。")

    def _ensure_capture(self, hwnd: int) -> None:
        with self._condition:
            if (
                self._hwnd == hwnd
                and self._capture_control is not None
                and not self._closed
                and not self._capture_finished()
            ):
                return

        self._start_capture(hwnd)

    def _start_capture(self, hwnd: int) -> None:
        old_control = self._detach_capture()
        self._stop_control(old_control)

        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=None,
            monitor_index=None,
            window_name=None,
            window_hwnd=hwnd,
        )

        @capture.event
        def on_frame_arrived(
            frame: Frame,
            capture_control: InternalCaptureControl,
        ) -> None:
            with self._condition:
                if self._capture is not capture:
                    return
                self._latest_bgra = frame.frame_buffer.copy()
                self._frame_seq += 1
                self._condition.notify_all()

        @capture.event
        def on_closed() -> None:
            with self._condition:
                if self._capture is capture:
                    self._closed = True
                    self._condition.notify_all()

        with self._condition:
            self._hwnd = hwnd
            self._capture = capture
            self._capture_control = None
            self._latest_bgra = None
            self._frame_seq = 0
            self._closed = False

        try:
            control = capture.start_free_threaded()
        except Exception:
            with self._condition:
                if self._capture is capture:
                    self._clear_capture_locked()
                    self._condition.notify_all()
            raise

        with self._condition:
            if self._capture is capture:
                self._capture_control = control
            else:
                self._stop_control(control)

    def _detach_capture(self) -> Any | None:
        with self._condition:
            control = self._capture_control
            self._clear_capture_locked()
            self._condition.notify_all()
            return control

    def _clear_capture_locked(self) -> None:
        self._hwnd = None
        self._capture = None
        self._capture_control = None
        self._latest_bgra = None
        self._frame_seq = 0
        self._closed = False

    def _capture_finished(self) -> bool:
        if self._capture_control is None:
            return True
        try:
            return bool(self._capture_control.is_finished())
        except Exception:
            return True

    @staticmethod
    def _stop_control(control: Any | None) -> None:
        if control is None:
            return
        try:
            control.stop()
        except Exception:
            return

    @staticmethod
    def _crop_client_area(bgra_image: np.ndarray, hwnd: int) -> np.ndarray:
        frame_height, frame_width = bgra_image.shape[:2]
        window_left, window_top, window_right, window_bottom = win32gui.GetWindowRect(hwnd)
        client_left, client_top, client_width, client_height = (
            WindowCaptureService.get_client_bounds(hwnd)
        )
        window_width = window_right - window_left
        window_height = window_bottom - window_top
        if window_width <= 0 or window_height <= 0:
            raise RuntimeError("窗口尺寸无效。")

        scale_x = frame_width / window_width
        scale_y = frame_height / window_height
        crop_left = round((client_left - window_left) * scale_x)
        crop_top = round((client_top - window_top) * scale_y)
        crop_right = round((client_left + client_width - window_left) * scale_x)
        crop_bottom = round((client_top + client_height - window_top) * scale_y)

        crop_left = max(0, min(crop_left, frame_width))
        crop_top = max(0, min(crop_top, frame_height))
        crop_right = max(crop_left, min(crop_right, frame_width))
        crop_bottom = max(crop_top, min(crop_bottom, frame_height))
        cropped = bgra_image[crop_top:crop_bottom, crop_left:crop_right]
        if cropped.size == 0:
            raise RuntimeError("窗口客户区截图为空，请检查窗口状态。")
        return cropped


window_capture_service = WindowCaptureService()
