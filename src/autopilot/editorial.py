from __future__ import annotations

import re
from dataclasses import dataclass

from autopilot.models import ResearchPack, TopicCandidate


@dataclass(frozen=True)
class EditorialBrief:
    series: str
    promise: str
    required_beats: tuple[str, ...]
    brand_name: str = "BYTEVEXA"

    def as_text(self) -> str:
        beats = "\n".join(f"- {item}" for item in self.required_beats)
        return (
            f"{self.brand_name.upper()} EDITORIAL BRIEF\n"
            f"SERIES: {self.series}\n"
            f"VIEWER PROMISE: {self.promise}\n"
            "REQUIRED STORY BEATS:\n"
            f"{beats}\n"
            "Use the research below for factual claims. The brief itself is not evidence."
        )


class ByteVexaEditorialSystem:
    def enrich(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> ResearchPack:
        brief = self.brief_for(candidate, research, video_format=video_format)
        notes = research.research_notes.strip()
        combined = brief.as_text() + ("\n\nRESEARCH EVIDENCE\n" + notes if notes else "")
        return research.model_copy(update={"research_notes": combined})

    def brief_for(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> EditorialBrief:
        text = f"{candidate.title} {candidate.angle} {research.research_notes}".lower()
        if video_format == "long":
            return EditorialBrief(
                brand_name="BYTEVEXA",
                series="Full Deep Dive & Architecture Guide",
                promise=(
                    "Deliver an exhaustive 8-12 minute technical explainer with architectural breakdown, "
                    "code/command workflows, real benchmarks, and honest limitations without generic hype."
                ),
                required_beats=(
                    "Open with the critical capability or practical problem being solved.",
                    "Explain the foundational architectural components and setup.",
                    "Walk through concrete, verified developer or user workflows.",
                    "Demonstrate actual outputs, real examples, and performance metrics.",
                    "Analyze VRAM, compute requirements, pricing, or production caveats.",
                    "Compare against major cloud SaaS or alternative approaches.",
                    "Provide a realistic, actionable decision framework and takeaway.",
                ),
            )

        series = self._series_for(text)
        practical = self._practical_hint(text)
        return EditorialBrief(
            brand_name="BYTEVEXA",
            series=series,
            promise=(
                "Explain one new AI development through a real task or everyday consequence. "
                f"When evidence allows, ground it in {practical}."
            ),
            required_beats=(
                "Open with the most useful or surprising consequence, not the announcement.",
                "Explain what changed in one plain-English sentence.",
                "Connect it to one realistic user and task.",
                "Show or illustrate an input -> action -> output flow.",
                "Include at least one concrete feature, workflow step, limitation, comparison, or availability condition supported by evidence.",
                "For a software review, show public signup/access, the actual product surface, a feature, a public workflow and its output; show price/free availability only from the official page, then give a compact pros/cons decision.",
                "State the catch or who should care when relevant.",
                "End with a clear practical takeaway instead of generic filler.",
                "Avoid a sequence made mostly of landing pages or plain text cards. Do not call an unlogged-in marketing page a live test.",
            ),
        )

    def relevance_score(self, title: str) -> float:
        text = title.lower()
        score = 0.0
        high_value = {
            "launch": 5, "released": 5, "release": 5, "new": 3, "update": 4,
            "agent": 4, "browser": 5, "video": 4, "image": 4, "voice": 4,
            "search": 4, "code": 4, "coding": 4, "presentation": 5, "slides": 5,
            "study": 5, "research": 4, "document": 4, "pdf": 5, "meeting": 5,
            "email": 5, "phone": 4, "app": 4, "tool": 4,
        }
        for term, weight in high_value.items():
            if re.search(rf"\b{re.escape(term)}\b", text):
                score += weight
        score -= sum(4 for term in ("funding", "valuation", "lawsuit", "executive", "rumor") if term in text)
        return max(-12.0, min(18.0, score))

    @staticmethod
    def _series_for(text: str) -> str:
        if any(term in text for term in ("launch", "released", "release", "update", "announced", "new model")):
            return "What Changed?"
        if any(term in text for term in ("benchmark", "versus", " vs ", "compare", "comparison")):
            return "AI vs Real Task"
        if any(term in text for term in ("how to", "workflow", "feature", "tool", "app", "browser", "presentation", "slides")):
            return "30-Second Demo"
        if any(term in text for term in ("free", "pricing", "subscription")):
            return "Worth Trying?"
        return "AI News You Can Use"

    @staticmethod
    def _practical_hint(text: str) -> str:
        mappings = (
            (("student", "study", "research", "pdf", "notes"), "a student or research workflow"),
            (("slides", "presentation", "deck"), "making a presentation from a short prompt"),
            (("code", "coding", "developer"), "a small coding task with a visible result"),
            (("video", "image", "design"), "creating one piece of media from a concrete prompt"),
            (("email", "meeting", "office", "work"), "a normal work task someone repeats every week"),
            (("search", "browser", "web"), "finding and using information on the web"),
        )
        for keywords, description in mappings:
            if any(word in text for word in keywords):
                return description
        return "a normal task a student, creator, or knowledge worker already does"


class WonderTalesEditorialSystem:
    """Editorial system for WonderTales Kids (Children's poems, rhymes, bedtime tales)."""

    def enrich(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> ResearchPack:
        brief = self.brief_for(candidate, research, video_format=video_format)
        notes = research.research_notes.strip()
        combined = brief.as_text() + ("\n\nSTORY EVIDENCE & SEEDS\n" + notes if notes else "")
        return research.model_copy(update={"research_notes": combined})

    def brief_for(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> EditorialBrief:
        if video_format == "long":
            return EditorialBrief(
                brand_name="WONDERTALES KIDS",
                series="Enchanted Bedtime Storybook & Moral Fables",
                promise=(
                    "An enchanting 8-10 minute animated bedtime adventure or 5-poem collection for toddlers and kids. "
                    "Features lovable animal heroes, rhythmic rhyming verses, gentle conflict resolution, and a soothing bedtime lesson."
                ),
                required_beats=(
                    "Warm, cozy opening setting the scene in a magical sunlit meadow or starry forest.",
                    "Introduce the curious little animal hero with an adorable personality trait.",
                    "A playful mini-quest or gentle mystery (e.g. lost star, missing honey pot, colorful rainbow bridge).",
                    "Three whimsical encounters with kind animal friends who share helpful advice in rhyming verse.",
                    "A moment of gentle bravery, teamwork, or sharing that solves the quest happily.",
                    "A warm bedtime lullaby rhythm signaling rest, safety, and sweet dreams.",
                    "Closing soothing whisper wishing young viewers goodnight with love and peace.",
                ),
            )

        return EditorialBrief(
            brand_name="WONDERTALES KIDS",
            series="Singing Rhymes & Toddler Poems",
            promise="A singing 45-second bouncy nursery rhyme and animated animal poem in strict AABB musical rhyming verse with a joyful moral.",
            required_beats=(
                "Bouncy, upbeat 4-line rhyming song stanza that hooks children immediately with musical rhythm.",
                "Adorable animal hero doing something playful with joyful sound words (hop-hop, splash, giggle, twinkle-twinkle).",
                "Delightful adventure or gentle lesson told entirely in singing rhyming couplets.",
                "Sweet, memorable rhyming moral couplet that leaves kids smiling and singing along happily.",
            ),
        )

    def relevance_score(self, title: str) -> float:
        text = title.lower()
        score = 0.0
        good_terms = ("poem", "rhyme", "story", "fable", "bedtime", "animal", "bunny", "bear", "lion", "kindness", "magic")
        for t in good_terms:
            if t in text:
                score += 3.0
        return max(-10.0, min(20.0, score))


class MokshaVaniEditorialSystem:
    """Editorial system for MokshaVani (Hindi bhajans, Gayatri Mantra, sacred Sanskrit chants)."""

    def enrich(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> ResearchPack:
        brief = self.brief_for(candidate, research, video_format=video_format)
        notes = research.research_notes.strip()
        combined = brief.as_text() + ("\n\nVEDIC SOURCES & MEANINGS\n" + notes if notes else "")
        return research.model_copy(update={"research_notes": combined})

    def brief_for(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> EditorialBrief:
        if video_format == "long":
            return EditorialBrief(
                brand_name="MOKSHAVANI",
                series="Vedic Meditation & Sacred Chants Mahayajna",
                promise=(
                    "An immersive 8-10 minute sacred meditation and spiritual discourse in Hindi. Explains the Sanskrit origin, "
                    "word-by-word meaning, acoustic vibration benefits, and life-transforming spiritual power of sacred mantras."
                ),
                required_beats=(
                    "Sacred Sanskrit invocation with resonant chanting (Gayatri Mantra, Mahamrityunjaya, Hanuman Chalisa, or Shiva Tandav).",
                    "Cosmic significance: Which Rishi revealed this mantra, deity energy, and spiritual vibration.",
                    "Word-by-word Hindi translation explaining the profound philosophical depth.",
                    "Scientific and psychological benefits: Vagus nerve stimulation, anxiety relief, fearlessness, and mental aura.",
                    "Sacred chanting protocol: Ideal time (Brahmamuhurta), posture, breath awareness, and 108 japa practice.",
                    "Real-life transformative mindset: Removing negativity, fear of failure, and ego.",
                    "Closing sacred shanti mantra chanting blessing all beings with peace and divine light.",
                ),
            )

        return EditorialBrief(
            brand_name="MOKSHAVANI",
            series="Divya Shloka Sutra",
            promise="A serene 45-second Sanskrit shloka recitation with authentic Hindi translation and mental peace benefit.",
            required_beats=(
                "Resonant Sanskrit shloka chanted with spiritual clarity and reverent cadence.",
                "Exact Hindi meaning translated into simple, deeply touching, and inspiring words.",
                "One practical spiritual benefit: mental calm, courage, protection, or gratitude.",
                "Reverent closing blessing (Jai Shri Ram, Har Har Mahadev, Radhe Radhe, Om Shanti).",
            ),
        )

    def relevance_score(self, title: str) -> float:
        text = title.lower()
        score = 0.0
        good_terms = ("gayatri", "mantra", "bhajan", "shiva", "hanuman", "krishna", "ram", "vedic", "meditation", "chalisa", "stotram")
        for t in good_terms:
            if t in text:
                score += 4.0
        return max(-10.0, min(20.0, score))


class ApexStoicEditorialSystem:
    """Editorial system for ApexStoic (Stoicism, Marcus Aurelius, emotional mastery, discipline)."""

    def enrich(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> ResearchPack:
        brief = self.brief_for(candidate, research, video_format=video_format)
        notes = research.research_notes.strip()
        combined = brief.as_text() + ("\n\nPHILOSOPHICAL EVIDENCE & TEXTS\n" + notes if notes else "")
        return research.model_copy(update={"research_notes": combined})

    def brief_for(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> EditorialBrief:
        if video_format == "long":
            return EditorialBrief(
                brand_name="APEXSTOIC",
                series="Stoic Mastery & Psychological Warfare",
                promise=(
                    "An unsparing, high-impact 8-10 minute philosophical masterclass on emotional self-mastery, "
                    "mental toughness, and ancient Stoic resilience (Marcus Aurelius, Seneca, Epictetus) to forge an unshakeable mind."
                ),
                required_beats=(
                    "Brutal opening hook exposing modern emotional reactivity and why most men lose control of their lives.",
                    "The Dichotomy of Control: The ruthless separation between what you influence and what you must ignore.",
                    "Rule 1: Move in complete silence — why broadcasting goals destroys dopamine and invites envy.",
                    "Rule 2: The Art of Voluntary Hardship — inoculating the mind against sudden chaos and betrayal.",
                    "Rule 3: Amor Fati and Memento Mori — converting every obstacle into immediate psychological fuel.",
                    "Historical case study: Marcus Aurelius ruling Rome through the Antonine Plague, war, and treason.",
                    "Commanding closing framework: Exactly how to carry yourself in the world starting today.",
                ),
            )

        return EditorialBrief(
            brand_name="APEXSTOIC",
            series="Brutal Stoic Rules",
            promise="A 45-second dose of unapologetic Stoic wisdom and mental toughness that commands immediate respect.",
            required_beats=(
                "Confrontational psychological hook exposing an emotional weakness or common delusion.",
                "Ancient Stoic maxim from Marcus Aurelius or Seneca delivered with commanding baritone precision.",
                "The psychological contrast: How the weak react versus how the master responds.",
                "Unforgiving closing rule of conduct: Take action in silence.",
            ),
        )

    def relevance_score(self, title: str) -> float:
        text = title.lower()
        score = 0.0
        good_terms = ("stoic", "marcus aurelius", "seneca", "epictetus", "discipline", "emotion", "silence", "mindset", "rules")
        for t in good_terms:
            if t in text:
                score += 3.5
        return max(-10.0, min(20.0, score))


class ChronosEnigmaEditorialSystem:
    """Editorial system for ChronosEnigma (Ancient mysteries, lost civilizations, archaeology)."""

    def enrich(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> ResearchPack:
        brief = self.brief_for(candidate, research, video_format=video_format)
        notes = research.research_notes.strip()
        combined = brief.as_text() + ("\n\nARCHAEOLOGICAL & HISTORICAL EVIDENCE\n" + notes if notes else "")
        return research.model_copy(update={"research_notes": combined})

    def brief_for(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> EditorialBrief:
        if video_format == "long":
            return EditorialBrief(
                brand_name="CHRONOSENIGMA",
                series="Forbidden Antiquity & Lost Civilizations",
                promise=(
                    "An 8-10 minute cinematic documentary investigating unsolved archaeological anomalies, "
                    "megalithic engineering, and lost civilizations that challenge conventional historical timelines."
                ),
                required_beats=(
                    "Atmospheric opening mystery hook presenting a specific artifact, ruin, or anomaly that defies explanation.",
                    "The orthodox mainstream consensus and the exact physical contradictions that break it.",
                    "Empirical physical evidence: Precision laser scans, core drillings, acoustic resonance, or astronomical alignments.",
                    "Global corroboration: Matching motifs and engineering across oceans before recorded maritime contact.",
                    "Alternative hypotheses: Advanced lost global culture, forgotten cataclysms, or cyclical civilizations.",
                    "Critical analysis of what modern science still cannot replicate or explain.",
                    "Haunting documentary takeaway on humanity's forgotten past and the fragility of civilizations.",
                ),
            )

        return EditorialBrief(
            brand_name="CHRONOSENIGMA",
            series="Ancient Anomalies Explained",
            promise="A gripping 45-second investigation into one baffling ancient mystery or impossible artifact.",
            required_beats=(
                "Mysterious visual question highlighting an archaeological paradox.",
                "Exact physical measurements and engineering oddity described clearly.",
                "Orthodox theory vs the physical impossibility.",
                "Chilling closing thought that leaves the viewer questioning orthodox history.",
            ),
        )

    def relevance_score(self, title: str) -> float:
        text = title.lower()
        score = 0.0
        good_terms = ("ancient", "civilization", "mystery", "pyramid", "ruins", "archaeology", "atlantis", "anomaly", "megalith")
        for t in good_terms:
            if t in text:
                score += 3.5
        return max(-10.0, min(20.0, score))


class EmpirePulseEditorialSystem:
    """Editorial system for EmpirePulse (Geopolitics, sovereign wealth, billionaire dynasties, megaprojects)."""

    def enrich(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> ResearchPack:
        brief = self.brief_for(candidate, research, video_format=video_format)
        notes = research.research_notes.strip()
        combined = brief.as_text() + ("\n\nECONOMIC & GEOPOLITICAL EVIDENCE\n" + notes if notes else "")
        return research.model_copy(update={"research_notes": combined})

    def brief_for(self, candidate: TopicCandidate, research: ResearchPack, video_format: str = "short") -> EditorialBrief:
        if video_format == "long":
            return EditorialBrief(
                brand_name="EMPIREPULSE",
                series="Geopolitical Empires & Trillion-Dollar Dynasties",
                promise=(
                    "A fast-paced, high-status 8-10 minute geopolitical and economic documentary analyzing how small nations, "
                    "sovereign wealth funds, and dynasty families amass unimaginable global wealth and geopolitical leverage."
                ),
                required_beats=(
                    "Staggering economic paradox hook: How an isolated or resource-poor territory built astronomical wealth.",
                    "The historical vulnerability or geopolitical crisis that forced strategic reinvention.",
                    "The institutional blueprint: Sovereign wealth vehicles, tax architecture, and trade choke points.",
                    "The financial engine in action: Trophy foreign assets, sovereign equity, and strategic soft power.",
                    "The hidden costs and trade-offs: Social contracts, geopolitical risks, and global adversaries.",
                    "Comparative analysis: Why similar nations failed where this system succeeded.",
                    "Strategic macroeconomic takeaway on the future balance of global power and wealth.",
                ),
            )

        return EditorialBrief(
            brand_name="EMPIREPULSE",
            series="Economic Power Moves",
            promise="A high-velocity 45-second breakdown of a mind-blowing financial power move or sovereign wealth secret.",
            required_beats=(
                "Explosive financial paradox hook revealing a shocking wealth or geopolitical stat.",
                "The hidden mechanism or sovereign strategy that made it possible.",
                "The staggering dollar figure or global market consequence.",
                "Sharp closing verdict on how elite global power actually operates.",
            ),
        )

    def relevance_score(self, title: str) -> float:
        text = title.lower()
        score = 0.0
        good_terms = ("wealth", "billionaire", "economy", "sovereign", "dynasty", "qatar", "singapore", "trillion", "empire", "money")
        for t in good_terms:
            if t in text:
                score += 3.5
        return max(-10.0, min(20.0, score))


def editorial_system_for(profile: str):
    """Factory to retrieve the isolated editorial system for any channel profile."""
    from autopilot.facts import CurioAxiomEditorialSystem

    systems = {
        "bytevexa": ByteVexaEditorialSystem,
        "curioaxiom": CurioAxiomEditorialSystem,
        "wondertales": WonderTalesEditorialSystem,
        "mokshavani": MokshaVaniEditorialSystem,
        "apexstoic": ApexStoicEditorialSystem,
        "chronosenigma": ChronosEnigmaEditorialSystem,
        "empirepulse": EmpirePulseEditorialSystem,
    }
    cls = systems.get(profile, ByteVexaEditorialSystem)
    return cls()
