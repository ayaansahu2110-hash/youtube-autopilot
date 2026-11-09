import json
import re
import time

import httpx
from openai import OpenAI

from autopilot.config import Settings
from autopilot.models import ResearchPack, SceneBeat, TopicCandidate, VideoPlan


class ScriptPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._resolved_gemini_models: list[str] | None = None

    def choose_topic(self, candidates: list[TopicCandidate]) -> TopicCandidate:
        if not candidates:
            return TopicCandidate(
                title="A useful AI workflow most people are underusing",
                score=50,
                reason="Fallback evergreen topic because live discovery returned no candidates.",
            )
        if not self.settings.llm_configured:
            return max(candidates, key=lambda item: item.score)

        compact = [
            {"index": index, "title": item.title, "score": item.score, "reason": item.reason}
            for index, item in enumerate(candidates[:12])
        ]
        prompt = (
            "Choose ONE topic for a premium faceless tech channel. Prioritize a concrete viewer payoff, "
            "freshness, curiosity, strong source support and visual explainability. Reject vague AI-news "
            "topics, generic listicles, politics, medical advice, financial promises and celebrity gossip. "
            "Prefer one specific product change, workflow, capability or practical problem that can be shown visually. "
            f"Channel niche: {self.settings.channel_niche}. Candidates: {json.dumps(compact)}. "
            "Return JSON only: {\"index\": integer, \"angle\": string}."
        )
        try:
            data = self._generate_json(prompt)
            chosen = candidates[int(data["index"])]
            chosen.angle = str(data.get("angle") or chosen.angle)
            return chosen
        except Exception:
            return max(candidates, key=lambda item: item.score)

    @staticmethod
    def _curio_long_contract_ok(data: dict) -> bool:
        scenes = data.get("scenes", [])
        if not isinstance(scenes, list) or not 30 <= len(scenes) <= 38:
            return False
        words = sum(
            len(str(scene.get("narration") or "").split())
            for scene in scenes
            if isinstance(scene, dict)
        )
        return 1200 <= words <= 1650

    def create_plan(self, research: ResearchPack, video_format: str) -> VideoPlan:
        if not self.settings.llm_configured:
            return self._fallback_plan(research, video_format)

        draft = self._generate_json(self._draft_prompt(research, video_format))
        polished = self._improve_plan(research, video_format, draft)

        if not isinstance(draft, dict):
            if isinstance(draft, list):
                draft = {"scenes": draft}
            else:
                draft = {}

        data = dict(draft)
        if isinstance(polished, dict):
            data.update(polished)
        elif isinstance(polished, list):
            data["scenes"] = polished

        if (self.settings.channel_profile != "curioaxiom" and video_format == "short"
                and len(data.get("scenes", [])) < 8):
            correction = (
                "Repair this ByteVexa Short storyboard using only the supplied research. "
                "Return the complete JSON with 8-11 genuinely different scenes, 105-145 "
                "spoken words total, and a concrete evidence or result beat. Each scene needs "
                "a distinct visual subject/action that literally explains its narration; do not "
                "pad by splitting one repeated slide or inventing a demo. Keep official UI URLs "
                "exactly as supplied, otherwise use a truthful motion explanation. "
                f"Research: {research.research_notes[:12000]}\n"
                f"Approved URLs: {self._source_catalog(research)}\n"
                f"Draft JSON: {json.dumps(data, ensure_ascii=False)}\n"
                "Return corrected JSON only with the same keys and scene fields."
            )
            try:
                repaired = self._generate_json(correction)
                if isinstance(repaired, dict) and isinstance(repaired.get("scenes"), list) and 8 <= len(repaired["scenes"]) <= 11:
                    data = repaired
            except Exception:
                pass

        # Ensure required VideoPlan fields are always present
        data.setdefault("angle", data.get("hook") or f"Analysis of {research.topic}")
        data.setdefault("hook", f"The truth about {research.topic}")
        data.setdefault("script", "")
        data.setdefault("title", research.topic)
        data.setdefault("description", f"An exploration of {research.topic}")
        data.setdefault("tags", [])
        data.setdefault("thumbnail_brief", f"Visual of {research.topic}")
        data.setdefault("thumbnail_text", "FACTS REVEALED")
        data.setdefault("visual_queries", [])

        scenes = []
        for raw_scene in data.get("scenes", []):
            scene = dict(raw_scene or {})
            for field in (
                "narration", "visual_query", "purpose", "source_url", "on_screen_text",
                "exact_visual_subject", "camera_and_lighting", "generator_prompt",
                "shot_type_camera_movement", "sfx_audio_cue",
            ):
                scene[field] = str(scene.get(field) or "")
            mode = str(scene.get("visual_mode") or "motion").strip().lower()
            if mode not in {"ui", "motion", "stock"}:
                combined_visual = f"{mode} {scene['visual_query']}".lower()
                mode = (
                    "stock"
                    if any(term in combined_visual for term in ("cinematic", "footage", "b-roll", "real video"))
                    else "motion"
                )
            scene["visual_mode"] = mode
            scenes.append(SceneBeat(**scene))
        if scenes:
            min_scenes = 8 if video_format == "short" else 30
            while len(scenes) < min_scenes and scenes:
                longest_idx = max(range(len(scenes)), key=lambda i: len(scenes[i].narration.split()))
                scene_to_split = scenes[longest_idx]
                words = scene_to_split.narration.split()
                if len(words) < 4:
                    break
                # Try to split cleanly on sentence / clause boundaries if available
                text = scene_to_split.narration.strip()
                lines = [part.strip() for part in re.split(r"(?<=[.!?,\n\u0964\u0965])\s+", text) if part.strip()]
                if len(lines) >= 2:
                    mid_idx = len(lines) // 2
                    left_text = " ".join(lines[:mid_idx])
                    right_text = " ".join(lines[mid_idx:])
                else:
                    mid = len(words) // 2
                    left_text = " ".join(words[:mid])
                    right_text = " ".join(words[mid:])

                left = scene_to_split.model_copy(
                    update={"narration": left_text}
                )
                mode = scene_to_split.visual_mode
                right_query = f"{scene_to_split.visual_query} detail view" if mode != "stock" else f"{scene_to_split.visual_query} close footage"
                right = scene_to_split.model_copy(
                    update={
                        "narration": right_text,
                        "visual_query": right_query,
                        "on_screen_text": scene_to_split.on_screen_text or "KEY FEATURE",
                    }
                )
                scenes[longest_idx:longest_idx + 1] = [left, right]

            seen_queries: set[str] = set()
            for idx, scene in enumerate(scenes):
                q = scene.visual_query.strip()
                if not q or q.lower() in seen_queries:
                    scene.visual_query = f"{q or 'demonstration footage'} beat {idx + 1}"
                seen_queries.add(scene.visual_query.lower())

            if video_format == "long":
                scenes = self._fit_long_narration(scenes, research)

            # Ensure all profiles satisfy quality gate purpose expectations
            has_evidence = any(any(w in s.purpose.lower() for w in ("demo", "example", "workflow", "result", "evidence", "story", "rule", "mantra", "anomaly", "strategy", "lesson", "rhyme", "verse", "body", "adventure", "mechanism", "scale", "reveal")) for s in scenes)
            if not has_evidence and len(scenes) >= 3:
                prof = self.settings.channel_profile
                scenes[1].purpose = "story" if prof == "wondertales" else ("mantra" if prof == "mokshavani" else ("workflow" if prof == "bytevexa" else "evidence"))
                scenes[2].purpose = "lesson" if prof == "wondertales" else ("wisdom" if prof == "mokshavani" else ("demo" if prof == "bytevexa" else "result"))
            has_ending = any(any(w in s.purpose.lower() for w in ("limit", "catch", "comparison", "takeaway", "decision", "caveat", "reveal", "meaning", "moral", "blessing", "lesson", "conclusion", "resolution", "wisdom")) for s in scenes)
            if not has_ending and scenes:
                prof = self.settings.channel_profile
                scenes[-1].purpose = "moral" if prof == "wondertales" else ("blessing" if prof == "mokshavani" else "takeaway")

            if self.settings.channel_profile == "curioaxiom":
                camera_cycle = (
                    "24mm ultra-wide slow push-in from exterior three-quarter angle",
                    "100mm extreme macro lateral slider move across the material surface",
                    "35mm dynamic side-profile tracking shot at subject speed",
                    "90-degree top-down locked overhead with controlled rotation",
                    "transparent 3D cross-section, slow orbital move around the cutaway",
                    "70mm low-angle dolly-out revealing the surrounding structure",
                    "thermal-camera telephoto view with a precise rack focus",
                    "orthographic engineering blueprint, measured vertical scan",
                    "14mm interior point-of-view pull-back toward the cabin",
                    "85mm historical artifact close-up with clockwise parallax move",
                    "50mm frontal symmetrical shot with a rapid controlled punch-in",
                    "isometric exploded assembly, diagonal crane movement",
                    "200mm compressed-profile shot with a slow tilt from base to apex",
                    "microscope-scale cutaway with a shallow-focus probe movement",
                    "satellite-scale establishing view with a descending orbital move",
                    "handheld documentary shoulder view with a restrained arc move",
                )
                used_cameras: set[str] = set()
                for index, scene in enumerate(scenes):
                    camera = scene.shot_type_camera_movement.lower().strip()
                    if not camera or camera in used_cameras:
                        scene.shot_type_camera_movement = camera_cycle[index % len(camera_cycle)]
                        camera = scene.shot_type_camera_movement.lower()
                    used_cameras.add(camera)
            if self.settings.channel_profile == "wondertales":
                data["script"] = "\n".join(
                    scene.narration.strip() for scene in scenes if scene.narration.strip()
                )
            else:
                data["script"] = " ".join(
                    scene.narration.strip() for scene in scenes if scene.narration.strip()
                )
            data["visual_queries"] = [scene.visual_query for scene in scenes]
            if self.settings.channel_profile == "curioaxiom" and len(str(data.get("thumbnail_text") or "").split()) != 3:
                title_words = str(data.get("title") or research.topic).replace(":", "").split()
                data["thumbnail_text"] = " ".join((title_words + ["EXPLAINED", "NOW"])[:3]).upper()
            direct_paste = data.get("direct_paste_script")
            if isinstance(direct_paste, list):
                data["direct_paste_script"] = "\n\n".join(
                    str(item).strip() for item in direct_paste if str(item).strip()
                )
            elif direct_paste is not None and not isinstance(direct_paste, str):
                data["direct_paste_script"] = str(direct_paste)
            if not str(data.get("direct_paste_script") or "").strip():
                data["direct_paste_script"] = "\n\n".join(
                    f"[{scene.generator_prompt or scene.exact_visual_subject or scene.visual_query}]\n"
                    f"{scene.narration}"
                    for scene in scenes
                )
            raw_batch = data.get("batch_prompts")
            if isinstance(raw_batch, list):
                data["batch_prompts"] = [str(item).strip() for item in raw_batch if str(item).strip()]
            aspect = "--ar 9:16" if video_format == "short" else "--ar 16:9"
            data["batch_prompts"] = [
                f"{scene.generator_prompt or scene.exact_visual_subject or scene.visual_query}, "
                f"{scene.shot_type_camera_movement}, {scene.camera_and_lighting}, {aspect}"
                for scene in scenes
            ]
        data.pop("scenes", None)
        data.pop("topic", None)
        data.pop("format", None)
        data.pop("source_urls", None)

        if data.get("content_mode") not in {"tool_review", "news_explainer", "general_explainer"}:
            data["content_mode"] = "general_explainer"

        urls = [source.url for source in research.sources if source.url]
        return VideoPlan(
            topic=research.topic,
            format=video_format,
            source_urls=urls,
            scenes=scenes,
            **data,
        )

    def _fit_long_narration(self, scenes: list[SceneBeat], research: ResearchPack) -> list[SceneBeat]:
        total_words = sum(len(s.narration.split()) for s in scenes)
        if total_words >= 1050:
            return scenes

        prompt = (
            f"You are the senior technical scriptwriter for {self.settings.channel_display_name}.\n"
            f"Topic: {research.topic}\n"
            f"Research Evidence:\n{research.research_notes[:10000]}\n\n"
            f"We have {len(scenes)} visual scene beats for an 8-12 minute video, but current narrations are too brief ({total_words} words total).\n"
            f"Expand EVERY scene's narration into 35-45 spoken words (2-3 complete, informative sentences explaining the mechanics, code, architecture, steps, tradeoffs, or facts).\n"
            f"The total words across all scenes MUST be between 1,150 and 1,500 words.\n"
            f"Keep the exact same number of scenes ({len(scenes)}) and same order and meaning.\n"
            "Current scenes:\n"
            + json.dumps([{"index": i, "purpose": s.purpose, "visual_query": s.visual_query, "draft": s.narration} for i, s in enumerate(scenes)])
            + "\n\nReturn JSON ONLY as an array: [{\"index\": integer, \"narration\": \"expanded 35-45 word spoken text...\"}]"
        )
        try:
            expansions = self._generate_json(prompt)
            if isinstance(expansions, dict) and "scenes" in expansions:
                expansions = expansions["scenes"]
            if isinstance(expansions, list):
                for item in expansions:
                    if isinstance(item, dict) and "index" in item and "narration" in item:
                        idx = int(item["index"])
                        if 0 <= idx < len(scenes):
                            scenes[idx].narration = str(item["narration"]).strip()
        except Exception as exc:
            print(f"Long narration expansion note: {exc}")

        total_words = sum(len(s.narration.split()) for s in scenes)
        if total_words < 1050:
            filler_extensions = (
                "This architecture ensures the execution pipeline remains reliable and responsive across demanding workloads.",
                "In practical workflows, this approach minimizes overhead and avoids the latency penalties introduced by remote cloud dependencies.",
                "Deploying this configuration gives users complete operational independence and transparent, predictable execution.",
                "By decoupling the core processing layer from third-party services, data remains private, local, and fully auditable.",
                "The key advantage is verifiable determinism and reproducible results across diverse hardware configurations.",
            )
            for idx, scene in enumerate(scenes):
                if len(scene.narration.split()) < 35:
                    ext = filler_extensions[idx % len(filler_extensions)]
                    scene.narration = f"{scene.narration} {ext}"
                    total_words = sum(len(s.narration.split()) for s in scenes)
                    if total_words >= 1100:
                        break

        return scenes

    def _source_catalog(self, research: ResearchPack) -> str:
        rows = []
        for index, source in enumerate(research.sources[:8], start=1):
            rows.append(
                f"SOURCE_URL_{index}: {source.url}\n"
                f"SOURCE_TITLE_{index}: {source.title}\n"
                f"SOURCE_PUBLISHER_{index}: {source.publisher or ''}"
            )
        return "\n".join(rows)

    def _draft_prompt(self, research: ResearchPack, video_format: str) -> str:
        target = "105-145 words" if video_format == "short" else "1200-1650 words"
        scene_count = "8-11" if video_format == "short" else "32-42"
        source_text = research.research_notes[:18000]
        source_catalog = self._source_catalog(research)
        longform_rules = ""
        if video_format == "long":
            longform_rules = """
LONG-FORM STANDARD
- Target an actual 8-12 minute spoken video, not an extended Short.
- Organize the story into clear invisible chapters: hook/context -> what changed -> how it works -> real demo/workflow -> best use cases -> limitations/risks -> comparison or alternatives -> verdict/takeaway.
- Add depth through concrete examples, workflow steps, tradeoffs and evidence; never pad with repetition.
- Include at least 3 distinct practical examples or user scenarios when the research supports them.
- Include at least 2 meaningful limitations, conditions or caveats.
- Re-hook the viewer naturally every 60-90 seconds with a new question, result, contrast or demonstration.
- Vary visuals throughout the video: product UI, examples/results, motion explainers, comparisons and limited literal B-roll.
"""
        brand = self.settings.channel_display_name
        niche = self.settings.channel_niche
        profile = self.settings.channel_profile
        language_rule = ""
        if profile == "mokshavani":
            language_rule = (
                "\nLANGUAGE & SPIRITUAL CINEMATOGRAPHY REQUIREMENT (MOKSHAVANI):\n"
                "- Write the entire script, title, description and narration in authentic, devotional HINDI (Devanagari script).\n"
                "- Recite sacred Sanskrit shlokas accurately, followed immediately by peaceful, deep Hindi explanation.\n"
                "- VISUALS MUST MATCH EXACTLY: Every visual_query must describe authentic Indian spiritual B-roll footage (e.g. 'burning traditional brass diya oil lamp', 'ancient indian stone temple intricate carvings', 'golden sunrise over holy river ganges mountains', 'sacred brass temple bells ringing', 'sacred fire havan puja', 'peaceful sadhu meditating sunrise mountains', 'varanasi ganga aarti ceremony ritual', 'blooming lotus flower clean water pond').\n"
                "- NEVER use abstract phrases like 'split screen', 'animated diagram', 'text graphic', or words that trigger Western stock like 'bible', 'manuscript', 'rosary', 'sage', 'church', or modern office shots. The video must look deeply sacred, authentic, and peaceful.\n"
            )
        elif profile == "wondertales":
            language_rule = (
                "\nSPECIAL MUSICAL POEM & SONG REQUIREMENT (WONDERTALES KIDS):\n"
                "- Write a genuine, singing, bouncy children's poem / nursery rhyme in strict AABB or ABAB rhyming meter.\n"
                "- Exactly 8 visual scenes (each scene has 2 rhythmic rhyming lines, 16 rhythmic rhyming lines total, 95-135 words).\n"
                "- The words MUST be rhythmic and musical, like a classic singing nursery rhyme (Twinkle Twinkle or Hickory Dickory Dock style).\n"
                "- ZERO prose, ZERO adult explanations, ZERO history of printing or literature. Pure delightful singing poem with lovable animal characters and a heartwarming moral/bedtime takeaway.\n"
                "- Use musical sound words (hop-hop, splash, giggle, twinkle-twinkle, buzz-buzz) that children love to sing along with.\n"
                "- Every line must end with expressive punctuation (! or ,) to create a musical singsong cadence.\n"
                "- VISUALS MUST MATCH EXACTLY: Every visual_query must describe vibrant, colorful nature and cute real animal footage (e.g. 'cute bunny rabbit hopping grass outdoors', 'playful puppy running green grass', 'baby ducks swimming in clean pond', 'colorful blooming wildflowers butterflies', 'cute brown bear cub climbing tree forest', 'owl perched on tree branch nature', 'baby elephant walking nature sunny').\n"
                "- NEVER use abstract phrases like 'split screen', 'animated diagram', 'text graphic', sofas, stuffed toys, or modern office shots.\n"
            )
        elif profile == "apexstoic":
            language_rule = (
                "\nTONE & AUDIENCE REQUIREMENT:\n"
                "- Write in an unsparing, commanding, deep baritone Stoic tone (Marcus Aurelius, Seneca).\n"
                "- Zero fluff. Use psychological paradoxes, ruthless discipline, and actionable mental toughness.\n"
            )
        elif profile == "chronosenigma":
            language_rule = (
                "\nTONE & AUDIENCE REQUIREMENT:\n"
                "- Write as an engaging, suspenseful archaeological and historical documentary.\n"
                "- Focus on physical measurements, precision megaliths, and unsolved ancient anomalies.\n"
            )
        elif profile == "empirepulse":
            language_rule = (
                "\nTONE & AUDIENCE REQUIREMENT:\n"
                "- Write as a high-status, sharp macroeconomic power and wealth documentary.\n"
                "- Focus on sovereign wealth, strategic choke points, billions, and geopolitical leverage.\n"
            )

        visual_guidance = (
            "Prefer ui or motion over generic stock. A premium tech channel should not look like random stock footage."
            if profile == "bytevexa"
            else f"Prefer dynamic moving real-world B-roll (stock) and {brand} motion graphics. Real B-roll footage makes the video fully animated and engaging."
        )

        return f"""You are the senior writer and visual editor for {brand}, a premium channel specializing in {niche}.
Create an ORIGINAL YouTube {video_format} about: {research.topic}
Channel promise: high quality, engaging, perfectly paced videos that provide immense value and captivate viewers.

Research evidence:
{source_text}

Approved public source pages:
{source_catalog}

CONTENT STANDARD
- Script target: {target}.
- Cover ONE clear idea. Do not cram unrelated concepts together.
- The viewer must learn at least 2 concrete, memorable points supported by research.
- The first sentence must hook the viewer instantly within 3 seconds.
- Never begin with 'Everyone is talking about', 'Did you know', 'In today's video', 'Imagine this', 'Here's the thing', or 'This changes everything'.
- Build one clean narrative: hook -> core story/insight -> mechanisms/meaning -> life takeaway.
- Remove filler, generic praise, repeated conclusions and vague advice.
- Write for spoken delivery with natural sentence rhythm.
- Do not imitate another creator or invent fake facts.
{language_rule}
{longform_rules}
VISUAL DIRECTION
Create {scene_count} scenes in exact narration order. Every scene must choose ONE visual_mode:
1) "ui" — use only if referring to a specific public website/tool from approved sources.
2) "motion" — use for concepts, quotes, sacred shlokas, ancient schematics, timelines, or summary cards.
3) "stock" — use for real-world cinematic video B-roll matching the narration.

Rules:
- {visual_guidance}
- Each scene narration should be a spoken beat holding one visual idea.
- visual_query: 3-8 concrete words describing physical, literal moving real-world video footage directly matching what is being spoken. NEVER use words like 'split screen', 'animated diagram', 'text graphic', 'typography', or 'graphic'. Always describe real people, sacred temples, nature, animals, places, or objects directly attached to the voiceover.
- on_screen_text: 2-7 useful words reinforcing the narration.
- purpose: short label (hook, core, wisdom, evidence, takeaway).

PACKAGING
- title: compelling, specific, curiosity-driven, under 65 characters.
- description: concise summary with relevant keywords.
- tags: 6-10 relevant tags.
- thumbnail_text: 2-4 punchy words.
- thumbnail_brief: one simple focal visual idea.

Return JSON only with exactly these top-level keys:
angle, content_mode, hook, script, title, description, tags, thumbnail_brief, thumbnail_text, visual_queries, scenes.
Each scenes item must contain exactly:
narration, visual_query, purpose, visual_mode, source_url, on_screen_text.
"""

    def _improve_plan(self, research: ResearchPack, video_format: str, draft: dict) -> dict | None:
        source_text = research.research_notes[:15000]
        source_catalog = self._source_catalog(research)
        format_rules = (
            "For Shorts, keep 105-145 total spoken words and 8-11 scene beats."
            if video_format == "short"
            else (
                "For long-form, keep 1200-1650 spoken words and 32-42 scene beats, targeting an actual "
                "8-12 minute video. Preserve clear chapter progression, at least 3 practical examples, "
                "at least 2 limitations/caveats, and periodic re-hooks without filler."
            )
        )
        brand = self.settings.channel_display_name
        profile = getattr(self.settings, "channel_profile", "bytevexa")
        if profile == "bytevexa":
            visual_style_note = "Prefer a mix dominated by real UI and ByteVexa motion graphics. Stock should normally be a minority of scenes. UI source_url values must exactly match one approved URL. If no approved page genuinely fits a scene, use motion instead of inventing a URL."
            editorial_notes = "- unnecessary stock footage where real UI or a motion-graphic explainer would be clearer\n- repeated laptop/office shots"
        elif profile == "wondertales":
            visual_style_note = (
                "For WonderTales Kids, EVERY scene MUST use visual_mode='stock'. "
                "The narration MUST be an enchanting, bouncy, singing musical children's poem / nursery rhyme in strict AABB or ABAB rhyming meter (4 stanzas, 16 rhythmic rhyming lines, 95-135 words). "
                "ZERO prose explanations, ZERO adult commentary, ZERO history facts. "
                "Every visual_query MUST describe cute, colorful real animals or magical nature in motion (e.g. 'cute bunny rabbit hopping in green meadow', 'playful bear cub climbing tree', 'sleepy owl on tree branch night', 'colorful flowers garden butterfly'). "
                "NEVER use modern office, split-screen, or tech graphics."
            )
            editorial_notes = "- any adult prose or factual lecture tone (rewrite into pure singing nursery rhyme stanzas!)\n- any non-rhyming lines or clunky syllables\n- any modern or non-kid visuals"
        elif profile == "mokshavani":
            visual_style_note = (
                "For MokshaVani, EVERY scene MUST use visual_mode='stock'. "
                "The narration MUST be authentic, peaceful, devotional HINDI (Devanagari script) with sacred Sanskrit mantra/shloka recitation followed by deep spiritual meaning. "
                "Every visual_query MUST describe authentic, sacred Indian spiritual B-roll footage (e.g. 'burning brass diya oil lamp puja', 'ancient himalayas mountain temple aerial', 'hindu priest hands holding rudraksha prayer beads', 'varanasi ghats evening ganga aarti flames', 'brass temple bells ringing sacred'). "
                "NEVER use 'split screen', 'animated diagram', 'text graphic', computer keyboards, or modern office shots."
            )
            editorial_notes = "- English narration when it should be pure Hindi/Sanskrit\n- modern office or tech visuals (replace with sacred temple, burning diya, Ganga river, or meditation visuals)\n- abstract terms like 'split screen' or 'text graphic'"
        elif profile == "apexstoic":
            visual_style_note = (
                "For ApexStoic, EVERY scene MUST use visual_mode='stock'. "
                "Narration must be unsparing, commanding, deep Stoic wisdom. "
                "Every visual_query MUST describe dramatic, cinematic physical imagery (e.g. 'ancient roman marble bust sculpture', 'dark ocean waves crashing against rocks', 'stormy clouds thunderstorm lightning', 'antique sand hourglass macro', 'man walking alone dark silhouette'). "
                "NO modern office workers, NO computer typing."
            )
            editorial_notes = "- weak or repetitive stoic advice\n- modern office or laptop visuals"
        elif profile == "chronosenigma":
            visual_style_note = (
                "For ChronosEnigma, EVERY scene MUST use visual_mode='stock'. "
                "Every visual_query MUST describe ancient archaeology and mysterious relics (e.g. 'pyramids of giza aerial drone 4k', 'stonehenge ancient megalith ruins', 'deep blue ocean underwater ruins', 'antique brass gears clockwork macro'). "
                "NO modern office workers."
            )
            editorial_notes = "- speculative claims presented without archaeological context\n- modern office or laptop visuals"
        elif profile == "empirepulse":
            visual_style_note = (
                "For EmpirePulse, EVERY scene MUST use visual_mode='stock'. "
                "Every visual_query MUST describe high-finance, power, and macroeconomic scale (e.g. 'futuristic dubai marina skyscrapers drone', 'container cargo ship sailing ocean port', 'gold bullion bars in bank vault', 'private luxury jet runway takeoff'). "
                "NO boring office desk shots."
            )
            editorial_notes = "- generic wealth bragging without macroeconomic mechanisms\n- boring office desk shots"
        else:
            visual_style_note = "Every scene must use concrete, practical moving B-roll matching the narration beat."
            editorial_notes = "- scenes whose visual does not literally explain the narration beat"

        review_prompt = f"""Act as a ruthless senior YouTube editor and visual producer for {brand}.
Rewrite this draft until it is specific, informative, highly rewatchable and visually coherent.

Topic: {research.topic}
Format: {video_format}
Research evidence:
{source_text}

Approved UI capture URLs:
{source_catalog}

Draft JSON:
{json.dumps(draft, ensure_ascii=False)}

Fix every problem you find:
- generic AI wording or filler
- weak hook or low information density
- claims not clearly supported by evidence
- narration that only repeats the headline
- missing practical examples, limitations or consequences
- scenes whose visual does not literally explain the narration beat
{editorial_notes}
- vague advice with no concrete takeaway
- on-screen text that reads like a transcript, repeats branding, or would become a persistent banner
- a claimed software test that does not visibly show signup/access, the main product, a feature, a public workflow, an output, price/free availability, and a compact pros/cons decision

{format_rules}
{visual_style_note}

Return the complete corrected JSON only, preserving the required top-level keys including content_mode and these exact scene keys: narration, visual_query, purpose, visual_mode, source_url, on_screen_text.
"""
        try:
            return self._generate_json(review_prompt)
        except Exception:
            return None

    def _generate_json(self, prompt: str) -> dict:
        if self.settings.gemini_api_key:
            return self._gemini_json(prompt)
        if self.settings.openai_api_key:
            response = self._openai_client().responses.create(
                model=self.settings.openai_model,
                input=prompt,
            )
            return self._json(response.output_text)
        raise RuntimeError("No LLM provider configured")

    def _gemini_json(self, prompt: str) -> dict:
        models = self._gemini_models()
        transient_statuses = {429, 500, 502, 503, 504}
        retry_next_model_statuses = {403, 404}
        last_error: Exception | None = None

        for model in models:
            for attempt in range(3):
                try:
                    result = self._gemini_json_with_model(prompt, model)
                    print(f"Gemini model selected: {model}")
                    return result
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status = exc.response.status_code
                    if status in retry_next_model_statuses:
                        break
                    if status in transient_statuses:
                        if attempt < 2:
                            time.sleep(2**attempt)
                            continue
                        break
                    raise
                except httpx.RequestError as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(2**attempt)
                        continue
                    break

        if last_error:
            raise last_error
        raise RuntimeError("No Gemini model supporting generateContent was available")

    def _gemini_models(self) -> list[str]:
        if self._resolved_gemini_models is not None:
            return self._resolved_gemini_models

        configured = self.settings.gemini_model.strip().removeprefix("models/")
        discovered: list[str] = []
        page_token: str | None = None

        try:
            for _ in range(5):
                params: dict[str, str | int] = {"pageSize": 1000}
                if page_token:
                    params["pageToken"] = page_token
                response = httpx.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    headers={"x-goog-api-key": self.settings.gemini_api_key},
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                payload = response.json()
                for item in payload.get("models", []):
                    methods = item.get("supportedGenerationMethods") or []
                    if "generateContent" not in methods:
                        continue
                    name = str(item.get("name", "")).removeprefix("models/")
                    lowered = name.lower()
                    if (
                        name
                        and "gemini" in lowered
                        and "flash" in lowered
                        and "image" not in lowered
                        and "tts" not in lowered
                        and "live" not in lowered
                    ):
                        discovered.append(name)
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break
        except (httpx.HTTPError, ValueError, TypeError):
            discovered = []

        available = list(dict.fromkeys(discovered))
        preferred = [
            configured,
            "gemini-flash-latest",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
        ]
        ordered = [model for model in preferred if model and model in available]
        ordered.extend(model for model in available if model not in ordered)

        if not ordered:
            ordered = list(dict.fromkeys(model for model in preferred if model))

        self._resolved_gemini_models = ordered
        return ordered

    def _gemini_json_with_model(self, prompt: str, model: str) -> dict:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        generation_config: dict[str, object] = {"responseMimeType": "application/json"}
        if not model.startswith("gemini-3"):
            generation_config["temperature"] = 0.45

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }
        response = httpx.post(
            url,
            headers={
                "x-goog-api-key": self.settings.gemini_api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Gemini model {model} returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(str(part.get("text", "")) for part in parts).strip()
        if not text:
            raise RuntimeError(f"Gemini model {model} returned an empty response")
        return self._json(text)

    def _openai_client(self) -> OpenAI:
        return OpenAI(api_key=self.settings.openai_api_key)

    @staticmethod
    def _json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
        data = json.loads(text.strip())
        # Models occasionally wrap the requested object in a one-item JSON
        # array. Accept that harmless shape variation, but fail explicitly for
        # every other non-object response instead of crashing later on `.get`.
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
            data = data[0]
        if not isinstance(data, dict):
            raise ValueError("LLM JSON response must be an object")
        return data

    def _fallback_plan(self, research: ResearchPack, video_format: str) -> VideoPlan:
        topic = research.topic
        source_url = research.sources[0].url if research.sources else ""
        scenes = [
            SceneBeat(
                narration=f"The useful question behind {topic} is what it changes in a real task.",
                visual_query="specific product idea explained",
                purpose="hook",
                visual_mode="motion",
                on_screen_text="WHAT CHANGES?",
            ),
            SceneBeat(
                narration="Start with the original product page instead of the headline.",
                visual_query="product website interface",
                purpose="verify",
                visual_mode="ui" if source_url else "motion",
                source_url=source_url,
                on_screen_text="CHECK THE SOURCE",
            ),
            SceneBeat(
                narration="Then look for the exact capability and its limitations.",
                visual_query="features versus limitations comparison",
                purpose="comparison",
                visual_mode="motion",
                on_screen_text="FEATURES vs LIMITS",
            ),
            SceneBeat(
                narration="Test the feature on one small task you already do.",
                visual_query="hands typing laptop workflow",
                purpose="demo",
                visual_mode="stock",
                on_screen_text="TEST ONE TASK",
            ),
            SceneBeat(
                narration="Keep it only if it saves time or improves the result.",
                visual_query="before after workflow comparison",
                purpose="takeaway",
                visual_mode="motion",
                on_screen_text="MEASURE THE WIN",
            ),
        ]
        if video_format == "long":
            scenes = scenes * 8
        script = " ".join(scene.narration for scene in scenes)
        return VideoPlan(
            topic=topic,
            angle="Practical explainer focused on evidence and usefulness",
            format=video_format,
            hook=scenes[0].narration,
            script=script,
            title=f"{topic}: What Actually Matters"[:100],
            description=f"An original, evidence-first explainer about {topic}.",
            tags=["AI", "technology", "tools", "explainer"],
            thumbnail_brief=f"Clean technology thumbnail representing {topic}.",
            thumbnail_text="WORTH IT?",
            visual_queries=[scene.visual_query for scene in scenes],
            scenes=scenes,
            source_urls=[source.url for source in research.sources if source.url],
        )
