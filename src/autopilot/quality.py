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

        if plan.format == "short" and not 55 <= words <= 180:
            errors.append(f"Short script word count {words} is outside 55-180.")
        if plan.format == "long" and not 650 <= words <= 1500:
            errors.append(f"Long script word count {words} is outside 650-1500.")
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

        risky_terms = {
            "guaranteed profit", "get rich quick", "medical cure", "diagnose yourself",
            "hack any account", "bypass copyright", "steal", "pirated",
        }
        combined = f"{plan.title} {plan.script}".lower()
        hit = next((term for term in risky_terms if term in combined), None)
        if hit:
            errors.append(f"Risky or low-quality framing detected: {hit!r}.")

        if not plan.visual_queries:
            warnings.append("No visual search queries were generated; fallback background will be used.")
        return QualityReport(passed=not errors, errors=errors, warnings=warnings)
