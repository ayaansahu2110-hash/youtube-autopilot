import httpx
import pytest

from autopilot.config import Settings
from autopilot.discovery import TopicDiscovery
from autopilot.research import Researcher
from autopilot.state import StateStore


RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Science</title>
<item><title>Scientists study a distant planet</title>
<link>https://example.org/planet</link>
<description>New observations of a distant planet.</description>
<source url="https://example.org">Science Publisher</source>
</item></channel></rss>"""


@pytest.mark.parametrize("component", ["discovery", "research"])
def test_downloaded_rss_produces_source_entries(monkeypatch, tmp_path, component):
    # Exercise the real feedparser API: mocking the parser hid empty-feed failures.
    monkeypatch.setattr(
        httpx, "get", lambda *args, **kwargs: httpx.Response(
            200, text=RSS, request=httpx.Request("GET", "https://example.org/feed")
        )
    )
    settings = Settings(state_file=tmp_path / "history.json")
    if component == "discovery":
        entries = TopicDiscovery(settings, StateStore(settings.state_file))._rss_search(
            "https://example.org/feed"
        )
    else:
        entries = Researcher(settings)._parse_rss("https://example.org/feed", "planet")
    assert len(entries) == 1
    assert entries[0]["title"] == "Scientists study a distant planet"
    assert entries[0]["url"] == "https://example.org/planet"


def test_rss_network_failure_remains_recoverable(monkeypatch, tmp_path):
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("feed unavailable")

    monkeypatch.setattr(httpx, "get", unavailable)
    settings = Settings(state_file=tmp_path / "history.json")
    assert Researcher(settings)._parse_rss("https://example.org/feed", "planet") == []
