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


class TopicDiscovery:
    def __init__(self, settings: Settings, state: StateStore):
        self.settings = settings
        self.state = state

    def discover(self, max_candidates: int = 24) -> list[TopicCandidate]:
        signals: dict[str, dict] = defaultdict(lambda: {"count": 0, "urls": [], "freshness": 0.0})
        for query in self._queries():
            for item in self._google_news(query):
                key = self._normalize(item["title"])
                if not key:
                    continue
                bucket = signals[key]
                bucket["title"] = item["title"]
                bucket["count"] += 1
                bucket["urls"].append(item["url"])
                bucket["freshness"] = max(bucket["freshness"], item["freshness"])

        recent = [self._normalize(item) for item in self.state.recent_topics()]
        preferred = set(self.state.performance_terms())
        candidates: list[TopicCandidate] = []
        for key, signal in signals.items():
            if any(self._similar(key, old) for old in recent if old):
                continue
            overlap = len(preferred.intersection(key.split()))
            score = min(100.0, 52 + signal["count"] * 7 + signal["freshness"] * 25 + overlap * 4)
            candidates.append(
                TopicCandidate(
                    title=signal["title"],
                    score=score,
                    reason=f"Fresh cross-source signal; repeated {signal['count']} time(s).",
                    source_urls=list(dict.fromkeys(signal["urls"]))[:5],
                )
            )
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:max_candidates]

    def _queries(self) -> list[str]:
        terms = list(self.settings.topic_query_list)
        terms.extend(self.state.performance_terms(limit=6))
        return list(dict.fromkeys(terms))[:10]

    def _google_news(self, query: str) -> list[dict]:
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        try:
            response = httpx.get(url, timeout=12, follow_redirects=True, headers={"User-Agent": "YouTubeAutopilot/1.0"})
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
            freshness = 0.25
            published = entry.get("published")
            if published:
                try:
                    dt = parsedate_to_datetime(published)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    hours = max(0.0, (now - dt).total_seconds() / 3600)
                    freshness = max(0.0, 1.0 - min(hours, 168) / 168)
                except (TypeError, ValueError, OverflowError):
                    pass
            items.append({"title": title, "url": str(entry.get("link", "")), "freshness": freshness})
        return items

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
