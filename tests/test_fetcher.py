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
