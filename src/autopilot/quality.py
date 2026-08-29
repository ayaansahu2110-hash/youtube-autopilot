from difflib import SequenceMatcher

from autopilot.config import Settings
from autopilot.models import QualityReport, ResearchPack, VideoPlan
from autopilot.state import StateStore


class QualityGate:
    def __init__(self, settings: Settings, state: StateStore):
        self.settings = settings
        self.state = state

    def evaluate(self, plan: VideoPlan, research: ResearchPack, *, strict: bool) -> QualityReport:
        errors: list[str] = []
        warnings: list[str] = []
        words = len(plan.script.split())

        if plan.format == "short" and not 90 <= words <= 165:
            errors.append(f"Short script word count {words} is outside premium range 90-165.")
        if plan.format == "long" and not 700 <= words <= 1400:
            errors.append(f"Long script word count {words} is outside 700-1400.")
        if len(plan.title) > 100:
            errors.append("YouTube title exceeds 100 characters.")
        if strict and len(research.sources) < self.settings.min_research_sources:
            errors.append(
                f"Only {len(research.sources)} research source(s); minimum is {self.settings.min_research_sources}."
            )
        elif len(research.sources) < self.settings.min_research_sources:
            warnings.append("Research source count is below production minimum; dry-run allowed.")

        normalized_topic = plan.topic.lower().strip()
        for old in self.state.recent_topics(limit=80):
            similarity = SequenceMatcher(None, normalized_topic, old.lower().strip()).ratio()
            if similarity >= 0.86:
                errors.append(f"Topic is too similar to a recent topic ({similarity:.0%}).")
                break

        combined = f"{plan.title} {plan.script}".lower()
        risky_terms = {
            "guaranteed profit", "get rich quick", "medical cure", "diagnose yourself",
            "hack any account", "bypass copyright", "steal", "pirated",
        }
        hit = next((term for term in risky_terms if term in combined), None)
        if hit:
            errors.append(f"Risky or low-quality framing detected: {hit!r}.")

        generic_openers = (
            "everyone is talking about",
            "did you know",
            "in today's video",
            "imagine this",
            "here's the thing",
            "this changes everything",
        )
        script_start = plan.script.strip().lower()[:120]
        if any(opener in script_start for opener in generic_openers):
            errors.append("Generic AI-style hook detected; regenerate with a specific opening.")

        minimum_queries = 8 if plan.format == "short" else 14
        if len(plan.visual_queries) < minimum_queries:
            errors.append(
                f"Only {len(plan.visual_queries)} visual beats generated; need at least {minimum_queries}."
            )

        unique_queries = {query.lower().strip() for query in plan.visual_queries if query.strip()}
        if len(unique_queries) < minimum_queries:
            errors.append("Visual plan is too repetitive; regenerate with more distinct scene ideas.")

        return QualityReport(passed=not errors, errors=errors, warnings=warnings)
