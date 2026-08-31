"""Tests for the ntfy notification helper (no real network)."""

import pytest

from abhayleads import notify


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_send_ntfy_posts_to_topic_url(monkeypatch):
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr("abhayleads.notify.requests.post", fake_post)

    notify.send_ntfy("my-topic", "12 new leads", title="Abhay Leads")

    assert captured["url"] == "https://ntfy.sh/my-topic"
    assert captured["data"] == b"12 new leads"
    assert captured["headers"]["Title"] == "Abhay Leads"


def test_send_ntfy_uses_custom_base_url(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "abhayleads.notify.requests.post",
        lambda url, data=None, headers=None, timeout=None: captured.update(url=url) or FakeResponse(),
    )

    notify.send_ntfy("my-topic", "hello", base_url="https://ntfy.example.com/")

    assert captured["url"] == "https://ntfy.example.com/my-topic"


def test_send_ntfy_requires_a_topic():
    with pytest.raises(ValueError):
        notify.send_ntfy("", "hello")


def test_send_ntfy_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(
        "abhayleads.notify.requests.post",
        lambda url, data=None, headers=None, timeout=None: FakeResponse(status_code=500),
    )

    with pytest.raises(RuntimeError):
        notify.send_ntfy("my-topic", "hello")


def test_send_ntfy_strips_non_ascii_title_instead_of_crashing(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "abhayleads.notify.requests.post",
        lambda url, data=None, headers=None, timeout=None: captured.update(headers=headers) or FakeResponse(),
    )

    notify.send_ntfy("my-topic", "hello", title="Café Leads")

    # Must not raise, and the header value must be pure ASCII.
    captured["headers"]["Title"].encode("ascii")
