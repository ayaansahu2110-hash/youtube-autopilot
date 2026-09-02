from __future__ import annotations

import json
from urllib.parse import urlparse

from autopilot.config import Settings
from autopilot.discovery import TopicDiscovery
from autopilot.models import ResearchPack, SceneBeat, TopicCandidate, VideoPlan
from autopilot.providers.premium_planner import PremiumScriptPlanner


AUTHORITATIVE_DOMAINS = {
    "science": ("nasa.gov", "noaa.gov", "esa.int", "nih.gov", "nature.com", "science.org"),
    "history": ("si.edu", "loc.gov", "archives.gov", "britishmuseum.org"),
    "geography": ("un.org", "worldbank.org", "usgs.gov", "noaa.gov"),
    "mathematics": ("ams.org", "maa.org", "mathworld.wolfram.com", "edu"),
    "space": ("nasa.gov", "esa.int", "jpl.nasa.gov", "noirlab.edu"),
    "engineering": ("nist.gov", "ieee.org", "asme.org", "sae.org", "faa.gov", "nasa.gov", "edu"),
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

    def _hacker_news(self, query: str) -> list[dict]:
        # Facts discovery must not drift into software opinion posts when a
        # news search is unavailable. Use an official science publisher instead.
        if not hasattr(self, "_official_feed_cache"):
            self._official_feed_cache = self._rss_search("https://www.nasa.gov/feed/")
        return list(self._official_feed_cache)

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
    _FINAL_CAMERA_CYCLE = (
        "24mm ultra-wide low-angle slow push-in",
        "50mm side-profile dynamic tracking pan",
        "35mm 90-degree top-down locked overhead",
        "85mm macro cross-section orbit",
        "70mm telephoto front-on slow pull-back",
        "18mm aerial descending crane move",
        "100mm extreme macro lateral slider",
        "40mm three-quarter handheld follow shot",
        "28mm ground-level tilt-up reveal",
        "60mm cutaway dolly left",
        "135mm compressed-profile rack focus",
        "32mm rear-axis stabilized chase",
        "90mm artifact detail clockwise arc",
        "20mm interior point-of-view rise",
        "55mm blueprint scan diagonal glide",
        "75mm high-angle counterclockwise orbit",
        "45mm Dutch-angle corrective roll to level",
        "105mm interior-to-exterior focus pull",
        "26mm left-to-right jib sweep",
        "65mm under-surface probe push",
        "30mm doorway-frame lateral reveal",
        "120mm edge-on material inspection tilt",
        "38mm reverse-tracking foreground wipe",
        "80mm static profile with subject crossing frame",
    )

    def create_plan(self, research: ResearchPack, video_format: str) -> VideoPlan:
        plan = super().create_plan(research, video_format)
        if video_format == "short" and len(plan.script.split()) > 145 and plan.scenes:
            self._fit_short_narration(plan, target_words=145)
        if video_format == "short" and len(plan.scenes) < 22:
            scenes = list(plan.scenes)
            while len(scenes) < 22:
                index = max(range(len(scenes)), key=lambda item: len(scenes[item].narration.split()))
                scene = scenes[index]
                words = scene.narration.split()
                if len(words) < 4:
                    break
                midpoint = len(words) // 2
                left = scene.model_copy(
                    update={
                        "narration": " ".join(words[:midpoint]),
                        "visual_query": scene.visual_query + " wide cinematic footage",
                    }
                )
                right = SceneBeat(
                    narration=" ".join(words[midpoint:]),
                    visual_query=scene.visual_query + " close detail footage",
                    purpose=scene.purpose,
                    visual_mode=scene.visual_mode,
                    source_url=scene.source_url,
                    on_screen_text=scene.on_screen_text,
                    exact_visual_subject=scene.exact_visual_subject,
                    camera_and_lighting=scene.camera_and_lighting,
                    generator_prompt=scene.generator_prompt,
                    shot_type_camera_movement=scene.shot_type_camera_movement,
                    sfx_audio_cue=scene.sfx_audio_cue,
                )
                scenes[index:index + 1] = [left, right]
            plan.scenes = scenes
            plan.script = " ".join(scene.narration.strip() for scene in scenes)
            plan.visual_queries = [scene.visual_query for scene in scenes]
        # Scene splitting happens after the base planner's normalization. Rebuild all
        # visual-directing fields from the final scene list so no child scene inherits
        # its parent's camera treatment or prompt.
        aspect = "9:16" if video_format == "short" else "16:9"
        grades = ("cool steel", "warm tungsten", "neutral daylight", "deep cobalt")
        for index, scene in enumerate(plan.scenes):
            camera = self._FINAL_CAMERA_CYCLE[index % len(self._FINAL_CAMERA_CYCLE)]
            scene.shot_type_camera_movement = camera
            subject = scene.exact_visual_subject.strip() or scene.visual_query.strip()
            scene.exact_visual_subject = subject
            scene.generator_prompt = (
                f"Literal depiction of: {scene.narration.strip()} Subject: {subject}. "
                f"Visible action and context: {scene.visual_query.strip()}. Shot: {camera}. "
                f"Lighting: {scene.camera_and_lighting.strip() or 'physically accurate documentary lighting'}. "
                f"Vertical {aspect} composition, realistic materials and physics, no unrelated objects, "
                "no logos, no captions, no text overlay."
            )
        plan.visual_queries = [scene.visual_query for scene in plan.scenes]
        plan.direct_paste_script = "\n\n".join(
            f"[Scene {index + 1}: {scene.generator_prompt}] {scene.narration.strip()}"
            for index, scene in enumerate(plan.scenes)
        )
        plan.batch_prompts = [
            f"{scene.generator_prompt} {grades[index % len(grades)]} documentary color grade --ar {aspect}"
            for index, scene in enumerate(plan.scenes)
        ]
        return plan

    @staticmethod
    def _fit_short_narration(plan: VideoPlan, *, target_words: int) -> None:
        """Keep every story beat while enforcing a predictable Shorts duration."""
        scene_words = [scene.narration.split() for scene in plan.scenes]
        total = sum(len(words) for words in scene_words)
        if total <= target_words:
            return
        minimum = 3
        budgets = [
            max(minimum, int(target_words * len(words) / max(1, total)))
            for words in scene_words
        ]
        while sum(budgets) < target_words:
            index = max(
                range(len(budgets)),
                key=lambda item: len(scene_words[item]) - budgets[item],
            )
            if budgets[index] >= len(scene_words[index]):
                break
            budgets[index] += 1
        while sum(budgets) > target_words:
            index = max(range(len(budgets)), key=lambda item: budgets[item] - minimum)
            if budgets[index] <= minimum:
                break
            budgets[index] -= 1
        for scene, words, budget in zip(plan.scenes, scene_words, budgets):
            shortened = " ".join(words[:budget]).rstrip(",;:-")
            if shortened and shortened[-1] not in ".!?":
                shortened += "."
            scene.narration = shortened
        plan.script = " ".join(scene.narration for scene in plan.scenes)

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
        scenes = "20-24" if video_format == "short" else "28-38"
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
- For a Short, make the first sentence understandable in under two seconds and introduce a new
  asset, action, angle, scale, or consequence every 1.5-2.7 seconds. Each scene is one visual action.
- Never stretch, split, loop or reuse one image/clip to fill multiple consecutive timeline segments.
- ZERO-MISMATCH STORYBOARD: every visible object/action must be justified by the exact words spoken
  in that scene. Never use generic topical filler, decorative scientists, random laboratories,
  unrelated rockets, landscapes, office footage or broad mood shots.
- ZERO-REPETITION: never reuse an asset, framing, scene concept, camera angle, movement, visual prompt,
  background composition or explanatory device. Repeated subjects must change physical perspective:
  wide environment -> macro material detail -> dynamic tracking action -> cutaway/thermal/blueprint evidence.
- Rotate shot grammar deliberately across scenes: slow push-in -> dynamic tracking/pan -> 90-degree
  top-down -> physically accurate 3D cross-section/cutaway, then continue with new focal lengths and axes.
- Include two concrete verified facts, an explanation of the mechanism or cause, and a caveat.
- End on the meaning of the answer, not generic engagement bait.
- Choose visual_mode motion or stock (ui only for an essential authoritative source page).
- Make 70-85% of scenes stock: real, cinematic, physically relevant moving footage. Write short searchable
  queries describing footage that plausibly exists, such as "space capsule reentry", "arc jet heat
  shield test" or "capsule parachute landing". Never request impossible CGI as stock footage.
- Reserve motion for at most one third of scenes and only for diagrams, maps, scale, timelines or
  mechanisms that cannot be filmed. UI source_url must exactly match a research URL.
- on_screen_text is 2-5 punchy words that add meaning rather than repeat the narration. purpose uses hook, evidence, context, mechanism, scale, reveal,
  caveat or takeaway. Avoid repeated or generic visuals.
- exact_visual_subject states the literal subject, object, action and state visible on screen.
- camera_and_lighting specifies shot size/angle, movement, focal point and physically appropriate lighting.
- shot_type_camera_movement gives the precise lens/framing and camera move and must be unique per scene.
- sfx_audio_cue names one restrained transition or mechanism sound synchronized to the visible action.
- generator_prompt is a standalone copy-pasteable prompt for an AI video generator. It must restate
  the literal subject and action, camera direction, environment, lighting, vertical 9:16 composition,
  realistic physics and exclusions needed to prevent mismatched objects. Do not merely say cinematic or 8K.
- title_options contains exactly 3 truthful high-CTR alternatives under 50 characters; title is the best one.
- thumbnail_text is exactly 3 bold words; thumbnail_brief specifies foreground subject, focal contrast and background.
- direct_paste_script combines the exact narration in order with bracketed generator-ready visual cues.
- batch_prompts contains one unique prompt per scene, in order, each ending in --ar 9:16 for Shorts
  or --ar 16:9 for long-form and including a scene-specific color grade.

PACKAGING
- Specific truthful title under 70 characters; 2-4 word thumbnail text; 6-12 relevant tags.
- Description summarizes the answer and preserves uncertainty.

Return JSON only with exactly: angle, hook, script, title, title_options, description, tags,
thumbnail_brief, thumbnail_text, visual_queries, direct_paste_script, batch_prompts, scenes. Each scene has exactly
narration, visual_query, purpose, visual_mode, source_url, on_screen_text, exact_visual_subject,
camera_and_lighting, generator_prompt, shot_type_camera_movement, sfx_audio_cue. Scenes are the source of truth.
"""

    def _improve_plan(self, research: ResearchPack, video_format: str, draft: dict) -> dict | None:
        prompt = f"""Act as CurioAxiom's fact-checking executive editor. Rewrite the draft JSON.
Research: {research.research_notes[:18000]}
Verification: {research.confidence_score:.0f}/100; {research.verification_notes}
Draft: {json.dumps(draft, ensure_ascii=False)}
Remove unsupported precision, myths, generic hooks, random-list structure, repeated visuals and false certainty.
Ensure one coherent cinematic question, two evidence beats, a mechanism/context explanation, caveat and reveal.
Reject every generic or merely topic-adjacent visual. Confirm each prompt literally depicts that scene's
spoken nouns, action, scale and consequence. Reject repeated subjects shown from the same physical
perspective, repeated camera moves, repeated compositions and prompts that differ only by adjectives.
Return the complete corrected JSON only with the same keys
and exact scene keys.
"""
        try:
            return self._generate_json(prompt)
        except Exception:
            return draft
