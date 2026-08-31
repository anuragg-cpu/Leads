"""Base class every lead source implements."""

from abc import ABC, abstractmethod
from typing import Any, Callable, Iterator

from ..models import LeadCandidate

#: A generic browser-style user agent. Being identifiable and polite (a
#: real UA, modest request rates, respecting robots.txt) is part of what
#: keeps these sources ToS-safe - don't strip this out to look more like
#: a bare script.
USER_AGENT = "AbhayLeadsBot/0.1 (personal lead-research tool; contact: set-your-email-in-config)"


def _noop(_message: str) -> None:
    pass


class BaseLeadSource(ABC):
    name: str = "base"

    def __init__(self, source_config: dict[str, Any]):
        self.source_config = source_config
        #: Set by fetcher.run_fetch before each call, so a slow source (one
        #: making many network requests, like osm_places) can report which
        #: item it's on instead of going silent for minutes at a time.
        #: Sources that finish in one or two quick requests can ignore this.
        self.progress_callback: Callable[[str], None] = _noop
        #: A source that makes several independent requests (one per
        #: locality, one per subreddit, ...) should catch a failure on any
        #: single one, append a note here, and carry on rather than losing
        #: everything collected so far - safe_fetch() surfaces these
        #: alongside whatever candidates *did* come back.
        self.warnings: list[str] = []

    @abstractmethod
    def fetch(self, keywords: list[str]) -> Iterator[LeadCandidate]:
        """Search for the given keywords, yielding raw candidates as they're
        found - NOT a list built up and returned at the end. This is what
        lets the CLI/GUI save (and, in the GUI, display) each lead the
        moment it's found instead of waiting for the whole source - all
        localities, all keywords - to finish first.

        Implementations should NOT filter/score - just yield everything
        plausibly relevant. Scoring and exclusion happen centrally so the
        logic only has to be tuned in one place.
        """
        raise NotImplementedError
        yield  # pragma: no cover - makes this a generator function to subclass

    def safe_fetch(self, keywords: list[str]) -> Iterator[LeadCandidate]:
        """Wraps fetch() so one source's network hiccup doesn't kill a run.

        Yields through to fetch()'s candidates as they arrive. If fetch()
        raises partway through, whatever was already yielded (and, by the
        caller, already saved) is NOT lost - only the exception is recorded,
        into self.warnings, for the caller to check once iteration ends.
        """
        self.warnings = []
        try:
            yield from self.fetch(keywords)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, this is a boundary
            self.warnings.append(f"{self.name}: {exc}")
