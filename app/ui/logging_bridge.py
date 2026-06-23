from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal


class LogEmitter(QObject):
    message_logged = Signal(str)


class QtLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.emitter = LogEmitter()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # pragma: no cover - logging internals
            message = record.getMessage()
        self.emitter.message_logged.emit(message)
