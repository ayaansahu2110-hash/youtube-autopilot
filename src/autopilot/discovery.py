import re
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
import httpx

from autopilot.config import Settings
from autopilot.models import TopicCandidate
from autopilot.state import StateStore


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"
    )
}


class TopicDiscovery:
    def __init__(self, settings: Settings, state: StateStore):
        self.settings = settings
        self.state = state

    def discover(self, max_candidates: int = 24) -> list[TopicCandidate]:
        signals: dict[str, dict] = defaultdict(lambda: {"count": 0, "urls": [], "freshness": 0.0})
        for query in self._queries():
            items = self._news_search(query)
            # GitHub-hosted runners can occasionally be blocked by news RSS
            # endpoints. Hacker News Algolia is a public, no-key fallback.
            if not items:
                items = self._hacker_news(query)
            for item in items:
                key = self._normalize(item["title"])
                if not key:
                    continue
                bucket = signals[key]
                bucket["title"] = item["title"]
                bucket["count"] += 1
                bucket["urls"].extend(item.get("urls") or [item.get("url", "")])
                bucket["freshness"] = max(bucket["freshness"], item["freshness"])

        recent = [self._normalize(item) for item in self.state.recent_topics()]
        preferred = set(self.state.performance_terms())
        candidates: list[TopicCandidate] = []
        for key, signal in signals.items():
            if any(self._similar(key, old) for old in recent if old):
                continue
            overlap = len(preferred.intersection(key.split()))
            score = min(100.0, 52 + signal["count"] * 7 + signal["freshness"] * 25 + overlap * 4)
            urls = [url for url in dict.fromkeys(signal["urls"]) if url]
            candidates.append(
                TopicCandidate(
                    title=signal["title"],
                    score=score,
                    reason=f"Fresh public signal; repeated {signal['count']} time(s).",
                    source_urls=urls[:5],
                )
            )
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:max_candidates]

    def _queries(self) -> list[str]:
        terms = list(self.settings.topic_query_list)
        terms.extend(self.state.performance_terms(limit=6))
        return list(dict.fromkeys(terms))[:10]

    def _news_search(self, query: str) -> list[dict]:
        items = self._rss_search(
            f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        )
        if len(items) >= 4:
            return items

        bing = self._rss_search(
            f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss"
        )
        combined: list[dict] = []
        seen: set[str] = set()
        for item in items + bing:
            key = self._normalize(item["title"])
            if key and key not in seen:
                seen.add(key)
                combined.append(item)
        return combined[:12]

    def _rss_search(self, url: str) -> list[dict]:
        try:
            response = httpx.get(url, timeout=15, follow_redirects=True, headers=_BROWSER_HEADERS)
            response.raise_for_status()
            parsed = feedparser.loads(response.text)
        except Exception:
            return []

        now = datetime.now(timezone.utc)
        items = []
        for entry in parsed.entries[:12]:
            title = re.sub(r"\s+-\s+[^-]+$", "", str(entry.get("title", ""))).strip()
            if len(title) < 12:
                continue
            freshness = self._freshness(entry.get("published"), now)
            link = str(entry.get("link", ""))
            items.append({"title": title, "url": link, "urls": [link], "freshness": freshness})
        return items

    def _hacker_news(self, query: str) -> list[dict]:
        try:
            response = httpx.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={"query": query, "tags": "story", "hitsPerPage": 12},
                timeout=15,
                follow_redirects=True,
                headers=_BROWSER_HEADERS,
            )
            response.raise_for_status()
            hits = response.json().get("hits") or []
        except Exception:
            return []

        now = datetime.now(timezone.utc)
        items: list[dict] = []
        for hit in hits:
            title = str(hit.get("title") or "").strip()
            if len(title) < 12:
                continue
            created = hit.get("created_at")
            freshness = self._iso_freshness(created, now)
            story_id = str(hit.get("objectID") or "").strip()
            original = str(hit.get("url") or "").strip()
            discussion = f"https://news.ycombinator.com/item?id={story_id}" if story_id else ""
            urls = [url for url in (original, discussion) if url]
            items.append(
                {
                    "title": title,
                    "url": original or discussion,
                    "urls": urls,
                    "freshness": freshness,
                }
            )
        return items

    @staticmethod
    def _freshness(published, now: datetime) -> float:
        freshness = 0.25
        if published:
            try:
                dt = parsedate_to_datetime(published)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                hours = max(0.0, (now - dt).total_seconds() / 3600)
                freshness = max(0.0, 1.0 - min(hours, 168) / 168)
            except (TypeError, ValueError, OverflowError):
                pass
        return freshness

    @staticmethod
    def _iso_freshness(created, now: datetime) -> float:
        if not created:
            return 0.25
        try:
            dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            hours = max(0.0, (now - dt).total_seconds() / 3600)
            return max(0.0, 1.0 - min(hours, 168) / 168)
        except (TypeError, ValueError, OverflowError):
            return 0.25

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

    @staticmethod
    def _similar(a: str, b: str) -> bool:
        if not a or not b:
            return False
        a_words, b_words = set(a.split()), set(b.split())
        union = a_words | b_words
        return bool(union) and len(a_words & b_words) / len(union) >= 0.62
