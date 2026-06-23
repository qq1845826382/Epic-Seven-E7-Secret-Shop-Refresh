from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from app.ui.main_window import MainWindow


def run_app(default_mode: str = "mouse", from_legacy_entry: bool = False) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    setTheme(Theme.DARK)
    window = MainWindow(default_mode=default_mode, from_legacy_entry=from_legacy_entry)
    window.show()
    return app.exec()
