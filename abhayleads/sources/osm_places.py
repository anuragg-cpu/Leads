"""OpenStreetMap-based account discovery for local B2B sales.

Unlike the other sources (which search for someone publicly describing a
problem), this one is for products sold to a specific *kind of place* in
a specific *area* - hospitals, co-working spaces, campuses, housing
societies, etc. It doesn't find "signal", it builds a canvassing list:
named places matching your categories within a radius of each of your
`product.target_locations`.

Two free, public, no-key APIs, used politely and within their published
usage policies:

- Nominatim (https://nominatim.org/release-docs/latest/api/Search/) to
  turn a locality name into coordinates - capped at 1 request/second,
  and the result is cached to disk so each locality is only geocoded
  once, ever.
- Overpass API (https://wiki.openstreetmap.org/wiki/Overpass_API) to
  query OpenStreetMap for named places matching your categories within
  `radius_meters` of that point.

Note: this was written and reviewed for correctness, but this session's
sandboxed network could not get a live response from any public Overpass
mirror (connection resets/timeouts on every one tried - consistent with
those instances blocking cloud/datacenter IP ranges, a known issue for
this specific API). Nominatim geocoding *was* verified live. Please
confirm this source returns results the first time you run it from your
own machine.
"""

import json
import time
from pathlib import Path
from typing import Any, Optional

import requests

from ..config import default_paths
from ..models import LeadCandidate
from .base import USER_AGENT, BaseLeadSource

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Mirrors tried in order - if the first is unreachable/rate-limited, fall
# back to the next rather than failing the whole fetch.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# category name -> list of (osm_key, osm_value, human label) to search for.
CATEGORY_FILTERS: dict[str, list[tuple[str, str, str]]] = {
    "hospital": [("amenity", "hospital", "Hospital")],
    "coworking": [("office", "coworking", "Co-working space")],
    "campus": [
        ("amenity", "university", "University campus"),
        ("amenity", "college", "College campus"),
    ],
    "residential": [("building", "apartments", "Housing society / apartment complex")],
}

GEOCODE_CACHE_FILENAME = "osm_geocode_cache.json"


def _load_geocode_cache(cache_path: Path) -> dict[str, dict[str, float]]:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_geocode_cache(cache_path: Path, cache: dict[str, dict[str, float]]):
    cache_path.write_text(json.dumps(cache, indent=2))


class OSMPlacesSource(BaseLeadSource):
    name = "osm_places"

    def fetch(self, keywords: list[str]) -> list[LeadCandidate]:
        # Location/category driven, not free-text search - keywords unused.
        localities = self.source_config.get("target_locations", []) or []
        if not localities:
            return []

        categories = self.source_config.get("categories") or list(CATEGORY_FILTERS)
        radius = self.source_config.get("radius_meters", 3000)
        max_localities = self.source_config.get("max_localities", 20)

        _, app_data_dir = default_paths()
        cache_path = app_data_dir / GEOCODE_CACHE_FILENAME
        cache = _load_geocode_cache(cache_path)

        candidates: list[LeadCandidate] = []
        seen_urls: set[str] = set()

        for locality in localities[:max_localities]:
            point = cache.get(locality)
            if point is None:
                point = self._geocode(locality)
                time.sleep(1.1)  # Nominatim usage policy: max 1 request/second
                if point is None:
                    continue
                cache[locality] = point
                _save_geocode_cache(cache_path, cache)

            for element, label in self._query_overpass(point, radius, categories):
                candidate = self._element_to_candidate(element, locality, label)
                if candidate is None or candidate.source_detail in seen_urls:
                    continue
                seen_urls.add(candidate.source_detail)
                candidates.append(candidate)
            time.sleep(1)

        return candidates

    def _geocode(self, locality: str) -> Optional[dict[str, float]]:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": f"{locality}, Maharashtra, India", "format": "json", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        return {"lat": float(results[0]["lat"]), "lon": float(results[0]["lon"])}

    def _query_overpass(
        self, point: dict[str, float], radius: int, categories: list[str]
    ) -> list[tuple[dict[str, Any], str]]:
        clauses = []
        for category in categories:
            for key, value, _label in CATEGORY_FILTERS.get(category, []):
                name_filter = '["name"]' if category == "residential" else ""
                clauses.append(
                    f'nwr["{key}"="{value}"]{name_filter}(around:{radius},{point["lat"]},{point["lon"]});'
                )
        if not clauses:
            return []

        query = f'[out:json][timeout:25];({"".join(clauses)});out center tags;'

        data = None
        last_error: Optional[Exception] = None
        for url in OVERPASS_URLS:
            try:
                resp = requests.post(url, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as exc:  # noqa: BLE001 - try the next mirror
                last_error = exc
                continue
        if data is None:
            raise RuntimeError(f"All Overpass endpoints failed: {last_error}")

        return [(element, self._label_for(element.get("tags", {}), categories)) for element in data.get("elements", [])]

    def _label_for(self, tags: dict[str, str], categories: list[str]) -> str:
        for category in categories:
            for key, value, label in CATEGORY_FILTERS.get(category, []):
                if tags.get(key) == value:
                    return label
        return "Place"

    def _element_to_candidate(self, element: dict[str, Any], locality: str, label: str) -> Optional[LeadCandidate]:
        tags = element.get("tags", {})
        name = tags.get("name")
        if not name:
            return None

        url = f"https://www.openstreetmap.org/{element.get('type')}/{element.get('id')}"
        address_parts = [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:suburb") or locality]
        address = ", ".join(p for p in address_parts if p)
        raw_text = f"{label} near {locality}" + (f" - {address}" if address else "")

        return LeadCandidate(
            source=self.name,
            source_detail=url,
            company=name,
            title=f"{label}: {name} ({locality})",
            url=url,
            raw_text=raw_text,
        )
