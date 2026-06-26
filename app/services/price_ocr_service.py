from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

import cv2
import numpy as np


BASE_WIDTH = 1920
BASE_HEIGHT = 1080


@dataclass(frozen=True)
class PriceSlot:
    key: str
    phase: str
    crop: tuple[int, int, int, int]
    buy_x_range: tuple[int, int]
    buy_y_range: tuple[int, int]


@dataclass(frozen=True)
class RecognizedPrice:
    slot: PriceSlot
    price: str


PRICE_SLOTS = [
    PriceSlot("item_1", "top", (1660, 140, 1860, 190), (1600, 1850), (222, 270)),
    PriceSlot("item_2", "top", (1660, 350, 1860, 410), (1600, 1850), (440, 485)),
    PriceSlot("item_3", "top", (1660, 570, 1860, 630), (1600, 1850), (660, 705)),
    PriceSlot("item_4", "top", (1660, 790, 1860, 850), (1600, 1850), (875, 918)),
    PriceSlot("item_5", "bottom", (1660, 705, 1860, 760), (1600, 1850), (795, 836)),
    PriceSlot("item_6", "bottom", (1660, 925, 1860, 980), (1600, 1850), (1010, 1055)),
]


class PriceOCRService:
    def __init__(self) -> None:
        self._engine: Any | None = None

    def scan_prices(
        self,
        screen_image: np.ndarray,
        phase: str,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
    ) -> list[RecognizedPrice]:
        recognized: list[RecognizedPrice] = []
        for slot in PRICE_SLOTS:
            if slot.phase != phase:
                continue
            crop = self._crop(screen_image, slot.crop, scale_x, scale_y)
            price = self.recognize_price(crop)
            if price:
                recognized.append(RecognizedPrice(slot=slot, price=price))
        return recognized

    def ensure_ready(self) -> None:
        self._get_engine()

    def recognize_price(self, image: np.ndarray) -> str:
        result = self._get_engine()(self._preprocess(image))
        text = "".join(self._extract_texts(result))
        return self.clean_price_text(text)

    @staticmethod
    def clean_price_text(text: str) -> str:
        return re.sub(r"\D", "", text)

    def _get_engine(self):
        if self._engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError as exc:
                raise RuntimeError("缺少 RapidOCR 依赖，请先执行 pip install -r requirements.txt。") from exc
            try:
                self._engine = RapidOCR()
            except Exception as exc:
                raise RuntimeError(f"RapidOCR 初始化失败：{exc}") from exc
        return self._engine

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            gray = image
        enlarged = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        blurred = cv2.GaussianBlur(enlarged, (3, 3), 0)
        _, threshold = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return cv2.cvtColor(threshold, cv2.COLOR_GRAY2BGR)

    def _crop(
        self,
        screen_image: np.ndarray,
        crop: tuple[int, int, int, int],
        scale_x: float,
        scale_y: float,
    ) -> np.ndarray:
        height, width = screen_image.shape[:2]
        left = self._clamp(int(crop[0] * scale_x), 0, width)
        top = self._clamp(int(crop[1] * scale_y), 0, height)
        right = self._clamp(int(crop[2] * scale_x), left + 1, width)
        bottom = self._clamp(int(crop[3] * scale_y), top + 1, height)
        return screen_image[top:bottom, left:right]

    @staticmethod
    def _clamp(value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(value, maximum))

    def _extract_texts(self, result: Any) -> Iterable[str]:
        if result is None:
            return
        for attr in ("txts", "texts", "rec_texts"):
            values = getattr(result, attr, None)
            if values is not None:
                for value in values:
                    yield str(value)
                return
        for method_name in ("to_dict", "to_json"):
            method = getattr(result, method_name, None)
            if callable(method):
                yield from self._extract_texts(method())
                return
        if isinstance(result, dict):
            for key in ("txts", "texts", "rec_texts"):
                values = result.get(key)
                if values is not None:
                    for value in values:
                        yield str(value)
                    return
            for value in result.values():
                yield from self._extract_texts(value)
            return
        if isinstance(result, (list, tuple)):
            for item in result:
                if isinstance(item, str):
                    yield item
                elif isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[1], str):
                    yield item[1]
                else:
                    yield from self._extract_texts(item)


price_ocr_service = PriceOCRService()
