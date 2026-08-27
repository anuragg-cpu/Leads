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
