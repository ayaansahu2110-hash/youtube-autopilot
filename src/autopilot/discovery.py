import re
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser
import httpx

from autopilot.config import Settings
from autopilot.editorial import editorial_system_for
from autopilot.models import TopicCandidate
from autopilot.state import StateStore


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"
    )
}

CHANNEL_EVERGREEN_TOPICS: dict[str, list[dict]] = {
    "wondertales": [
        {
            "title": "Five Little Ducklings Splashing in the Lake",
            "urls": ["https://en.wikipedia.org/wiki/Five_Little_Ducks", "https://en.wikipedia.org/wiki/Nursery_rhyme"],
            "score": 96.0,
            "reason": "Classic musical counting song and bouncy singing poem with adorable fluffy ducklings.",
        },
        {
            "title": "The Playful Puppy Who Chased the Rainbow",
            "urls": ["https://en.wikipedia.org/wiki/Children%27s_poetry", "https://en.wikipedia.org/wiki/Fable"],
            "score": 95.0,
            "reason": "Joyful rhyming animal poem with wagging puppy and bright rainbow colors.",
        },
        {
            "title": "The Cheerful Kitten and the Golden Yarn Ball",
            "urls": ["https://en.wikipedia.org/wiki/Nursery_rhyme", "https://en.wikipedia.org/wiki/Moral"],
            "score": 94.0,
            "reason": "Playful singing kitten adventure with purring and bouncing yarn rhymes.",
        },
        {
            "title": "The Busy Little Bee Making Sweet Honey",
            "urls": ["https://en.wikipedia.org/wiki/Children%27s_literature", "https://en.wikipedia.org/wiki/Fable"],
            "score": 93.0,
            "reason": "Buzz-buzz musical preschool song about flowers, teamwork, and sweet treats.",
        },
        {
            "title": "Hop Little Froggie on the Green Lily Pad",
            "urls": ["https://en.wikipedia.org/wiki/Nursery_rhyme", "https://en.wikipedia.org/wiki/Children%27s_poetry"],
            "score": 92.0,
            "reason": "Croak-croak jumping rhythm poem that toddlers love to bounce and hop along with.",
        },
        {
            "title": "The Tiny Green Caterpillar That Learned to Fly",
            "urls": ["https://en.wikipedia.org/wiki/The_Very_Hungry_Caterpillar", "https://en.wikipedia.org/wiki/Fable"],
            "score": 95.0,
            "reason": "Magical rhyming transformation fable from crawling caterpillar to colorful butterfly.",
        },
        {
            "title": "The Gentle Giraffe Who Reached for the Clouds",
            "urls": ["https://en.wikipedia.org/wiki/Children%27s_poetry", "https://en.wikipedia.org/wiki/Moral"],
            "score": 91.0,
            "reason": "Heartwarming animal poem showing how being tall helps pick fruit for short friends.",
        },
        {
            "title": "Counting Baby Stars: A Goodnight Lullaby Song",
            "urls": ["https://en.wikipedia.org/wiki/Lullaby", "https://en.wikipedia.org/wiki/Twinkle,_Twinkle,_Little_Star"],
            "score": 97.0,
            "reason": "Soothing bedtime singing poem that calms toddlers into peaceful sweet dreams.",
        },
        {
            "title": "The Happy Dolphin Splashing in the Ocean Waves",
            "urls": ["https://en.wikipedia.org/wiki/Children%27s_literature", "https://en.wikipedia.org/wiki/Nursery_rhyme"],
            "score": 90.0,
            "reason": "Splish-splash musical seaside rhyme with friendly jumping dolphins.",
        },
        {
            "title": "The Sleepy Koala High Up in the Gum Tree",
            "urls": ["https://en.wikipedia.org/wiki/Lullaby", "https://en.wikipedia.org/wiki/Children%27s_poetry"],
            "score": 89.0,
            "reason": "Cuddly bedtime poem about cozy hugs and peaceful starry nights.",
        },
    ],
    "mokshavani": [
        {
            "title": "Gayatri Mantra: Meaning and Divine Acoustic Power",
            "urls": [
                "https://en.wikipedia.org/wiki/Gayatri_Mantra",
                "https://en.wikipedia.org/wiki/Rigveda",
            ],
            "score": 95.0,
            "reason": "Supreme Vedic chant for intellect, clarity, and universal divine illumination.",
        },
        {
            "title": "Mahamrityunjaya Mantra: Conquering Fear and Negative Energy",
            "urls": [
                "https://en.wikipedia.org/wiki/Mahamrityunjaya_Mantra",
                "https://en.wikipedia.org/wiki/Rudra",
            ],
            "score": 94.0,
            "reason": "Sacred Rudra mantra for spiritual healing, longevity, and liberation from fear.",
        },
        {
            "title": "Hanuman Chalisa: 40 Verses of Supreme Strength and Protection",
            "urls": [
                "https://en.wikipedia.org/wiki/Hanuman_Chalisa",
                "https://en.wikipedia.org/wiki/Awadhi_literature",
            ],
            "score": 96.0,
            "reason": "Most beloved devotional hymn invoking unshakeable courage and devotion.",
        },
        {
            "title": "Shiv Tandav Stotram: The Cosmic Dance of Bhagwan Shiva",
            "urls": [
                "https://en.wikipedia.org/wiki/Shiva_Tandava_Stotra",
                "https://en.wikipedia.org/wiki/Ravana",
            ],
            "score": 92.0,
            "reason": "Electrifying Sanskrit composition celebrating divine power and cosmic rhythm.",
        },
        {
            "title": "Bhagavad Gita Chapter 2 Verse 47: The Secret of Karma Yoga",
            "urls": [
                "https://en.wikipedia.org/wiki/Karmanye_Vadhikaraste",
                "https://en.wikipedia.org/wiki/Karma_yoga",
            ],
            "score": 90.0,
            "reason": "The timeless philosophy of focused action free from attachment to results.",
        },
        {
            "title": "Karpura Gauram Karunavataram: Sacred Evening Aarti with Meaning",
            "urls": [
                "https://en.wikipedia.org/wiki/Karpura-gauram_karunavataram",
                "https://en.wikipedia.org/wiki/Yajurveda",
            ],
            "score": 88.0,
            "reason": "Ancient Shiva mantra recited during divine Aarti for supreme peace.",
        },
        {
            "title": "Vishnu Sahasranama: 1000 Names of Supreme Consciousness",
            "urls": [
                "https://en.wikipedia.org/wiki/Vishnu_Sahasranama",
                "https://en.wikipedia.org/wiki/Mahabharata",
            ],
            "score": 89.0,
            "reason": "Vedic recitation for calming the restless mind and invoking auspiciousness.",
        },
        {
            "title": "Shanti Mantra: Om Dyauha Shantir Antariksham Shantihi",
            "urls": [
                "https://en.wikipedia.org/wiki/Shanti_Mantra",
                "https://en.wikipedia.org/wiki/Upanishads",
            ],
            "score": 87.0,
            "reason": "Universal Vedic prayer for cosmic harmony, world peace, and spiritual tranquility.",
        },
    ],
    "apexstoic": [
        {
            "title": "Marcus Aurelius: 7 Rules to Never Care What People Think",
            "urls": [
                "https://en.wikipedia.org/wiki/Meditations",
                "https://plato.stanford.edu/entries/marcus-aurelius/",
            ],
            "score": 92.0,
            "reason": "Timeless Stoic mental armor against societal opinions and external judgment.",
        },
        {
            "title": "The Power of Moving in Silence: Why Stoics Never Speak",
            "urls": [
                "https://en.wikipedia.org/wiki/Stoicism",
                "https://plato.stanford.edu/entries/stoicism/",
            ],
            "score": 90.0,
            "reason": "The psychology of silent execution and preserving dopamine for real mastery.",
        },
        {
            "title": "How to Master Your Emotions: The Dichotomy of Control",
            "urls": [
                "https://en.wikipedia.org/wiki/Epictetus",
                "https://plato.stanford.edu/entries/epictetus/",
            ],
            "score": 94.0,
            "reason": "The fundamental Stoic formula to eliminate anxiety, anger, and feeling helpless.",
        },
        {
            "title": "Seneca's Guide to Overcoming Anxiety and Fear",
            "urls": [
                "https://en.wikipedia.org/wiki/Seneca_the_Younger",
                "https://plato.stanford.edu/entries/seneca/",
            ],
            "score": 91.0,
            "reason": "Why we suffer more often in imagination than in reality, and how to stop it.",
        },
        {
            "title": "Why Betrayal and Insults Cannot Hurt a True Stoic",
            "urls": [
                "https://en.wikipedia.org/wiki/Meditations",
                "https://plato.stanford.edu/entries/stoicism/",
            ],
            "score": 89.0,
            "reason": "Marcus Aurelius's mental model for dealing with deceptive and ungrateful people.",
        },
        {
            "title": "Memento Mori: Why Remembering Death Makes You Fearless",
            "urls": [
                "https://en.wikipedia.org/wiki/Memento_mori",
                "https://plato.stanford.edu/entries/seneca/",
            ],
            "score": 93.0,
            "reason": "How ancient philosophers turned mortality into the ultimate fuel for urgent action.",
        },
        {
            "title": "The Law of Emotional Detachment: Amor Fati",
            "urls": [
                "https://en.wikipedia.org/wiki/Amor_fati",
                "https://plato.stanford.edu/entries/stoicism/",
            ],
            "score": 88.0,
            "reason": "Loving your fate and turning every catastrophe into immediate strength.",
        },
        {
            "title": "How to Stop Being Lazy: The Brutal Stoic Discipline Formula",
            "urls": [
                "https://en.wikipedia.org/wiki/Meditations",
                "https://plato.stanford.edu/entries/marcus-aurelius/",
            ],
            "score": 92.0,
            "reason": "Waking up before sunrise with relentless duty, inspired by the Roman Emperor.",
        },
    ],
    "chronosenigma": [
        {
            "title": "The Great Pyramid of Giza: Impossible Precision Engineering",
            "urls": [
                "https://en.wikipedia.org/wiki/Great_Pyramid_of_Giza",
                "https://en.wikipedia.org/wiki/Egyptian_pyramid_construction_techniques",
            ],
            "score": 95.0,
            "reason": "2.3 million stone blocks aligned to true north with sub-millimeter precision.",
        },
        {
            "title": "Göbekli Tepe: The 12,000-Year-Old Megalith That Defies History",
            "urls": [
                "https://en.wikipedia.org/wiki/G%C3%B6bekli_Tepe",
                "https://en.wikipedia.org/wiki/Pre-Pottery_Neolithic",
            ],
            "score": 94.0,
            "reason": "Megalithic sanctuary built before farming that shattered orthodox timelines.",
        },
        {
            "title": "Derinkuyu: The Massive Ancient Underground City That Housed 20,000 People",
            "urls": [
                "https://en.wikipedia.org/wiki/Derinkuyu_underground_city",
                "https://en.wikipedia.org/wiki/Cappadocia",
            ],
            "score": 91.0,
            "reason": "Multi-level subterranean marvel built deep into volcanic rock with air shafts.",
        },
        {
            "title": "The Antikythera Mechanism: The 2,000-Year-Old Astronomical Computer",
            "urls": [
                "https://en.wikipedia.org/wiki/Antikythera_mechanism",
                "https://en.wikipedia.org/wiki/Ancient_Greek_technology",
            ],
            "score": 92.0,
            "reason": "Ancient Greek bronze clockwork gear system calculating celestial orbits.",
        },
        {
            "title": "Gunung Padang: The Megalithic Site Hidden Under a Mountain",
            "urls": [
                "https://en.wikipedia.org/wiki/Gunung_Padang_Megalithic_Site",
                "https://en.wikipedia.org/wiki/Megalith",
            ],
            "score": 90.0,
            "reason": "Massive terraced stone hill in Indonesia with core drillings showing deep antiquity.",
        },
        {
            "title": "The Richat Structure: Is the Eye of the Sahara the Lost Atlantis?",
            "urls": [
                "https://en.wikipedia.org/wiki/Richat_Structure",
                "https://en.wikipedia.org/wiki/Atlantis",
            ],
            "score": 88.0,
            "reason": "Concentric geological rings matching Plato's exact dimensions of the lost capital.",
        },
    ],
    "empirepulse": [
        {
            "title": "How Qatar Built Infinite Wealth with Zero Rivers or Farmland",
            "urls": [
                "https://en.wikipedia.org/wiki/Economy_of_Qatar",
                "https://www.worldbank.org/en/country/gcc/overview",
            ],
            "score": 93.0,
            "reason": "The geopolitical masterstroke of North Field LNG and the world's richest per capita state.",
        },
        {
            "title": "The Secret Financial Machine of Singapore: From Swamp to Superpower",
            "urls": [
                "https://en.wikipedia.org/wiki/Economy_of_Singapore",
                "https://www.temasek.com.sg/",
            ],
            "score": 95.0,
            "reason": "How Temasek and GIC built a $1 trillion sovereign engine without natural resources.",
        },
        {
            "title": "Norway's $1.7 Trillion Oil Fund: The World's Biggest Piggy Bank",
            "urls": [
                "https://en.wikipedia.org/wiki/Government_Pension_Fund_of_Norway",
                "https://www.nbim.no/",
            ],
            "score": 94.0,
            "reason": "Owning 1.5% of all publicly listed companies on Earth for 5.5 million citizens.",
        },
        {
            "title": "How Switzerland Got So Rich: The Neutral Fortress Banking Empire",
            "urls": [
                "https://en.wikipedia.org/wiki/Economy_of_Switzerland",
                "https://www.worldbank.org/en/country/switzerland",
            ],
            "score": 91.0,
            "reason": "Alpine defense, private banking confidentiality, and high-value industrial monopolies.",
        },
        {
            "title": "How Monaco Became the Billionaire Tax Haven of the Planet",
            "urls": [
                "https://en.wikipedia.org/wiki/Monaco",
                "https://www.worldbank.org/en/country/monaco",
            ],
            "score": 89.0,
            "reason": "Zero income tax, supreme security, and the highest concentration of millionaires on Earth.",
        },
        {
            "title": "The Economics of Trillion-Dollar Megaprojects: Saudi Vision 2030",
            "urls": [
                "https://en.wikipedia.org/wiki/Public_Investment_Fund",
                "https://en.wikipedia.org/wiki/Saudi_Vision_2030",
            ],
            "score": 92.0,
            "reason": "How PIF is deploying sovereign capital into NEOM, AI infrastructure, and global sports.",
        },
        {
            "title": "The Geopolitics of Choke Points: The Battle for the Strait of Malacca",
            "urls": [
                "https://en.wikipedia.org/wiki/Strait_of_Malacca",
                "https://en.wikipedia.org/wiki/Choke_point",
            ],
            "score": 90.0,
            "reason": "The narrow waterway controlling 40% of global trade and the energy of superpower nations.",
        },
        {
            "title": "How Tiny Luxembourg Became the Richest Country per Capita in the World",
            "urls": [
                "https://en.wikipedia.org/wiki/Economy_of_Luxembourg",
                "https://www.worldbank.org/en/country/luxembourg",
            ],
            "score": 88.0,
            "reason": "The European fund administration capital managing trillions in sovereign and institutional wealth.",
        },
    ],
    "astrapulse": [
        {
            "title": "Scorpio Zodiac Secrets: Why Their Intuition Is Never Wrong",
            "urls": ["https://en.wikipedia.org/wiki/Scorpio_(astrology)", "https://en.wikipedia.org/wiki/Astrological_sign"],
            "score": 96.0,
            "reason": "Hyper-engaging exploration of Scorpio's piercing emotional intuition, psychological depth, and loyalty.",
        },
        {
            "title": "Cancer Zodiac Secrets: The Fierce Protector Behind the Shell",
            "urls": ["https://en.wikipedia.org/wiki/Cancer_(astrology)", "https://en.wikipedia.org/wiki/Water_(classical_element)"],
            "score": 95.0,
            "reason": "Emotional resonance exploring Cancer's lunar connection, fierce loyalty, and psychic empathy.",
        },
        {
            "title": "Aries Zodiac Secrets: The Unstoppable Fire of the Pioneer",
            "urls": ["https://en.wikipedia.org/wiki/Aries_(astrology)", "https://en.wikipedia.org/wiki/Mars_(astrology)"],
            "score": 94.0,
            "reason": "High-energy breakdown of Aries courage, magnetic confidence, and primal leadership drive.",
        },
        {
            "title": "The 12 Zodiac Signs Ranked by Emotional Intelligence",
            "urls": ["https://en.wikipedia.org/wiki/Astrology", "https://en.wikipedia.org/wiki/Zodiac"],
            "score": 95.0,
            "reason": "Viral ranking format breaking down how water, earth, fire, and air signs process human emotion.",
        },
        {
            "title": "Zodiac Compatibility: Why Opposites Magnetic Attractions Clashes",
            "urls": ["https://en.wikipedia.org/wiki/Synastry", "https://en.wikipedia.org/wiki/Astrology"],
            "score": 93.0,
            "reason": "Deep relational astrology analyzing polarity pairs and magnetic attractions.",
        },
        {
            "title": "What Your Moon Sign Really Reveals About Your Hidden Soul",
            "urls": ["https://en.wikipedia.org/wiki/Moon_(astrology)", "https://en.wikipedia.org/wiki/Horoscope"],
            "score": 92.0,
            "reason": "Essential astrological wisdom explaining the subconscious mind, emotional instinct, and inner child.",
        },
        {
            "title": "Saturn Return Explained: The Defining Karmic Shift of Your 20s",
            "urls": ["https://en.wikipedia.org/wiki/Saturn_return", "https://en.wikipedia.org/wiki/Saturn_(astrology)"],
            "score": 91.0,
            "reason": "The major 29-year astrological milestone of maturity, destiny realignment, and life restructuring.",
        },
    ],
}


