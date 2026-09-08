import requests

from abhayleads.google_maps_link import parse_google_maps_link, split_links


class FakeResponse:
    def __init__(self, url):
        self.url = url


def test_split_links_one_per_line():
    text = "https://maps.app.goo.gl/aaa\nhttps://maps.app.goo.gl/bbb\nhttps://maps.app.goo.gl/ccc"
    assert split_links(text) == [
        "https://maps.app.goo.gl/aaa",
        "https://maps.app.goo.gl/bbb",
        "https://maps.app.goo.gl/ccc",
    ]


def test_split_links_ignores_blank_lines_and_non_urls():
    text = "https://maps.app.goo.gl/aaa\n\nnot a url\n   \nhttps://maps.app.goo.gl/bbb"
    assert split_links(text) == ["https://maps.app.goo.gl/aaa", "https://maps.app.goo.gl/bbb"]


def test_split_links_drops_exact_duplicates_keeping_first_order():
    text = "https://maps.app.goo.gl/aaa\nhttps://maps.app.goo.gl/bbb\nhttps://maps.app.goo.gl/aaa"
    assert split_links(text) == ["https://maps.app.goo.gl/aaa", "https://maps.app.goo.gl/bbb"]


def test_split_links_single_link_returns_one_item_list():
    assert split_links("  https://maps.app.goo.gl/aaa  ") == ["https://maps.app.goo.gl/aaa"]


def test_split_links_empty_text_returns_empty_list():
    assert split_links("") == []
    assert split_links("   \n  \n") == []


def test_extracts_company_and_precise_point_when_present(monkeypatch):
    url = (
        "https://www.google.com/maps/place/Ruby+Hall+Clinic/@18.5308123,73.8747456,17z/"
        "data=!3m1!4b1!4m6!3m5!1s0x3bc2c05f1234:0xabc!8m2!3d18.5308!4d73.8747!16s%2Fg%2F1234"
    )
    monkeypatch.setattr("abhayleads.google_maps_link.requests.head", lambda *a, **k: FakeResponse(url))

    parsed = parse_google_maps_link(url)

    assert parsed.company == "Ruby Hall Clinic"
    assert parsed.lat == 18.5308
    assert parsed.lon == 73.8747  # the precise !3d/!4d point, not the @ view-center
    assert parsed.url == url


def test_falls_back_to_view_center_when_no_precise_point(monkeypatch):
    url = "https://www.google.com/maps/place/Prakrtii+CHS+G+Block/@18.5599,73.7799,16z"
    monkeypatch.setattr("abhayleads.google_maps_link.requests.head", lambda *a, **k: FakeResponse(url))

    parsed = parse_google_maps_link(url)

    assert parsed.company == "Prakrtii CHS G Block"
    assert parsed.lat == 18.5599
    assert parsed.lon == 73.7799


def test_url_decodes_and_despaces_multiword_names(monkeypatch):
    url = "https://www.google.com/maps/place/Joe%27s+Pizza+%26+Grill/@1.0,2.0,15z"
    monkeypatch.setattr("abhayleads.google_maps_link.requests.head", lambda *a, **k: FakeResponse(url))

    parsed = parse_google_maps_link(url)

    assert parsed.company == "Joe's Pizza & Grill"


def test_cid_only_link_yields_no_name_or_coordinates(monkeypatch):
    url = "https://www.google.com/maps?cid=12345678901234567890"
    monkeypatch.setattr("abhayleads.google_maps_link.requests.head", lambda *a, **k: FakeResponse(url))

    parsed = parse_google_maps_link(url)

    assert parsed.company == ""
    assert parsed.lat is None
    assert parsed.lon is None
    assert parsed.url == url


def test_plain_map_view_yields_coordinates_but_no_name(monkeypatch):
    url = "https://www.google.com/maps/@18.52,73.85,15z"
    monkeypatch.setattr("abhayleads.google_maps_link.requests.head", lambda *a, **k: FakeResponse(url))

    parsed = parse_google_maps_link(url)

    assert parsed.company == ""
    assert parsed.lat == 18.52
    assert parsed.lon == 73.85


def test_short_link_gets_resolved_via_redirect_before_parsing(monkeypatch):
    short_url = "https://maps.app.goo.gl/abcXYZ"
    long_url = "https://www.google.com/maps/place/Test+Dealer/@1.5,2.5,17z"

    def fake_head(url, **kwargs):
        assert url == short_url  # the short link is what actually gets requested
        return FakeResponse(long_url)

    monkeypatch.setattr("abhayleads.google_maps_link.requests.head", fake_head)

    parsed = parse_google_maps_link(short_url)

    assert parsed.url == long_url  # resolved, not the pasted short link
    assert parsed.company == "Test Dealer"
    assert parsed.lat == 1.5
    assert parsed.lon == 2.5


def test_network_failure_falls_back_to_parsing_the_pasted_url_as_is(monkeypatch):
    url = "https://www.google.com/maps/place/Offline+Test/@3.0,4.0,15z"

    def fake_head(*a, **k):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr("abhayleads.google_maps_link.requests.head", fake_head)

    parsed = parse_google_maps_link(url)

    assert parsed.company == "Offline Test"
    assert parsed.lat == 3.0
    assert parsed.url == url


def test_strips_leading_trailing_whitespace_from_pasted_link(monkeypatch):
    url = "https://www.google.com/maps/place/Trimmed/@1.0,1.0,15z"
    monkeypatch.setattr("abhayleads.google_maps_link.requests.head", lambda *a, **k: FakeResponse(url))

    parsed = parse_google_maps_link(f"  {url}  \n")

    assert parsed.company == "Trimmed"
