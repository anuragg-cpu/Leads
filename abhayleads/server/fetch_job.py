"""Runs a fetch in a background thread inside the server process, so an
HTTP request can start one and return immediately - the mobile web UI
polls /fetch/status rather than holding a request open for however long
a fetch takes (which, per earlier testing in this project, can be
several minutes).

Single global job, not one per request: this is a single-user personal
tool, not a multi-tenant service - a second "start" while one is already
running is rejected rather than queued or run in parallel.
"""

import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from ..db import Database
from ..fetcher import run_fetch


class FetchJob:
    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self.messages: list[str] = []
        self.result: Optional[dict] = None
        self.error: Optional[str] = None
        self._stop_requested = False

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "messages": list(self.messages[-30:]),
                "result": self.result,
                "error": self.error,
            }

    def start(self, db_path: Path, config: dict[str, Any], only_source: Optional[str] = None) -> None:
        with self._lock:
            if self.running:
                raise RuntimeError("A fetch is already running.")
            self.running = True
            self.messages = []
            self.result = None
            self.error = None
            self._stop_requested = False

        thread = threading.Thread(target=self._run, args=(db_path, config, only_source), daemon=True)
        thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_requested = True

    def _should_stop(self) -> bool:
        with self._lock:
            return self._stop_requested

    def _progress(self, message: str) -> None:
        with self._lock:
            self.messages.append(message)

    def _run(self, db_path: Path, config: dict[str, Any], only_source: Optional[str]) -> None:
        try:
            db = Database(db_path)
            try:
                result = run_fetch(
                    db,
                    config,
                    only_sources=[only_source] if only_source else None,
                    progress=self._progress,
                    should_stop=self._should_stop,
                )
                with self._lock:
                    self.result = asdict(result)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001 - surfaced via /fetch/status
            with self._lock:
                self.error = str(exc)
        finally:
            with self._lock:
                self.running = False
