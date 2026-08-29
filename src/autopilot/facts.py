from __future__ import annotations

import json
from urllib.parse import urlparse

from autopilot.config import Settings
from autopilot.discovery import TopicDiscovery
from autopilot.models import ResearchPack, TopicCandidate
from autopilot.providers.premium_planner import PremiumScriptPlanner


AUTHORITATIVE_DOMAINS = {
    "science": ("nasa.gov", "noaa.gov", "esa.int", "nih.gov", "nature.com", "science.org"),
    "history": ("si.edu", "loc.gov", "archives.gov", "britishmuseum.org"),
    "geography": ("un.org", "worldbank.org", "usgs.gov", "noaa.gov"),
    "mathematics": ("ams.org", "maa.org", "mathworld.wolfram.com", "edu"),
    "space": ("nasa.gov", "esa.int", "jpl.nasa.gov", "noirlab.edu"),
    "engineering": ("nist.gov", "ieee.org", "asme.org", "sae.org", "edu"),
    "f1_automotive": ("fia.com", "formula1.com", "sae.org", "nhtsa.gov"),
}


class FactCategoryRouter:
    LANES = {
        "f1_automotive": ("formula 1", "f1", "race car", "automotive", "car", "tyre", "brake"),
        "space": ("space", "planet", "star", "moon", "mars", "saturn", "astronaut", "orbit"),
        "mathematics": ("math", "number", "probability", "paradox", "geometry", "equation"),
        "geography": ("country", "border", "ocean", "island", "map", "geography", "river"),
        "history": ("history", "ancient", "war", "empire", "archaeology", "century", "roman"),
        "engineering": ("engineering", "bridge", "aircraft", "machine", "structure", "material"),
        "science": ("science", "physics", "biology", "chemistry", "temperature", "energy"),
    }

    def route(self, text: str) -> str:
        lowered = text.lower()
        scores = {lane: sum(term in lowered for term in terms) for lane, terms in self.LANES.items()}
        lane, score = max(scores.items(), key=lambda item: item[1])
        return lane if score else "science"


class CurioAxiomEditorialSystem:
    def __init__(self) -> None:
        self.router = FactCategoryRouter()

    def relevance_score(self, title: str) -> float:
        text = title.lower()
        surprise = sum(term in text for term in (
            "why", "how", "hidden", "strange", "impossible", "oldest", "fastest",
            "largest", "smallest", "mystery", "discovery", "paradox", "unexpected",
        ))
        visual = sum(term in text for term in (
            "space", "planet", "map", "border", "engine", "car", "f1", "bridge",
            "ocean", "ancient", "machine", "physics",
        ))
        penalty = sum(term in text for term in ("opinion", "rumor", "celebrity", "politics", "horoscope"))
        return max(-12.0, min(18.0, surprise * 3 + visual * 2 - penalty * 6))

    def enrich(self, candidate: TopicCandidate, research: ResearchPack) -> ResearchPack:
        category = self.router.route(f"{candidate.title} {research.research_notes}")
        brief = (
            "CURIOAXIOM EDITORIAL BRIEF\n"
            f"CATEGORY: {category}\n"
            "PROMISE: One fascinating question. One cinematic story. One verified answer.\n"
            "REQUIRED STORY: mystery/question -> visual escalation -> verified explanation -> reveal -> meaning.\n"
            "Use only claims supported by research. Distinguish measured facts, estimates and theory. "
            "Never turn uncertainty into certainty. Avoid random fact lists and generic hooks.\n"
        )
        return research.model_copy(
            update={"category": category, "research_notes": brief + "\nRESEARCH EVIDENCE\n" + research.research_notes}
        )


class FactVerifier:
    """Score source diversity and authority before a fact may enter production."""

    def verify(self, research: ResearchPack) -> ResearchPack:
        domains = [urlparse(source.url).netloc.lower().removeprefix("www.") for source in research.sources]
        distinct = len(set(domains))
        authorities = AUTHORITATIVE_DOMAINS.get(research.category, ())
        authoritative = sum(
            any(
                domain == allowed
                or domain.endswith("." + allowed)
                or (allowed == "edu" and domain.endswith(".edu"))
                for allowed in authorities
            )
            for domain in domains
        )
        substantive = sum(len(source.snippet.strip()) >= 300 for source in research.sources)
        score = min(100.0, distinct * 15 + authoritative * 20 + substantive * 5)
        notes = [
            f"{distinct} distinct source domain(s)",
            f"{authoritative} category-authoritative source(s)",
            f"{substantive} substantive source extract(s)",
        ]
        if authoritative == 0:
            notes.append("No category-authoritative source found; production should fail closed.")
        return research.model_copy(update={"confidence_score": score, "verification_notes": notes})


