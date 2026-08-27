"""Base class every lead source implements."""

from abc import ABC, abstractmethod
from typing import Any, Callable

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
    def fetch(self, keywords: list[str]) -> list[LeadCandidate]:
        """Run a search for the given keywords and return raw candidates.

        Implementations should NOT filter/score - just return everything
        plausibly relevant. Scoring and exclusion happen centrally so the
        logic only has to be tuned in one place.
        """
        raise NotImplementedError

    def safe_fetch(self, keywords: list[str]) -> tuple[list[LeadCandidate], list[str]]:
        """Wraps fetch() so one source's network hiccup doesn't kill a run."""
        self.warnings = []
        try:
            candidates = self.fetch(keywords)
            return candidates, list(self.warnings)
        except Exception as exc:  # noqa: BLE001 - deliberately broad, this is a boundary
            return [], self.warnings + [f"{self.name}: {exc}"]
