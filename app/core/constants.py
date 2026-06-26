from __future__ import annotations

from pathlib import Path

from app.core.models import ItemDefinition

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
HISTORY_DIR = PROJECT_ROOT / "ShopRefreshHistory"
APP_CONFIG_PATH = PROJECT_ROOT / "app_config.ini"
WINDOW_ICON_PATH = ASSETS_DIR / "gui_icon.ico"

DEFAULT_TITLES = sorted(
    {
        "Epic Seven",
        "第七史诗",
        "BlueStacks App Player",
        "LDPlayer",
        "MuMu Player 12",
        "Google Play Games on PC Emulator",
        "에픽세븐",
    }
)

DEFAULT_STOP_KEY = "esc"
DEFAULT_MOUSE_SLEEP = 0.3
DEFAULT_SCREENSHOT_SLEEP = 0.3

ITEM_DEFINITIONS = [
    ItemDefinition(
        key="cov",
        file_name="cov.png",
        display_name="圣约书签",
        english_name="Covenant bookmark",
        price=184000,
        default_enabled=True,
    ),
    ItemDefinition(
        key="mys",
        file_name="mys.png",
        display_name="神秘奖牌",
        english_name="Mystic medal",
        price=280000,
        default_enabled=True,
    ),
    ItemDefinition(
        key="fb",
        file_name="fb.png",
        display_name="友情书签",
        english_name="Friendship bookmark",
        price=18000,
        default_enabled=False,
    ),
]
