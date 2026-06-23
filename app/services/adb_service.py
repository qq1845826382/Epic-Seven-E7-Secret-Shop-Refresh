from __future__ import annotations

import configparser
import subprocess
from pathlib import Path

from app.core.constants import ADB_CONFIG_PATH, ADB_EXECUTABLE


class ADBService:
    def __init__(self, adb_path: Path | None = None):
        self.adb_path = Path(adb_path or ADB_EXECUTABLE)

    def list_devices(self) -> list[str]:
        result = subprocess.run(
            [str(self.adb_path), "devices"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []
        devices: list[str] = []
        for line in result.stdout.splitlines()[1:]:
            line = line.strip()
            if not line or "\t" not in line:
                continue
            device_id, status = line.split("\t", 1)
            if status.strip() == "device":
                devices.append(device_id)
        return devices

    def connect_device(self, address: str) -> tuple[bool, str]:
        result = subprocess.run(
            [str(self.adb_path), "connect", address],
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout or result.stderr).strip()
        success_keywords = ("connected to", "already connected to")
        success = any(keyword in output.lower() for keyword in success_keywords)
        return success, output

    def load_config(self, config_path: Path | None = None) -> dict[str, str]:
        path = Path(config_path or ADB_CONFIG_PATH)
        if not path.exists():
            return {}
        config = configparser.ConfigParser()
        config.read(path, encoding="utf-8")
        return dict(config["Settings"]) if config.has_section("Settings") else {}

    def save_config(self, values: dict[str, str], config_path: Path | None = None) -> Path:
        path = Path(config_path or ADB_CONFIG_PATH)
        config = configparser.ConfigParser()
        config["Settings"] = values
        with path.open("w", encoding="utf-8") as file:
            config.write(file)
        return path
