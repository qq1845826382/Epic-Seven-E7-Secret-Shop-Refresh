from __future__ import annotations

import numpy as np
import win32gui
from windows_capture import Frame, InternalCaptureControl, WindowsCapture


class WindowCaptureService:
    """Capture a window client area with Windows Graphics Capture."""

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

    def capture_client(self, hwnd: int) -> np.ndarray:
        result: dict[str, np.ndarray] = {}
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
            result["bgra"] = frame.frame_buffer.copy()
            capture_control.stop()

        @capture.event
        def on_closed() -> None:
            return

        capture.start()
        bgra_image = result.get("bgra")
        if bgra_image is None:
            raise RuntimeError("没有获取到窗口画面。")

        client_bgra = self._crop_client_area(bgra_image, hwnd)
        return client_bgra[:, :, [2, 1, 0]].copy()

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