class TopicDiscovery:
    def __init__(self, settings: Settings, state: StateStore):
        self.settings = settings
        self.state = state
        self.editorial = editorial_system_for(settings.channel_profile)

    def discover(self, max_candidates: int = 24) -> list[TopicCandidate]:
        signals: dict[str, dict] = defaultdict(lambda: {"count": 0, "urls": [], "freshness": 0.0})
        profile = self.settings.channel_profile

        # 1. Search live RSS / news feeds
        for query in self._queries():
            items = self._news_search(query)
            if not items and profile in {"bytevexa", "curioaxiom"}:
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

        # 2. Incorporate curated evergreen viral topic bank for isolated niches
        evergreen_pool = CHANNEL_EVERGREEN_TOPICS.get(profile, [])
        for entry in evergreen_pool:
            key = self._normalize(entry["title"])
            if key not in signals:
                signals[key] = {
                    "title": entry["title"],
                    "count": 2,
                    "urls": entry.get("urls", []),
                    "freshness": 0.85,
                    "curated_score": entry.get("score", 85.0),
                    "curated_reason": entry.get("reason", "Curated evergreen viral candidate."),
                }

        recent = [self._normalize(item) for item in self.state.recent_topics()]
        preferred = set(self.state.performance_terms())
        candidates: list[TopicCandidate] = []

        for key, signal in signals.items():
            if self.settings.channel_profile != "curioaxiom" and not self.editorial.is_relevant_topic(signal["title"]):
                continue
            if any(self._similar(key, old) for old in recent if old):
                continue

            overlap = len(preferred.intersection(key.split()))
            practical = self.editorial.relevance_score(signal["title"])
            freshness_points = signal["freshness"] * 27
            repetition_points = min(18, signal["count"] * 6)
            base_score = signal.get("curated_score", 45.0 + repetition_points + freshness_points + overlap * 4 + practical)
            score = min(100.0, base_score)
            urls = [url for url in dict.fromkeys(signal["urls"]) if url]

            reason = signal.get("curated_reason")
            if not reason:
                if practical >= 8:
                    reason = f"High-relevance signal for {self.settings.channel_display_name}; repeated {signal['count']} time(s)."
                elif practical < 0:
                    reason = f"Candidate signal for {self.settings.channel_display_name}; practical viewer relevance is moderate."
                else:
                    reason = f"Candidate signal for {self.settings.channel_display_name}; repeated {signal['count']} time(s)."

            candidates.append(
                TopicCandidate(
                    title=signal["title"],
                    score=score,
                    reason=reason,
                    source_urls=urls[:5],
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:max_candidates]

    def _queries(self) -> list[str]:
        terms = list(self.settings.topic_query_list)
        profile = self.settings.channel_profile
        if profile == "bytevexa":
            terms.extend(
                [
                    "new AI tool workflow",
                    "AI app new feature",
                    "AI agent release",
                    "AI presentation tool",
                    "AI study research tool",
                    "AI browser productivity",
                ]
            )
        elif profile == "wondertales":
            terms.extend(["kids nursery rhymes", "bedtime moral stories for children", "animated poems for kids"])
        elif profile == "mokshavani":
            terms.extend(["Gayatri Mantra meaning", "Mahamrityunjaya benefits", "Hanuman Chalisa spiritual meaning"])
        elif profile == "apexstoic":
            terms.extend(["Marcus Aurelius stoic rules", "how to control emotions stoicism", "ancient discipline stoic"])
        elif profile == "chronosenigma":
            terms.extend(["ancient archaeological mystery", "unsolved ancient engineering", "lost civilization discovery"])
        elif profile == "empirepulse":
            terms.extend(["how small country became rich", "sovereign wealth fund strategy", "billionaire economic dynasty"])

        terms.extend(self.state.performance_terms(limit=6))
        return list(dict.fromkeys(terms))[:14]

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
        except httpx.HTTPError:
            return []
        parsed = feedparser.parse(response.text)

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
