import re
from urllib.parse import quote_plus, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

from autopilot.config import Settings
from autopilot.models import ResearchPack, ResearchSource, TopicCandidate


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"
    )
}


class Researcher:
    def __init__(self, settings: Settings):
        self.settings = settings

    def research(self, candidate: TopicCandidate) -> ResearchPack:
        sources: list[ResearchSource] = []
        seen_urls: set[str] = set()
        seen_publishers: set[str] = set()

        # Preserve primary discovery evidence before news aggregators can fill
        # the source budget with secondary coverage.
        if self.settings.channel_profile == "curioaxiom":
            for url in candidate.source_urls[:5]:
                self._append_url_source(sources, seen_urls, seen_publishers, candidate.title, url)

        # Search more than one public news endpoint because hosted runners can
        # occasionally be rate-limited or blocked by an individual provider.
        for item in self._news_entries(candidate.title):
            self._append_entry(sources, seen_urls, seen_publishers, item)
            if len(sources) >= 5:
                break

        # Preserve the discovery evidence and fetch the original pages. Only
        # count sources with useful text so the production quality gate cannot
        # be satisfied by empty URLs alone.
        for url in candidate.source_urls:
            if len(sources) >= 5:
                break
            self._append_url_source(sources, seen_urls, seen_publishers, candidate.title, url)

        # New developer tools are often first announced as a GitHub repository
        # before they receive independent press coverage. When that happens,
        # GitHub's public repository metadata can point us to the project's
        # official homepage/docs, giving the script a second substantive page
        # to cross-check capabilities, pricing and licensing details.
        if len(sources) < self.settings.min_research_sources:
            github_urls = [source.url for source in sources if "github.com" in urlparse(source.url).netloc]
            github_urls.extend(url for url in candidate.source_urls if "github.com" in urlparse(url).netloc)
            for github_url in dict.fromkeys(github_urls):
                companion = self._github_homepage_entry(github_url)
                if companion:
                    self._append_entry(sources, seen_urls, seen_publishers, companion)
                if len(sources) >= self.settings.min_research_sources:
                    break

        # A final public no-key fallback searches Hacker News for related recent
        # stories and then reads the linked original pages. This is discovery
        # evidence, not a substitute for factual verification.
        if self.settings.channel_profile != "curioaxiom" and len(sources) < self.settings.min_research_sources:
            for item in self._hacker_news_entries(candidate.title):
                self._append_entry(sources, seen_urls, seen_publishers, item)
                if len(sources) >= 5:
                    break

        notes = "\n\n".join(
            f"SOURCE {index + 1}: {source.publisher or 'Unknown'} — {source.title}\n{source.snippet[:1500]}"
            for index, source in enumerate(sources)
        )
        return ResearchPack(topic=candidate.title, sources=sources, research_notes=notes)

    def _append_entry(
        self,
        sources: list[ResearchSource],
        seen_urls: set[str],
        seen_publishers: set[str],
        item: dict,
    ) -> None:
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            return
        publisher = str(item.get("publisher") or urlparse(url).netloc).strip()
        publisher_key = publisher.lower()
        if publisher_key and publisher_key in seen_publishers:
            return

        # Hosted CI runners are frequently blocked by publisher bot protection,
        # especially for news pages. Prefer full page text, but preserve a
        # substantive publisher-attributed RSS summary when the page itself is
        # unavailable. This prevents manual/boost topics from collapsing to
        # zero research sources while still requiring real text and independent
        # publishers before production can pass the quality gate.
        page_text = self._extract_page_text(url)
        summary = self._clean(str(item.get("summary") or ""))
        snippet = self._clean(page_text) if page_text else summary
        minimum_length = 120 if page_text else 80
        if len(snippet) < minimum_length:
            return

        seen_urls.add(url)
        if publisher_key:
            seen_publishers.add(publisher_key)
        sources.append(
            ResearchSource(
                title=str(item.get("title") or "Source"),
                url=url,
                publisher=publisher,
                published_at=item.get("published"),
                snippet=snippet[:5000],
            )
        )

    def _append_url_source(
        self,
        sources: list[ResearchSource],
        seen_urls: set[str],
        seen_publishers: set[str],
        title: str,
        url: str,
    ) -> None:
        url = str(url or "").strip()
        if not url or url in seen_urls:
            return
        publisher = urlparse(url).netloc.strip()
        publisher_key = publisher.lower()
        if publisher_key and publisher_key in seen_publishers:
            return
        snippet = self._clean(self._extract_page_text(url))
        if len(snippet) < 120:
            return
        seen_urls.add(url)
        if publisher_key:
            seen_publishers.add(publisher_key)
        sources.append(
            ResearchSource(
                title=title,
                url=url,
                publisher=publisher,
                snippet=snippet[:5000],
            )
        )

    def _news_entries(self, topic: str) -> list[dict]:
        # Full editorial topic sentences are poor search queries and can yield
        # zero RSS results. Search both a compact entity/keyword query and the
        # original wording, de-duplicating results across providers.
        queries = self._search_queries(topic)
        entries: list[dict] = []
        seen: set[str] = set()
        for query in queries:
            urls = [
                f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en",
                f"https://www.bing.com/news/search?q={quote_plus(query)}&format=rss",
            ]
            for url in urls:
                for item in self._parse_rss(url, topic):
                    key = str(item.get("url") or "")
                    if key and key not in seen:
                        seen.add(key)
                        entries.append(item)
                if len(entries) >= 20:
                    break
            if len(entries) >= 20:
                break
        return entries[:20]

    @staticmethod
    def _search_queries(topic: str) -> list[str]:
        words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]*", topic)
        stop = {
            "about", "after", "and", "are", "could", "for", "from", "how", "its",
            "new", "now", "plans", "the", "their", "this", "to", "users", "what",
            "why", "with", "would", "means", "doing", "changes",
        }
        important = [word for word in words if len(word) >= 3 and word.lower() not in stop]
        compact = " ".join(important[:8]).strip()
        original = re.sub(r"\s+", " ", topic).strip()
        queries: list[str] = []
        for query in (compact, original):
            if query and query not in queries:
                queries.append(query)
        return queries or [topic]

    def _parse_rss(self, url: str, topic: str) -> list[dict]:
        try:
            response = httpx.get(
                url,
                timeout=15,
                follow_redirects=True,
                headers=_BROWSER_HEADERS,
            )
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

    def _hacker_news_entries(self, topic: str) -> list[dict]:
        # Keep the query compact; headline-like full sentences often return no
        # Algolia matches even when the underlying subject is active.
        words = [word for word in re.findall(r"[A-Za-z0-9]+", topic) if len(word) >= 3]
        query = " ".join(words[:6]) or topic
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

        entries: list[dict] = []
        for hit in hits:
            original = str(hit.get("url") or "").strip()
            if not original:
                continue
            entries.append(
                {
                    "title": str(hit.get("title") or topic),
                    "url": original,
                    "publisher": urlparse(original).netloc,
                    "published": hit.get("created_at"),
                    "summary": "",
                }
            )
        return entries

    @staticmethod
    def _github_homepage_entry(repo_url: str) -> dict | None:
        parsed = urlparse(repo_url)
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            return None
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            return None
        owner, repo = parts[0], parts[1].removesuffix(".git")
        try:
            response = httpx.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                timeout=12,
                follow_redirects=True,
                headers={**_BROWSER_HEADERS, "Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            return None

        homepage = str(data.get("homepage") or "").strip()
        if not homepage.startswith(("http://", "https://")):
            return None
        homepage_domain = urlparse(homepage).netloc.lower()
        if not homepage_domain or "github.com" in homepage_domain:
            return None
        return {
            "title": str(data.get("name") or repo) + " official website",
            "url": homepage,
            "publisher": homepage_domain,
            "published": None,
            "summary": str(data.get("description") or ""),
        }

    @staticmethod
    def _extract_page_text(url: str) -> str:
        if not url:
            return ""
        try:
            response = httpx.get(
                url,
                timeout=15,
                follow_redirects=True,
                headers=_BROWSER_HEADERS,
            )
            response.raise_for_status()
            if "text/html" not in response.headers.get("content-type", ""):
                return ""
            soup = BeautifulSoup(response.text, "html.parser")
            for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
                element.decompose()
            paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            # Some product landing pages rely on headings/list items rather than
            # long paragraphs. Include those only when paragraph extraction is
            # too sparse so a legitimate official page can still be evaluated.
            if sum(len(text) for text in paragraphs) < 300:
                extras = [
                    node.get_text(" ", strip=True)
                    for node in soup.find_all(["h1", "h2", "h3", "li"])
                ]
                paragraphs.extend(extras)
            return "\n".join(text for text in paragraphs if len(text) >= 30)[:12000]
        except Exception:
            return ""

    @staticmethod
    def _clean(text: str) -> str:
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
        return re.sub(r"\s+", " ", text).strip()
