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
from .osm_places import OSMPlacesSource
from .reddit_source import RedditSource

SOURCE_REGISTRY: dict[str, type[BaseLeadSource]] = {
    "hackernews": HackerNewsSource,
    "google_news": GoogleNewsSource,
    "github": GitHubSource,
    "reddit": RedditSource,
    "osm_places": OSMPlacesSource,
}


def get_enabled_sources(config: dict[str, Any], only: list[str] | None = None) -> list[BaseLeadSource]:
    sources_cfg = config.get("sources", {})
    target_locations = config.get("product", {}).get("target_locations", [])
    enabled = []
    for name, source_cls in SOURCE_REGISTRY.items():
        if only and name not in only:
            continue
        source_cfg = dict(sources_cfg.get(name, {}))
        if source_cfg.get("enabled", False):
            # Any source may opt into this (e.g. osm_places) without every
            # source needing to know about product.target_locations.
            source_cfg.setdefault("target_locations", target_locations)
            enabled.append(source_cls(source_cfg))
    return enabled
