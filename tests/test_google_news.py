"""Tests for query construction in the google_news source (no real network)."""

from abhayleads.sources.google_news import GoogleNewsSource


class FakeResponse:
    def __init__(self):
        self.content = b"<?xml version='1.0'?><rss><channel></channel></rss>"

    def raise_for_status(self):
        pass


def _capture_urls(monkeypatch):
    captured = []

    def fake_get(url, headers=None, timeout=None):
        captured.append(url)
        return FakeResponse()

    monkeypatch.setattr("abhayleads.sources.google_news.requests.get", fake_get)
    return captured


def test_fetch_defaults_to_us_edition_with_no_suffix(monkeypatch):
    captured = _capture_urls(monkeypatch)
    GoogleNewsSource({}).fetch(["panic button system"])

    assert len(captured) == 1
    url = captured[0]
    assert "hl=en-US" in url
    assert "gl=US" in url
    assert "panic+button+system" in url
    assert "India" not in url


def test_fetch_applies_configured_query_suffix_and_edition(monkeypatch):
    captured = _capture_urls(monkeypatch)
    source = GoogleNewsSource(
        {
            "query_suffix": "India",
            "edition": {"hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
        }
    )
    source.fetch(["panic button system"])

    url = captured[0]
    assert "hl=en-IN" in url
    assert "gl=IN" in url
    assert "panic+button+system+India" in url


def test_query_suffix_does_not_touch_the_keyword_itself(monkeypatch):
    # The suffix changes what's searched for, not what scoring later
    # matches against - keywords passed to fetch() must stay untouched.
    captured = []

    def fake_get(url, headers=None, timeout=None):
        captured.append(url)
        return FakeResponse()

    monkeypatch.setattr("abhayleads.sources.google_news.requests.get", fake_get)

    keywords = ["panic button system"]
    GoogleNewsSource({"query_suffix": "India"}).fetch(keywords)

    assert keywords == ["panic button system"]
