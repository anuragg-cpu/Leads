"""Tests for FetchJob, the background thread runner behind
`abhayleads serve`'s /fetch/start /fetch/status /fetch/stop endpoints.
Uses a fake run_fetch (no real sources/network) with a threading.Event so
tests can deterministically control when the "fetch" finishes."""

import threading
import time
from dataclasses import dataclass, field

import pytest

from abhayleads.server.fetch_job import FetchJob


@dataclass
class FakeFetchResult:
    new_leads: int = 0
    updated_leads: int = 0
    dropped_no_keywords: int = 0
    errors: list = field(default_factory=list)
    sources_run: list = field(default_factory=list)
    stopped: bool = False


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_status_when_never_started():
    job = FetchJob()
    status = job.status()
    assert status == {"running": False, "messages": [], "result": None, "error": None}


def test_start_runs_and_completes(monkeypatch):
    def fake_run_fetch(db, config, only_sources=None, progress=None, should_stop=None):
        progress("Searching fake_source...")
        return FakeFetchResult(new_leads=2, sources_run=["fake_source"])

    monkeypatch.setattr("abhayleads.server.fetch_job.run_fetch", fake_run_fetch)
    monkeypatch.setattr("abhayleads.server.fetch_job.Database", lambda path: FakeDb())

    job = FetchJob()
    job.start(db_path="unused", config={})
    assert wait_until(lambda: not job.status()["running"])

    status = job.status()
    assert status["result"]["new_leads"] == 2
    assert "Searching fake_source..." in status["messages"]
    assert status["error"] is None


def test_start_rejects_concurrent_run(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def fake_run_fetch(db, config, only_sources=None, progress=None, should_stop=None):
        started.set()
        release.wait(timeout=2)
        return FakeFetchResult()

    monkeypatch.setattr("abhayleads.server.fetch_job.run_fetch", fake_run_fetch)
    monkeypatch.setattr("abhayleads.server.fetch_job.Database", lambda path: FakeDb())

    job = FetchJob()
    job.start(db_path="unused", config={})
    assert started.wait(timeout=2)

    with pytest.raises(RuntimeError):
        job.start(db_path="unused", config={})

    release.set()
    assert wait_until(lambda: not job.status()["running"])


def test_stop_sets_should_stop_flag(monkeypatch):
    saw_stop_requested = threading.Event()

    def fake_run_fetch(db, config, only_sources=None, progress=None, should_stop=None):
        for _ in range(200):
            if should_stop():
                saw_stop_requested.set()
                return FakeFetchResult(stopped=True)
            time.sleep(0.01)
        return FakeFetchResult()

    monkeypatch.setattr("abhayleads.server.fetch_job.run_fetch", fake_run_fetch)
    monkeypatch.setattr("abhayleads.server.fetch_job.Database", lambda path: FakeDb())

    job = FetchJob()
    job.start(db_path="unused", config={})
    job.stop()
    assert wait_until(lambda: not job.status()["running"])
    assert saw_stop_requested.is_set()
    assert job.status()["result"]["stopped"] is True


def test_exception_in_fetch_is_captured_as_error(monkeypatch):
    def fake_run_fetch(db, config, only_sources=None, progress=None, should_stop=None):
        raise RuntimeError("boom")

    monkeypatch.setattr("abhayleads.server.fetch_job.run_fetch", fake_run_fetch)
    monkeypatch.setattr("abhayleads.server.fetch_job.Database", lambda path: FakeDb())

    job = FetchJob()
    job.start(db_path="unused", config={})
    assert wait_until(lambda: not job.status()["running"])

    status = job.status()
    assert status["error"] == "boom"
    assert status["result"] is None


class FakeDb:
    def close(self):
        pass
