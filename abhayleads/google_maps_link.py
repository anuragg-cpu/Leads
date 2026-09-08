"""Turns a pasted Google Maps link into a lead's starting fields (company
name + coordinates), for a place/vendor you found by manually searching
Google Maps rather than through any automated source - see the GUI's Add
Lead dialog and `abhayleads add --google-maps-link`.

Deliberately narrow in what it does: follows one redirect to resolve a
shortened share link (maps.app.goo.gl / goo.gl/maps), then parses the
resulting URL's own path/query text for a name and coordinates Google
already put there in plain sight for anyone to read. It never fetches or
parses the actual Google Maps page content - that would mean scraping
Google Maps, which its terms of service prohibit and this tool doesn't
do, same principle applied to every other source in this project (see
docs/SOURCES.md).

Best-effort: a plain search-results link or a `cid=`-only link has no
name encoded in the URL at all, so `company` can come back empty - the
caller still lets you fill that in yourself, same as any other manually
added lead.
"""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote

import requests

from .sources.base import USER_AGENT

REQUEST_TIMEOUT_SECONDS = 10

_PLACE_NAME_RE = re.compile(r"/maps/place/([^/@]+)")
# A place's pinned point (precise) vs. the map's view-center (just where
# it happened to be panned/zoomed to when the link was made) - prefer the
# former when both are present.
_PRECISE_POINT_RE = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
_VIEW_CENTER_RE = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")


@dataclass
class ParsedGoogleMapsLink:
    url: str  # the resolved link, after following any short-link redirect
    company: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None


def parse_google_maps_link(url: str) -> ParsedGoogleMapsLink:
    resolved_url = _resolve_redirect(url.strip())

    company = ""
    name_match = _PLACE_NAME_RE.search(resolved_url)
    if name_match:
        company = unquote(name_match.group(1)).replace("+", " ").strip()

    lat = lon = None
    point_match = _PRECISE_POINT_RE.search(resolved_url) or _VIEW_CENTER_RE.search(resolved_url)
    if point_match:
        lat, lon = float(point_match.group(1)), float(point_match.group(2))

    return ParsedGoogleMapsLink(url=resolved_url, company=company, lat=lat, lon=lon)


def split_links(text: str) -> list[str]:
    """Splits a paste-box's worth of text into individual URLs, one per
    line (or separated by other whitespace) - for pasting several links
    at once (e.g. copied one-by-one out of a Google Maps list) instead of
    just one. Ignores blank lines and anything that isn't a URL; keeps
    first-seen order and drops exact duplicates."""
    seen: set[str] = set()
    links: list[str] = []
    for token in text.split():
        if token.startswith(("http://", "https://")) and token not in seen:
            seen.add(token)
            links.append(token)
    return links


def _resolve_redirect(url: str) -> str:
    """Follows the redirect chain to turn a shortened share link into
    Google's own long-form URL. An already-long URL just comes back
    unchanged. Never raises - a network failure (offline, blocked, a
    non-Google URL that doesn't respond) just means parsing continues
    against whatever was pasted as-is, which still works fine for an
    already-long URL and simply yields no name/coordinates for a short one."""
    try:
        resp = requests.head(
            url, allow_redirects=True, timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}
        )
        return resp.url
    except requests.RequestException:
        return url
