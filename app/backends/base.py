from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.core.models import RunConfig


class BaseBackend(ABC):
    def __init__(self, config: RunConfig, logger):
        self.config = config
        self.logger = logger

    @property
    @abstractmethod
    def page_settle_delay(self) -> float:
        raise NotImplementedError

    @property
    @abstractmethod
    def scroll_settle_delay(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def prepare(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def load_template(self, file_name: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    def open_shop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def capture_screen(self):
        raise NotImplementedError

    @abstractmethod
    def validate_top_prices(self, screen_image) -> bool:
        raise NotImplementedError

    @abstractmethod
    def find_item_position(self, screen_image, template) -> Any | None:
        raise NotImplementedError

    @abstractmethod
    def buy_item(self, position: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def scroll_shop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def refresh_shop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def click_screen_center(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_debug_screenshot(self, reason: str, image) -> str:
        raise NotImplementedError

    def cleanup(self) -> None:
        """Hook for optional resource cleanup."""
