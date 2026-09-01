"""Tests for run_fetch's on_lead_saved callback - the mechanism a GUI
uses to show leads as they're found instead of waiting for the whole
fetch to finish.
"""

import tempfile
from pathlib import Path

import pytest

from abhayleads.db import Database
from abhayleads.fetcher import run_fetch
from abhayleads.models import LeadCandidate
from abhayleads.sources.base import BaseLeadSource


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmp:
        database = Database(Path(tmp) / "test.db")
        yield database
        database.close()


class FakeSource(BaseLeadSource):
    name = "fake"

    def fetch(self, keywords):
        for i in range(3):
            yield LeadCandidate(source=self.name, source_detail=str(i), company=f"Company {i}", raw_text="x")


BASE_CONFIG = {
    "product": {"keywords": ["x"]},
    "sources": {"fake": {"enabled": True}},
    "scoring": {},
}


def test_on_lead_saved_called_once_per_candidate(db, monkeypatch):
    monkeypatch.setattr("abhayleads.fetcher.get_enabled_sources", lambda config, only=None: [FakeSource({})])

    call_count = {"n": 0}
    run_fetch(db, BASE_CONFIG, on_lead_saved=lambda: call_count.update(n=call_count["n"] + 1))

    assert call_count["n"] == 3
    assert len(db.list_leads()) == 3


def test_leads_are_queryable_immediately_after_each_on_lead_saved_call(db, monkeypatch):
    # The whole point: a lead saved mid-fetch must already be in the db
    # by the time on_lead_saved fires for it - not batched until the end.
    monkeypatch.setattr("abhayleads.fetcher.get_enabled_sources", lambda config, only=None: [FakeSource({})])

    counts_seen = []
    run_fetch(db, BASE_CONFIG, on_lead_saved=lambda: counts_seen.append(len(db.list_leads())))

    assert counts_seen == [1, 2, 3]


def test_fetch_without_on_lead_saved_still_works(db, monkeypatch):
    monkeypatch.setattr("abhayleads.fetcher.get_enabled_sources", lambda config, only=None: [FakeSource({})])

    result = run_fetch(db, BASE_CONFIG)

    assert result.new_leads == 3
    assert len(db.list_leads()) == 3


class TwoSourceFake(BaseLeadSource):
    """Second source, for testing that a stop mid-way through source 1
    never even starts source 2."""

    name = "fake2"

    def fetch(self, keywords):
        for i in range(3):
            yield LeadCandidate(source=self.name, source_detail=f"s2-{i}", company=f"S2 {i}", raw_text="x")


def test_should_stop_ends_the_fetch_early_but_keeps_leads_already_saved(db, monkeypatch):
    monkeypatch.setattr(
        "abhayleads.fetcher.get_enabled_sources", lambda config, only=None: [FakeSource({}), TwoSourceFake({})]
    )

    # Stop as soon as 2 leads have been saved - partway through the
    # first source, well before the second source ever runs.
    saved_count = {"n": 0}

    def should_stop():
        return saved_count["n"] >= 2

    def on_lead_saved():
        saved_count["n"] += 1

    result = run_fetch(db, BASE_CONFIG, on_lead_saved=on_lead_saved, should_stop=should_stop)

    assert result.stopped is True
    assert result.new_leads == 2
    assert len(db.list_leads()) == 2
    assert all(lead["source"] == "fake" for lead in db.list_leads())  # source 2 never ran


def test_fetch_reports_not_stopped_when_it_finishes_normally(db, monkeypatch):
    monkeypatch.setattr("abhayleads.fetcher.get_enabled_sources", lambda config, only=None: [FakeSource({})])

    result = run_fetch(db, BASE_CONFIG, should_stop=lambda: False)

    assert result.stopped is False
    assert result.new_leads == 3
