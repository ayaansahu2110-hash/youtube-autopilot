import re
from urllib.parse import quote_plus, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from autopilot.config import Settings
from autopilot.models import ResearchPack, ResearchSource, TopicCandidate


class Researcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    def research(self, candidate: TopicCandidate) -> ResearchPack:
        sources: list[ResearchSource] = []
        seen_publishers: set[str] = set()

        for item in self._news_entries(candidate.title):
            publisher = item.get("publisher") or urlparse(item["url"]).netloc
            publisher_key = publisher.lower().strip()
            if publisher_key in seen_publishers:
                continue
            seen_publishers.add(publisher_key)
            snippet = self._extract_page_text(item["url"]) or item.get("summary", "")
            sources.append(
                ResearchSource(
                    title=item["title"],
                    url=item["url"],
                    publisher=publisher,
                    published_at=item.get("published"),
                    snippet=self._clean(snippet)[:5000],
                )
            )
            if len(sources) >= 5:
                break

        if not sources:
            for url in candidate.source_urls[:3]:
                sources.append(ResearchSource(title=candidate.title, url=url, snippet="Demand signal only; verify claims."))

        notes = "\n\n".join(
            f"SOURCE {index + 1}: {source.publisher or 'Unknown'} — {source.title}\n{source.snippet[:1500]}"
            for index, source in enumerate(sources)
        )
        return ResearchPack(topic=candidate.title, sources=sources, research_notes=notes)

    def _news_entries(self, topic: str) -> list[dict]:
        url = f"https://news.google.com/rss/search?q={quote_plus(topic)}&hl=en-US&gl=US&ceid=US:en"
        try:
            response = httpx.get(url, timeout=12, follow_redirects=True, headers={"User-Agent": "YouTubeAutopilot/1.0"})
            response.raise_for_status()
            parsed = feedparser.loads(response.text)
        except Exception:
            return []

        entries = []
        for entry in parsed.entries[:10]:
            publisher = None
            source = entry.get("source")
            if isinstance(source, dict):
                publisher = source.get("title")
            entries.append(
                {
                    "title": str(entry.get("title", topic)),
                    "url": str(entry.get("link", "")),
                    "publisher": publisher,
                    "published": entry.get("published"),
                    "summary": str(entry.get("summary", "")),
                }
            )
        return entries

    @staticmethod
    def _extract_page_text(url: str) -> str:
        if not url:
            return ""
        try:
            response = httpx.get(url, timeout=12, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 YouTubeAutopilot/1.0"})
            response.raise_for_status()
            if "text/html" not in response.headers.get("content-type", ""):
                return ""
            soup = BeautifulSoup(response.text, "html.parser")
            for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
                element.decompose()
            paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            return "\n".join(text for text in paragraphs if len(text) >= 40)[:12000]
        except Exception:
            return ""

    @staticmethod
    def _clean(text: str) -> str:
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
        return re.sub(r"\s+", " ", text).strip()