class FactTopicDiscovery(TopicDiscovery):
    def __init__(self, settings: Settings, state):
        super().__init__(settings, state)
        self.editorial = CurioAxiomEditorialSystem()

    def _queries(self) -> list[str]:
        lanes = [
            "counterintuitive science discovery", "NASA surprising science",
            "history archaeology discovery", "geography borders explained",
            "mathematics paradox explained", "space engineering discovery",
            "Formula 1 engineering explained", "automotive engineering innovation",
            "hidden engineering facts",
        ]
        lanes.extend(self.settings.topic_query_list)
        lanes.extend(self.state.performance_terms(limit=5))
        return list(dict.fromkeys(lanes))[:16]


class FactScriptPlanner(PremiumScriptPlanner):
    def choose_topic(self, candidates: list[TopicCandidate]) -> TopicCandidate:
        if not candidates or not self.settings.llm_configured:
            return super().choose_topic(candidates)
        compact = [
            {"index": i, "title": c.title, "score": c.score, "reason": c.reason}
            for i, c in enumerate(candidates[:12])
        ]
        prompt = (
            "Choose ONE CurioAxiom fact story. Optimize for surprise, visual potential, curiosity gap, "
            "credible verification, evergreen value and one clean question. Reject politics, medical advice, "
            "unresolved rumors and claims too vague to verify. Candidates: "
            f"{json.dumps(compact)}. Return JSON only: {{\"index\": integer, \"angle\": string}}."
        )
        try:
            data = self._generate_json(prompt)
            chosen = candidates[int(data["index"])]
            chosen.angle = str(data.get("angle") or chosen.angle)
            return chosen
        except Exception:
            return max(candidates, key=lambda item: item.score)

    def _draft_prompt(self, research: ResearchPack, video_format: str) -> str:
        words = "95-145" if video_format == "short" else "1,200-1,650"
        scenes = "8-12" if video_format == "short" else "28-38"
        return f"""You are the senior researcher, writer and visual director for CurioAxiom.
Create an original cinematic YouTube {video_format} about: {research.topic}
Brand promise: One fascinating question. One cinematic story. One verified answer.
Category: {research.category}. Verification confidence: {research.confidence_score:.0f}/100.

VERIFIED RESEARCH
{research.research_notes[:22000]}

RULES
- Write {words} spoken words and {scenes} scenes in exact narration order.
- Tell one micro-documentary: question/mystery -> escalation -> mechanism/context -> reveal -> why it matters.
- Every factual claim must be supported by the evidence. Never invent precision.
- Qualify estimates, debated interpretations, simulations and theoretical scenarios.
- Open with a specific contradiction or consequence; never start with 'Did you know?' or a list.
- Include two concrete verified facts, an explanation of the mechanism or cause, and a caveat.
- End on the meaning of the answer, not generic engagement bait.
- Choose visual_mode ui, motion or stock. Prefer motion for diagrams, maps, scale, timelines,
  mechanisms and reconstructions. UI source_url must exactly match a research URL.
- on_screen_text is 2-7 words. purpose uses hook, evidence, context, mechanism, scale, reveal,
  caveat or takeaway. Avoid repeated or generic visuals.

PACKAGING
- Specific truthful title under 70 characters; 2-4 word thumbnail text; 6-12 relevant tags.
- Description summarizes the answer and preserves uncertainty.

Return JSON only with exactly: angle, hook, script, title, description, tags, thumbnail_brief,
thumbnail_text, visual_queries, scenes. Each scene has exactly narration, visual_query, purpose,
visual_mode, source_url, on_screen_text. Scenes are the source of truth.
"""

    def _improve_plan(self, research: ResearchPack, video_format: str, draft: dict) -> dict | None:
        prompt = f"""Act as CurioAxiom's fact-checking executive editor. Rewrite the draft JSON.
Research: {research.research_notes[:18000]}
Verification: {research.confidence_score:.0f}/100; {research.verification_notes}
Draft: {json.dumps(draft, ensure_ascii=False)}
Remove unsupported precision, myths, generic hooks, random-list structure, repeated visuals and false certainty.
Ensure one coherent cinematic question, two evidence beats, a mechanism/context explanation, caveat and reveal.
Return the complete corrected JSON only with the same keys and exact scene keys.
"""
        try:
            return self._generate_json(prompt)
        except Exception:
            return draft
