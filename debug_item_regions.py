from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pyautogui
import win32con
import win32gui
from PIL import Image

from app.services.price_ocr_service import (
    BASE_HEIGHT,
    BASE_WIDTH,
    PRICE_SLOTS,
    PriceSlot,
    price_ocr_service,
)
from app.services.window_capture_service import window_capture_service


DEFAULT_WINDOW_TITLE = "第七史诗"
SCROLL_WAIT_SECONDS = 1.0


def crop_slot(screen_image: np.ndarray, slot: PriceSlot) -> np.ndarray:
    height, width = screen_image.shape[:2]
    scale_x = width / BASE_WIDTH
    scale_y = height / BASE_HEIGHT
    left, top, right, bottom = slot.crop
    left = max(0, min(round(left * scale_x), width))
    top = max(0, min(round(top * scale_y), height))
    right = max(left + 1, min(round(right * scale_x), width))
    bottom = max(top + 1, min(round(bottom * scale_y), height))
    return screen_image[top:bottom, left:right].copy()


def activate_window(hwnd: int) -> None:
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass


def scroll_shop_once(hwnd: int) -> None:
    client_left, client_top, client_width, client_height = (
        window_capture_service.get_client_bounds(hwnd)
    )
    x = client_left + client_width * 0.58
    start_y = client_top + client_height * 0.65
    end_y = client_top + client_height * (0.65 - 0.277)

    pyautogui.moveTo(x, start_y)
    time.sleep(0.05)
    pyautogui.mouseDown(button="left")
    try:
        time.sleep(0.05)
        pyautogui.moveTo(x, end_y)
        time.sleep(0.05)
    finally:
        pyautogui.mouseUp(button="left")


def save_phase(
    screen_image: np.ndarray,
    phase: str,
    output_dir: Path,
) -> None:
    Image.fromarray(screen_image, mode="RGB").save(output_dir / f"{phase}_full.png")

    for slot in PRICE_SLOTS:
        if slot.phase != phase:
            continue
        region = crop_slot(screen_image, slot)
        region_path = output_dir / f"{slot.key}.png"
        Image.fromarray(region, mode="RGB").save(region_path)
        try:
            price = price_ocr_service.recognize_price(region)
            result = price if price else "识别失败"
        except Exception as exc:
            result = f"OCR 异常：{exc}"
        print(f"{slot.key}: {result} -> {region_path}")


def run_debug(window_title: str, output_root: Path) -> Path:
    hwnd = window_capture_service.find_window(window_title)
    activate_window(hwnd)
    time.sleep(0.5)

    output_dir = output_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=False)

    print(f"已找到窗口：{window_title}")
    print("正在截取 item_1 到 item_4……")
    top_image = window_capture_service.capture_client(hwnd)
    save_phase(top_image, "top", output_dir)

    print("正在向上滑动商店……")
    scroll_shop_once(hwnd)
    print(f"滑动完成，固定等待 {SCROLL_WAIT_SECONDS:.0f} 秒……")
    time.sleep(SCROLL_WAIT_SECONDS)

    print("正在截取 item_5 和 item_6……")
    bottom_image = window_capture_service.capture_client(hwnd)
    save_phase(bottom_image, "bottom", output_dir)

    print(f"调试完成，未购买、未刷新。截图目录：{output_dir}")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="一次性截取神秘商店 item_1 到 item_6 的价格区域。",
    )
    parser.add_argument(
        "--window-title",
        default=DEFAULT_WINDOW_TITLE,
        help=f"目标窗口标题，默认：{DEFAULT_WINDOW_TITLE}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("debug_item_regions"),
        help="截图输出根目录，默认：debug_item_regions",
    )
    args = parser.parse_args()
    try:
        run_debug(args.window_title, args.output)
    finally:
        window_capture_service.stop()


if __name__ == "__main__":
    main()
