"""Tests for the pure (non-network) parts of the osm_places source."""

from abhayleads.sources.osm_places import OSMPlacesSource


def make_source(**overrides):
    config = {"target_locations": ["Baner"], "categories": ["hospital", "residential"]}
    config.update(overrides)
    return OSMPlacesSource(config)


def test_label_for_matches_configured_category():
    source = make_source()
    label = source._label_for({"amenity": "hospital"}, ["hospital", "residential"])
    assert label == "Hospital"


def test_label_for_falls_back_to_place_when_unmatched():
    source = make_source()
    label = source._label_for({"shop": "bakery"}, ["hospital"])
    assert label == "Place"


def test_element_to_candidate_builds_expected_fields():
    source = make_source()
    element = {
        "type": "way",
        "id": 12345,
        "tags": {
            "name": "Ruby Hall Clinic",
            "addr:street": "Sassoon Road",
        },
    }
    candidate = source._element_to_candidate(element, "Baner", "Hospital")

    assert candidate is not None
    assert candidate.company == "Ruby Hall Clinic"
    assert candidate.source == "osm_places"
    assert candidate.url == "https://www.openstreetmap.org/way/12345"
    assert candidate.source_detail == candidate.url
    assert "Hospital" in candidate.title
    assert "Ruby Hall Clinic" in candidate.title
    assert "Baner" in candidate.title
    assert "Sassoon Road" in candidate.raw_text


def test_element_to_candidate_skips_unnamed_places():
    source = make_source()
    element = {"type": "node", "id": 999, "tags": {}}
    assert source._element_to_candidate(element, "Baner", "Hospital") is None


def test_fetch_returns_empty_without_target_locations():
    source = OSMPlacesSource({"target_locations": []})
    assert source.fetch(keywords=[]) == []


def test_fetch_keeps_results_from_other_localities_when_one_fails(tmp_path, monkeypatch):
    # Regression test: a single locality's Overpass failure used to raise
    # out of fetch() entirely, silently discarding every candidate already
    # found for earlier localities and never even trying the later ones.
    monkeypatch.setattr(
        "abhayleads.sources.osm_places.default_paths",
        lambda: (tmp_path / "config", tmp_path),
    )
    monkeypatch.setattr("abhayleads.sources.osm_places.time.sleep", lambda *_: None)

    source = OSMPlacesSource({"target_locations": ["Baner", "Pune"], "categories": ["hospital"]})
    monkeypatch.setattr(source, "_geocode", lambda locality: {"lat": 1.0, "lon": 2.0})

    calls = {"n": 0}

    def fake_query_overpass(point, radius, categories):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("All Overpass endpoints failed: boom")
        return [({"type": "node", "id": 1, "tags": {"name": "Test Hospital"}}, "Hospital")]

    monkeypatch.setattr(source, "_query_overpass", fake_query_overpass)

    candidates = source.fetch(keywords=[])

    assert len(candidates) == 1
    assert candidates[0].company == "Test Hospital"
    assert len(source.warnings) == 1
    assert "Baner" in source.warnings[0]


def test_fetch_collapses_exact_same_name_within_one_locality(tmp_path, monkeypatch):
    # Regression test: OSM sometimes maps one real building as two
    # elements (e.g. a duplicate node), which used to show up as two
    # identical leads in the CRM.
    monkeypatch.setattr(
        "abhayleads.sources.osm_places.default_paths",
        lambda: (tmp_path / "config", tmp_path),
    )
    monkeypatch.setattr("abhayleads.sources.osm_places.time.sleep", lambda *_: None)

    source = OSMPlacesSource({"target_locations": ["Baner"], "categories": ["residential"]})
    monkeypatch.setattr(source, "_geocode", lambda locality: {"lat": 1.0, "lon": 2.0})
    monkeypatch.setattr(
        source,
        "_query_overpass",
        lambda point, radius, categories: [
            ({"type": "way", "id": 1, "tags": {"name": "Prakrtii CHS G Block"}}, "Housing society"),
            ({"type": "node", "id": 2, "tags": {"name": "Prakrtii CHS G Block"}}, "Housing society"),
            ({"type": "way", "id": 3, "tags": {"name": "Prakrtii CHS F Block"}}, "Housing society"),
        ],
    )

    candidates = source.fetch(keywords=[])

    names = sorted(c.company for c in candidates)
    assert names == ["Prakrtii CHS F Block", "Prakrtii CHS G Block"]
