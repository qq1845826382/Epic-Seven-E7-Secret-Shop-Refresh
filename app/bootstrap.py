from __future__ import annotations

import os
import sys

if os.name == "nt":
    os.environ.setdefault("QT_QPA_PLATFORM", "windows:dpiawareness=0")

from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from app.core.constants import WINDOW_ICON_PATH
from app.ui.main_window import MainWindow


def set_windows_app_id() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("kcdr.e7.secretshop.refresh")
    except Exception:
        pass


def apply_dark_mode(app: QApplication) -> None:
    setTheme(Theme.DARK)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(32, 32, 32))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.Base, QColor(24, 24, 24))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(38, 38, 38))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.Text, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 212))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    app.setStyleSheet(
        """
        QMainWindow {
            background-color: #202020;
            color: #f0f0f0;
        }
        QTabBar::tab {
            background-color: #242424;
            color: #d8d8d8;
            border: 0;
            border-radius: 4px;
            padding: 6px 14px;
            margin-right: 4px;
        }
        QTabBar::tab:selected {
            background-color: #3a3a3a;
            color: #ffffff;
            font-weight: 600;
        }
        QTabBar::tab:hover:!selected {
            background-color: #303030;
            color: #ffffff;
        }
        QTabWidget::pane, QScrollArea, QScrollArea > QWidget > QWidget {
            border: 0;
            background-color: #202020;
        }
        QScrollBar:vertical {
            background-color: #202020;
            width: 12px;
            margin: 2px;
            border: 0;
        }
        QScrollBar::handle:vertical {
            background-color: #555555;
            min-height: 36px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #6a6a6a;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {
            background: transparent;
            border: 0;
            height: 0;
        }
        QScrollBar:horizontal {
            background-color: #202020;
            height: 12px;
            margin: 2px;
            border: 0;
        }
        QScrollBar::handle:horizontal {
            background-color: #555555;
            min-width: 36px;
            border-radius: 6px;
        }
        QScrollBar::handle:horizontal:hover {
            background-color: #6a6a6a;
        }
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal,
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {
            background: transparent;
            border: 0;
            width: 0;
        }
        QPlainTextEdit {
            background-color: #181818;
            color: #f0f0f0;
            border: 1px solid #3a3a3a;
            border-radius: 6px;
            selection-background-color: #0078d4;
        }
        QSpinBox, QDoubleSpinBox {
            background-color: #181818;
            color: #f0f0f0;
            border: 1px solid #3a3a3a;
            border-radius: 4px;
            padding: 2px 6px;
        }
        QCheckBox {
            background-color: transparent;
            color: #f0f0f0;
        }
        """
    )


def run_app() -> int:
    set_windows_app_id()
    app = QApplication.instance() or QApplication(sys.argv)
    if WINDOW_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(WINDOW_ICON_PATH)))
    apply_dark_mode(app)
    window = MainWindow()
    window.show()
    return app.exec()
