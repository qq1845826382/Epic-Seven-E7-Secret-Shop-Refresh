from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


# 购买弹窗确认、顶部获得提示、商店刷新确认参考 e7Helper 的 1280x720 坐标。
# 注意：这套坐标只用于购买后复核和刷新确认，不用于价格 OCR。
FLOW_BASE_WIDTH = 1280
FLOW_BASE_HEIGHT = 720

# 购买弹窗中商品图标的预设搜索区。
PURCHASE_DIALOG_ITEM_REGION = (430, 160, 850, 470)
# 确认购买后顶部获得提示中的商品图标搜索区。
REWARD_TOAST_ITEM_REGION = (531, 48, 649, 155)
# 购买确认按钮、恢复点击中心点、刷新按钮均来自参考文档坐标。
CONFIRM_BUTTON_POINT = (798, 504)
SCREEN_CENTER_POINT = (640, 360)
SHOP_REFRESH_BUTTON_POINT = (237, 652)
SHOP_REFRESH_CONFIRM_POINT = (727, 474)
# 刷新后用第一个商品行附近的蓝色标记判断商店列表已重新加载。
FIRST_SHOP_ITEM_MARKER_POINT = (1090, 109)
FIRST_SHOP_ITEM_MARKER_COLOR = (0x24, 0xA7, 0xFD)

# 图标和颜色判定阈值集中放在这里，后续校准时不用翻 backend 逻辑。
ICON_MATCH_THRESHOLD = 0.70
ICON_TEMPLATE_SCALES = (0.65, 0.75, 0.85, 0.95, 1.0, 1.05, 1.15, 1.25, 1.35, 1.45)
SHOP_ITEM_MARKER_COLOR_TOLERANCE = 24
SHOP_ITEM_MARKER_REGION_RADIUS = 8
SHOP_ITEM_MARKER_MIN_RATIO = 0.12


@dataclass(frozen=True)
class PurchaseTarget:
    """引擎选择的目标物品，在 backend 里同时用于价格匹配和图标复核。"""

    key: str
    file_name: str
    display_name: str
    price: str


@dataclass(frozen=True)
class PendingPurchase:
    """价格命中后暂存的购买上下文，供 buy_item() 执行后续购买复核。"""

    target: PurchaseTarget
    position: tuple[float, float]
    phase: str


def scale_point(
    point: tuple[float, float],
    width: float,
    height: float,
    origin: tuple[float, float] = (0, 0),
) -> tuple[float, float]:
    """把 1280x720 参考点缩放到当前截图或窗口坐标系。"""

    return (
        origin[0] + point[0] * width / FLOW_BASE_WIDTH,
        origin[1] + point[1] * height / FLOW_BASE_HEIGHT,
    )


def scale_rect(
    rect: tuple[int, int, int, int],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    """把 1280x720 参考矩形缩放到当前截图坐标系。"""

    left = _clamp(int(rect[0] * width / FLOW_BASE_WIDTH), 0, width - 1)
    top = _clamp(int(rect[1] * height / FLOW_BASE_HEIGHT), 0, height - 1)
    right = _clamp(int(rect[2] * width / FLOW_BASE_WIDTH), left + 1, width)
    bottom = _clamp(int(rect[3] * height / FLOW_BASE_HEIGHT), top + 1, height)
    return left, top, right, bottom


def match_item_icon(
    screen_image: np.ndarray,
    template_path: Path,
    region: tuple[int, int, int, int],
    color_order: str,
    threshold: float = ICON_MATCH_THRESHOLD,
) -> bool:
    """在指定参考区域内做多尺度图标匹配。

    搜索区域会随截图分辨率缩放；模板也在多个倍率下匹配，避免鼠标窗口、
    ADB 截图或模拟器缩放导致商品图标尺寸和模板图不完全一致。
    """

    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise RuntimeError(f"无法读取商品图标模板：{template_path}")

    height, width = screen_image.shape[:2]
    left, top, right, bottom = scale_rect(region, width, height)
    crop = screen_image[top:bottom, left:right]
    gray_crop = _to_gray(crop, color_order)

    best_score = 0.0
    for scaled_template in _scaled_templates(template, gray_crop.shape[:2]):
        result = cv2.matchTemplate(gray_crop, scaled_template, cv2.TM_CCOEFF_NORMED)
        best_score = max(best_score, float(result.max()))
        if best_score >= threshold:
            return True
    return False


def color_region_matches(
    screen_image: np.ndarray,
    point: tuple[int, int],
    expected_rgb: tuple[int, int, int],
    color_order: str,
    tolerance: int = SHOP_ITEM_MARKER_COLOR_TOLERANCE,
    radius: int = SHOP_ITEM_MARKER_REGION_RADIUS,
    min_ratio: float = SHOP_ITEM_MARKER_MIN_RATIO,
) -> bool:
    """在参考点附近检查目标颜色占比。

    不再依赖单个像素必须命中目标颜色；缩放、抗锯齿或轻微色差只要仍在
    小区域内保留足够多目标颜色，就认为商店商品行已加载。
    """

    if screen_image.ndim < 3:
        return False
    height, width = screen_image.shape[:2]
    x, y = scale_point(point, width, height)
    x = _clamp(int(x), 0, width - 1)
    y = _clamp(int(y), 0, height - 1)
    radius_x = max(2, int(radius * width / FLOW_BASE_WIDTH))
    radius_y = max(2, int(radius * height / FLOW_BASE_HEIGHT))
    left = _clamp(x - radius_x, 0, width - 1)
    right = _clamp(x + radius_x + 1, left + 1, width)
    top = _clamp(y - radius_y, 0, height - 1)
    bottom = _clamp(y + radius_y + 1, top + 1, height)
    crop = screen_image[top:bottom, left:right][:, :, :3]
    if color_order == "bgr":
        rgb = crop[:, :, ::-1].astype(np.int16)
    else:
        rgb = crop.astype(np.int16)
    expected = np.array(expected_rgb, dtype=np.int16)
    mask = np.all(np.abs(rgb - expected) <= tolerance, axis=2)
    return float(mask.mean()) >= min_ratio


def _to_gray(image: np.ndarray, color_order: str) -> np.ndarray:
    if image.ndim == 2:
        return image
    conversion = cv2.COLOR_BGR2GRAY if color_order == "bgr" else cv2.COLOR_RGB2GRAY
    return cv2.cvtColor(image, conversion)


def _scaled_templates(template: np.ndarray, crop_shape: tuple[int, int]):
    crop_height, crop_width = crop_shape
    yielded_shapes: set[tuple[int, int]] = set()
    for scale in ICON_TEMPLATE_SCALES:
        width = int(round(template.shape[1] * scale))
        height = int(round(template.shape[0] * scale))
        if width < 4 or height < 4 or width > crop_width or height > crop_height:
            continue
        shape = (width, height)
        if shape in yielded_shapes:
            continue
        yielded_shapes.add(shape)
        interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        yield cv2.resize(template, shape, interpolation=interpolation)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))
