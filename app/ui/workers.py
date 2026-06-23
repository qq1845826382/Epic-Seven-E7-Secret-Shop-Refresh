from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from app.core.engine import RefreshEngine
from app.core.models import ItemSelection, RunConfig, RunResult, RunStatistics


class RefreshWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    statistics_changed = Signal(object)

    def __init__(self, config: RunConfig, selections: list[ItemSelection], logger):
        super().__init__()
        self.config = config
        self.selections = selections
        self.logger = logger
        self.engine: RefreshEngine | None = None

    @Slot()
    def run(self) -> None:
        try:
            self.engine = RefreshEngine(
                config=self.config,
                selections=self.selections,
                on_statistics=self._emit_statistics,
                logger=self.logger,
            )
            result = self.engine.run()
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))

    @Slot()
    def request_stop(self) -> None:
        if self.engine is not None:
            self.engine.request_stop()

    def _emit_statistics(self, statistics: RunStatistics) -> None:
        self.statistics_changed.emit(statistics)
