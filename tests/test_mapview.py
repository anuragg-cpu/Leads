"""Tests for the map-rendering helpers shared by the server's /map page
and the desktop GUI's standalone Map window."""

import json

from abhayleads.mapview import (
    STAGE_COLORS,
    leads_to_map_points,
    render_standalone_map_html,
    safe_json_for_script,
)


def test_leads_to_map_points_extracts_expected_fields():
    leads = [
        {
            "id": 1,
            "lat": 18.5,
            "lon": 73.8,
            "company": "Ruby Hall Clinic",
            "contact_name": "",
            "title": "Hospital",
            "stage": "New",
            "score": 70,
            "source": "osm_places",
        }
    ]
    points = leads_to_map_points(leads)
    assert points == [
        {"id": 1, "lat": 18.5, "lon": 73.8, "company": "Ruby Hall Clinic", "title": "Hospital", "stage": "New", "score": 70}
    ]


def test_leads_to_map_points_falls_back_to_contact_name_then_source_for_company():
    leads = [
        {
            "id": 1,
            "lat": 1.0,
            "lon": 2.0,
            "company": "",
            "contact_name": "Jane Doe",
            "title": "",
            "stage": "New",
            "score": 10,
            "source": "manual",
        },
        {
            "id": 2,
            "lat": 1.0,
            "lon": 2.0,
            "company": "",
            "contact_name": "",
            "title": "",
            "stage": "New",
            "score": 10,
            "source": "manual",
        },
    ]
    points = leads_to_map_points(leads)
    assert points[0]["company"] == "Jane Doe"
    assert points[1]["company"] == "manual"


def test_safe_json_for_script_escapes_script_breakout_characters():
    encoded = safe_json_for_script({"company": "</script><script>alert(1)</script>"})
    assert "</script>" not in encoded
    assert json.loads(encoded.replace("\\u003c", "<").replace("\\u003e", ">")) == {
        "company": "</script><script>alert(1)</script>"
    }


def test_render_standalone_map_html_empty_state_when_no_points():
    html = render_standalone_map_html([])
    assert "No leads with a map location yet" in html
    assert "leads-map" not in html  # no map div or script should render
    assert "unpkg.com" not in html  # shouldn't load Leaflet for nothing


def test_render_standalone_map_html_embeds_points_and_stage_colors():
    points = [{"id": 1, "lat": 18.5, "lon": 73.8, "company": "Acme", "title": "", "stage": "New", "score": 50}]
    html = render_standalone_map_html(points)
    assert "id=\"leads-map\"" in html
    assert '"company": "Acme"' in html
    assert json.dumps(STAGE_COLORS) in html
    assert "leadUrlBase = null" in html


def test_render_standalone_map_html_includes_lead_link_when_remote_base_url_given():
    points = [{"id": 7, "lat": 1.0, "lon": 2.0, "company": "Acme", "title": "", "stage": "New", "score": 50}]
    html = render_standalone_map_html(points, lead_url_base="https://example.ts.net/")
    assert 'leadUrlBase = "https://example.ts.net"' in html  # trailing slash stripped


def test_render_standalone_map_html_escapes_company_name_to_avoid_breaking_out_of_script_tag():
    points = [{"id": 1, "lat": 1.0, "lon": 2.0, "company": "</script><script>alert(1)</script>", "title": "", "stage": "New", "score": 1}]
    html = render_standalone_map_html(points)
    assert "</script><script>alert(1)" not in html
