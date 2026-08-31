"""Tests for BaseLeadSource.safe_fetch's streaming/error-recovery behavior.

This is the mechanism behind "leads show up as they're found" instead of
only after an entire source finishes - safe_fetch must be a real
generator that yields through as fetch() produces items, and a later
failure must not erase items already yielded.
"""

from abhayleads.models import LeadCandidate
from abhayleads.sources.base import BaseLeadSource


def make_candidate(n: int) -> LeadCandidate:
    return LeadCandidate(source="fake", source_detail=str(n), company=f"Company {n}")


class WellBehavedSource(BaseLeadSource):
    name = "fake"

    def fetch(self, keywords):
        for i in range(3):
            yield make_candidate(i)


class FailsPartwaySource(BaseLeadSource):
    name = "fake"

    def fetch(self, keywords):
        yield make_candidate(0)
        yield make_candidate(1)
        raise RuntimeError("boom")
        yield make_candidate(2)  # pragma: no cover - unreachable


def test_safe_fetch_yields_incrementally_not_all_at_once():
    source = WellBehavedSource({})
    generator = source.safe_fetch([])

    # Consuming just the first item must not require the source to have
    # produced all of them yet - that's the whole point of streaming.
    first = next(generator)
    assert first.company == "Company 0"

    remaining = list(generator)
    assert [c.company for c in remaining] == ["Company 1", "Company 2"]


def test_safe_fetch_keeps_items_yielded_before_a_later_failure():
    source = FailsPartwaySource({})
    candidates = list(source.safe_fetch([]))

    assert [c.company for c in candidates] == ["Company 0", "Company 1"]
    assert len(source.warnings) == 1
    assert "boom" in source.warnings[0]


def test_safe_fetch_resets_warnings_on_each_call():
    source = FailsPartwaySource({})
    list(source.safe_fetch([]))
    assert len(source.warnings) == 1

    list(source.safe_fetch([]))
    assert len(source.warnings) == 1  # not accumulated to 2 across calls
