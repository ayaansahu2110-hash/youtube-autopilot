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

        short_max = 175 if self.settings.channel_profile == "curioaxiom" else 165
        if plan.format == "short" and not 90 <= words <= short_max:
            errors.append(f"Short script word count {words} is outside premium range 90-{short_max}.")
        if plan.format == "long" and not 1200 <= words <= 1650:
            errors.append(f"Long script word count {words} is outside 8-12 minute target 1200-1650.")
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

        minimum_queries = 8 if plan.format == "short" else 30
        if len(plan.visual_queries) < minimum_queries:
            errors.append(
                f"Only {len(plan.visual_queries)} visual beats generated; need at least {minimum_queries}."
            )

        unique_queries = {query.lower().strip() for query in plan.visual_queries if query.strip()}
        if len(unique_queries) < minimum_queries:
            errors.append("Visual plan is too repetitive; regenerate with more distinct scene ideas.")

        minimum_scenes = 8 if plan.format == "short" else 30
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
            incomplete_storyboards = 0
            mismatched_storyboards = 0
            shot_treatments: list[str] = []
            generator_prompts: list[str] = []
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
                if self.settings.channel_profile == "curioaxiom":
                    if not all((
                        scene.exact_visual_subject.strip(),
                        scene.camera_and_lighting.strip(),
                        scene.generator_prompt.strip(),
                        scene.shot_type_camera_movement.strip(),
                        scene.sfx_audio_cue.strip(),
                    )):
                        incomplete_storyboards += 1
                    spoken = {
                        token for token in re.findall(r"[a-z0-9]+", scene.narration.lower())
                        if len(token) >= 4
                    }
                    visual = set(re.findall(
                        r"[a-z0-9]+",
                        f"{scene.exact_visual_subject} {scene.generator_prompt}".lower(),
                    ))
                    query = {
                        token for token in re.findall(r"[a-z0-9]+", scene.visual_query.lower())
                        if len(token) >= 4
                    }
                    # One shared concrete term is sufficient here: morphology
                    # differs naturally (brake/braking, heat/heating), while a
                    # completely disjoint scene remains a hard failure.
                    if spoken and not (spoken & visual) and not (query & visual):
                        mismatched_storyboards += 1
                    shot_treatments.append(scene.shot_type_camera_movement.lower().strip())
                    generator_prompts.append(scene.generator_prompt.lower().strip())

            if weak_queries > max(1, len(plan.scenes) // 5):
                errors.append("Too many scene visuals are abstract or underspecified.")
            max_stock = int(len(plan.scenes) * (0.80 if self.settings.channel_profile == "curioaxiom" else 0.50))
            min_non_stock = (
                max(2, len(plan.scenes) // 5)
                if self.settings.channel_profile == "curioaxiom"
                else max(4, len(plan.scenes) // 2)
            )
            if stock_count > max_stock:
                errors.append("Hybrid visual plan relies too heavily on stock footage.")
            if non_stock_count < min_non_stock:
                errors.append("Not enough explanatory or source-grounded scenes were planned.")
            if missing_labels > max(1, len(plan.scenes) // 5):
                errors.append("Too many scenes are missing useful on-screen reinforcement text.")
            if invalid_ui_sources:
                errors.append("One or more UI scenes reference a source URL that research did not approve.")
            if incomplete_storyboards:
                errors.append("Every CurioAxiom scene needs a literal subject, camera/lighting plan and generator prompt.")
            if mismatched_storyboards:
                errors.append("One or more CurioAxiom visuals do not share enough literal detail with their narration.")
            if self.settings.channel_profile == "curioaxiom":
                if len(plan.title_options) != 3 or any(len(title) >= 50 for title in plan.title_options):
                    errors.append("CurioAxiom requires exactly three title options under 50 characters.")
                if len(plan.thumbnail_text.split()) != 3:
                    errors.append("CurioAxiom thumbnail text must contain exactly three words.")
                if not plan.direct_paste_script.strip():
                    errors.append("CurioAxiom requires an automation-ready script with bracketed visual cues.")
                if len(plan.batch_prompts) != len(plan.scenes):
                    errors.append("CurioAxiom requires one batch-generation prompt per scene.")
                if len(set(shot_treatments)) != len(shot_treatments):
                    errors.append("Camera treatment repeats across CurioAxiom scenes.")
                near_duplicate_prompts = any(
                    SequenceMatcher(None, left, right).ratio() >= 0.84
                    for index, left in enumerate(generator_prompts)
                    for right in generator_prompts[index + 1:]
                    if left and right
                )
                if near_duplicate_prompts:
                    errors.append("Generator prompts repeat the same visual concept too closely.")

            if plan.format in {"short", "long"}:
                evidence_beats = (
                    ("evidence", "mechanism", "scale", "reveal")
                    if self.settings.channel_profile == "curioaxiom"
                    else ("demo", "example", "workflow", "result")
                )
                if not any(any(word in purpose for word in evidence_beats) for purpose in purposes):
                    errors.append("Video lacks a concrete evidence or result beat.")
                ending_beats = (
                    ("limit", "catch", "comparison", "takeaway", "decision", "caveat", "reveal", "meaning")
                    if self.settings.channel_profile == "curioaxiom"
                    else ("limit", "catch", "comparison", "takeaway", "decision")
                )
                if not any(any(word in purpose for word in ending_beats) for purpose in purposes):
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
