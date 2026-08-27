"""Pluggable lead sources.

Each source is a small class that turns a search into a list of
LeadCandidate objects. To add a new one: subclass BaseLeadSource,
implement fetch(), and register it in SOURCE_REGISTRY below.
"""

from typing import Any

from .base import BaseLeadSource
from .github_source import GitHubSource
from .google_news import GoogleNewsSource
from .hackernews import HackerNewsSource
from .reddit_source import RedditSource

SOURCE_REGISTRY: dict[str, type[BaseLeadSource]] = {
    "hackernews": HackerNewsSource,
    "google_news": GoogleNewsSource,
    "github": GitHubSource,
    "reddit": RedditSource,
}


def get_enabled_sources(config: dict[str, Any], only: list[str] | None = None) -> list[BaseLeadSource]:
    sources_cfg = config.get("sources", {})
    enabled = []
    for name, source_cls in SOURCE_REGISTRY.items():
        if only and name not in only:
            continue
        source_cfg = sources_cfg.get(name, {})
        if source_cfg.get("enabled", False):
            enabled.append(source_cls(source_cfg))
    return enabled
