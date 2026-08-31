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

Note: the public Overpass API mirrors are, in practice, unreliable -
verified independently from two different networks (this happens to
everyone, not something specific to your connection). When every mirror
fails, this source reports the error and moves on rather than hanging;
see "If osm_places keeps failing" in docs/SOURCES.md for what to do
about it (mainly: try again later, or run the same query manually at
https://overpass-turbo.eu/ as a one-off).
"""

import json
import time
from pathlib import Path
from typing import Any, Iterator, Optional

import requests

from ..config import default_paths
from ..models import LeadCandidate
from .base import USER_AGENT, BaseLeadSource

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Mirrors tried in order, each with a short timeout - if one is
# unreachable/overloaded, fail fast and try the next rather than sitting
# on one slow request for a long time.
#
# Only overpass-api.de (the reference instance) and overpass.kumi.systems
# are listed - both are well-established public mirrors. Others tried and
# rejected: overpass.osm.ch returns HTTP 200 with a valid-looking but
# empty/stale dataset (silently wrong, worse than an error - don't add it
# back without verifying its osm3s.timestamp_osm_base is current);
# overpass.openstreetmap.fr requires pre-arranged IP whitelisting and
# 403s everyone else.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
OVERPASS_TIMEOUT_SECONDS = 20

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

    def fetch(self, keywords: list[str]) -> Iterator[LeadCandidate]:
        # Location/category driven, not free-text search - keywords unused.
        localities = self.source_config.get("target_locations", []) or []
        if not localities:
            return

        categories = self.source_config.get("categories") or list(CATEGORY_FILTERS)
        radius = self.source_config.get("radius_meters", 3000)
        max_localities = self.source_config.get("max_localities", 20)

        _, app_data_dir = default_paths()
        cache_path = app_data_dir / GEOCODE_CACHE_FILENAME
        cache = _load_geocode_cache(cache_path)

        seen_urls: set[str] = set()
        localities = localities[:max_localities]
        total = len(localities)

        for i, locality in enumerate(localities, start=1):
            point = cache.get(locality)
            if point is None:
                self.progress_callback(f"osm_places: {locality} ({i}/{total}) - geocoding...")
                point = self._geocode(locality)
                time.sleep(1.1)  # Nominatim usage policy: max 1 request/second
                if point is None:
                    self.progress_callback(f"osm_places: {locality} ({i}/{total}) - couldn't geocode, skipping")
                    continue
                cache[locality] = point
                _save_geocode_cache(cache_path, cache)

            self.progress_callback(f"osm_places: {locality} ({i}/{total}) - querying Overpass...")
            try:
                elements = self._query_overpass(point, radius, categories)
            except Exception as exc:  # noqa: BLE001 - one locality's failure shouldn't lose the rest
                self.warnings.append(f"{locality}: Overpass query failed - {exc}")
                self.progress_callback(f"osm_places: {locality} ({i}/{total}) - failed, skipping")
                time.sleep(1)
                continue

            # OSM sometimes maps one real building/complex as two overlapping
            # elements (a way plus a duplicate node, common data-entry slip).
            # Collapse exact same-name repeats within this locality's batch -
            # deliberately NOT fuzzy: "Prakrtii CHS G Block" and "...F Block"
            # are kept as separate leads since they're genuinely different
            # named entities that may need separate outreach.
            seen_names_this_locality: set[str] = set()
            found_this_locality = 0
            for element, label in elements:
                candidate = self._element_to_candidate(element, locality, label)
                if candidate is None or candidate.source_detail in seen_urls:
                    continue
                name_key = candidate.company.strip().lower()
                if name_key in seen_names_this_locality:
                    continue
                seen_names_this_locality.add(name_key)
                seen_urls.add(candidate.source_detail)
                found_this_locality += 1
                yield candidate

            self.progress_callback(
                f"osm_places: {locality} ({i}/{total}) - found {found_this_locality}, saved"
            )
            time.sleep(1)

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
                resp = requests.post(
                    url,
                    data={"data": query},
                    headers={"User-Agent": USER_AGENT},
                    timeout=OVERPASS_TIMEOUT_SECONDS,
                )
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as exc:  # noqa: BLE001 - try the next mirror
                last_error = exc
                self.progress_callback(f"osm_places: {url} timed out/failed, trying next mirror...")
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
