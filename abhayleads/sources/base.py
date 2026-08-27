"""Base class every lead source implements."""

from abc import ABC, abstractmethod
from typing import Any

from ..models import LeadCandidate

#: A generic browser-style user agent. Being identifiable and polite (a
#: real UA, modest request rates, respecting robots.txt) is part of what
#: keeps these sources ToS-safe - don't strip this out to look more like
#: a bare script.
USER_AGENT = "AbhayLeadsBot/0.1 (personal lead-research tool; contact: set-your-email-in-config)"


class BaseLeadSource(ABC):
    name: str = "base"

    def __init__(self, source_config: dict[str, Any]):
        self.source_config = source_config

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
        try:
            return self.fetch(keywords), []
        except Exception as exc:  # noqa: BLE001 - deliberately broad, this is a boundary
            return [], [f"{self.name}: {exc}"]
