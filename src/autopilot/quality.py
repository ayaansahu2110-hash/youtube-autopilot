import re
from collections import Counter
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
        if plan.format == "long" and not 1150 <= words <= 1900:
            errors.append(f"Long script word count {words} is outside 8-12 minute range 1150-1900.")
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
        script_start = plan.script.strip().lower()[:140]
        if any(opener in script_start for opener in generic_openers):
            errors.append("Generic AI-style hook detected; regenerate with a specific opening.")

        shallow_phrases = (
            "worth the hype",
            "the future is here",
            "technology is changing fast",
            "work smarter not harder",
            "game changer",
            "revolutionary tool",
            "unlock your potential",
        )
        shallow_hits = sum(phrase in combined for phrase in shallow_phrases)
        if shallow_hits >= 2:
            errors.append("Script contains too much generic AI/influencer filler.")

        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", plan.script) if item.strip()]
        if plan.format == "short" and len(sentences) < 5:
            errors.append("Short is too thin: fewer than 5 meaningful narration beats.")

        minimum_queries = 8 if plan.format == "short" else 24
        if len(plan.visual_queries) < minimum_queries:
            errors.append(
                f"Only {len(plan.visual_queries)} visual beats generated; need at least {minimum_queries}."
            )

        unique_queries = {query.lower().strip() for query in plan.visual_queries if query.strip()}
        if len(unique_queries) < minimum_queries:
            errors.append("Visual plan is too repetitive; regenerate with more distinct scene ideas.")

        minimum_scenes = 8 if plan.format == "short" else 24
        if len(plan.scenes) < minimum_scenes:
            errors.append(f"Only {len(plan.scenes)} scene-aligned narration beats; need {minimum_scenes}.")
        else:
            scene_script = " ".join(scene.narration.strip() for scene in plan.scenes).strip()
            similarity = SequenceMatcher(None, scene_script.lower(), plan.script.strip().lower()).ratio()
            if similarity < 0.94:
                errors.append("Scene narration and final script are not synchronized closely enough.")

            generic_visual_terms = {"ai", "technology", "innovation", "future", "digital", "data"}
            weak_queries = 0
            approved_urls = {source.url for source in research.sources if source.url}
            stock_count = 0
            non_stock_count = 0
            missing_labels = 0
            invalid_ui_sources = 0
            purposes: list[str] = []
            ui_sources: list[str] = []

            for scene in plan.scenes:
                terms = {token for token in re.findall(r"[a-z0-9]+", scene.visual_query.lower())}
                if len(terms) < 3 or terms.issubset(generic_visual_terms):
                    weak_queries += 1
                if scene.visual_mode == "stock":
                    stock_count += 1
                else:
                    non_stock_count += 1
                if not scene.on_screen_text.strip():
                    missing_labels += 1
                if scene.visual_mode == "ui":
                    ui_sources.append(scene.source_url)
                    if scene.source_url not in approved_urls:
                        invalid_ui_sources += 1
                purposes.append(scene.purpose.lower().strip())

            if weak_queries > max(1, len(plan.scenes) // 5):
                errors.append("Too many scene visuals are abstract or underspecified.")
            if stock_count > len(plan.scenes) // 2:
                errors.append("Hybrid visual plan relies too heavily on stock footage.")
            if non_stock_count < max(4, len(plan.scenes) // 2):
                errors.append("Not enough real-UI or ByteVexa motion-graphic scenes were planned.")
            if missing_labels > max(1, len(plan.scenes) // 5):
                errors.append("Too many scenes are missing useful on-screen reinforcement text.")
            if invalid_ui_sources:
                errors.append("One or more UI scenes reference a source URL that research did not approve.")

            if plan.format in {"short", "long"}:
                if not any(any(word in purpose for word in ("demo", "example", "workflow", "result")) for purpose in purposes):
                    errors.append("Video lacks a concrete demo/example/result beat.")
                if not any(any(word in purpose for word in ("limit", "catch", "comparison", "takeaway", "decision")) for purpose in purposes):
                    errors.append("Video lacks a limitation/comparison/takeaway beat.")
                source_counts = Counter(url for url in ui_sources if url)
                repeat_limit = max(3, len(plan.scenes) // 3) if plan.format == "long" else max(3, len(plan.scenes) // 2)
                if source_counts and max(source_counts.values()) > repeat_limit:
                    errors.append("Too many scenes reuse the same product page; show more varied evidence or explanatory visuals.")

        if len(research.sources) >= 3:
            warnings.append("Research depth is strong: three or more independent source pages were available.")
        elif strict:
            warnings.append("Only two substantive sources were available; script must remain conservative.")

        return QualityReport(passed=not errors, errors=errors, warnings=warnings)
