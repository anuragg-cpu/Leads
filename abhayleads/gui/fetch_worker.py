"""Runs a fetch on a background thread so the GUI never freezes while
network requests to the various sources are in flight.
"""

from typing import Any, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from ..db import Database
from ..fetcher import FetchResult, run_fetch


class FetchWorker(QThread):
    progress = pyqtSignal(str)
    #: Emitted right after each individual lead is scored and written to
    #: the database - lets the window show leads as they're found instead
    #: of only once the entire fetch (every source, every locality/keyword)
    #: finishes, which for osm_places can be several minutes.
    lead_saved = pyqtSignal()
    finished_ok = pyqtSignal(object)  # FetchResult
    finished_error = pyqtSignal(str)

    def __init__(self, db_path, config: dict[str, Any], only_source: Optional[str] = None):
        super().__init__()
        self.db_path = db_path
        self.config = config
        self.only_source = only_source

    def run(self):
        try:
            db = Database(self.db_path)
            result: FetchResult = run_fetch(
                db,
                self.config,
                only_sources=[self.only_source] if self.only_source else None,
                progress=self.progress.emit,
                on_lead_saved=self.lead_saved.emit,
            )
            db.close()
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user in the GUI
            self.finished_error.emit(str(exc))
