import json
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

    def create_plan(self, research: ResearchPack, video_format: str) -> VideoPlan:
        if not self.settings.llm_configured:
            return self._fallback_plan(research, video_format)

        draft = self._generate_json(self._draft_prompt(research, video_format))
        polished = self._improve_plan(research, video_format, draft)
        data = polished or draft
        if (self.settings.channel_profile != "curioaxiom" and video_format == "short"
                and len(data.get("scenes", [])) < 8):
            # A compact editor pass can accidentally collapse a visual story
            # into five or six cards. Ask for new distinct evidence beats;
            # keep the normal quality gate as the final authority.
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
                if isinstance(repaired.get("scenes"), list) and 8 <= len(repaired["scenes"]) <= 11:
                    data = repaired
            except Exception:
                pass

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
        content_mode = str(data.get("content_mode") or "general_explainer").strip().lower()
        if content_mode not in {"tool_review", "news_explainer", "general_explainer"}:
            content_mode = "general_explainer"
        data["content_mode"] = content_mode

        urls = [source.url for source in research.sources if source.url]
        return VideoPlan(
            topic=research.topic,
            format=video_format,
            source_urls=urls,
            scenes=scenes,
            **data,
        )

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
        return f"""You are the senior writer and visual editor for ByteVexa, a premium faceless technology channel.
Create an ORIGINAL YouTube {video_format} about: {research.topic}
Channel promise: useful technology explained quickly, clearly and without hype.

Research evidence:
{source_text}

Approved public source pages that may be visually captured:
{source_catalog}

CONTENT STANDARD
- Script target: {target}.
- Cover ONE clear idea. Do not cram unrelated developments together.
- The viewer must learn at least 2 concrete, useful facts or actions supported by the research.
- Give at least one specific limitation, condition, comparison, example or practical consequence when evidence supports it.
- The first sentence must create curiosity through a specific problem, capability, contrast or consequence.
- Never begin with 'Everyone is talking about', 'Did you know', 'In today's video', 'Imagine this', 'Here's the thing', or 'This changes everything'.
- Build one clean narrative: hook -> what is happening -> how it works -> why it matters -> practical takeaway.
- Prefer named features, concrete user actions and specific limitations over broad claims.
- Remove filler, generic praise, repeated conclusions and vague advice.
- Write for spoken delivery with contractions and natural sentence rhythm.
- Do not imitate another creator or invent statistics, dates, prices, capabilities or quotes.
- Treat headlines as leads, not verified evidence.
- Never call something free, private, unlimited, open-source, best, revolutionary or game-changing unless evidence directly supports it and limitations are included.
{longform_rules}
SHORT-FORM RETENTION AND DESIGN
- For a Short, make the first 1.5 seconds show the outcome, proof, or a sharp before/after contrast. Do not warm up with branding or a broad definition.
- Each beat must have one focal visual. Change the visual treatment every 2-4 seconds: product UI, an interactive-looking workflow, a result, a comparison, or a constraint.
- Use colour to communicate meaning: fresh/result, contrast/comparison, and caution/limitation. Do not specify a persistent banner, repeated full-screen text card, or a blue information strip.
- on_screen_text is a 1-4 word emphasis only, not a subtitle or sentence. The renderer adds separate spoken captions.

PRODUCT WALKTHROUGH MODE
- Return content_mode "tool_review" ONLY when the approved sources include the actual public product site and its public experience can honestly show the workflow. Otherwise return "news_explainer" or "general_explainer"; never pretend a landing page is a hands-on test.
- A tool_review needs this scene progression: hook/result, signup or access surface, main product surface, key feature, public workflow/input, visible output/result, pricing/free availability, an honest pros-vs-cons comparison, and a clear verdict. Use precise purpose labels: hook, signup, main, feature, workflow, output, pricing (or availability), pros_cons, takeaway.
- For tool_review, make signup/main/feature/workflow/output/pricing-or-availability scenes "ui" and use the exact approved official product URL. The pros_cons scene may be one compact two-column motion comparison; it must not become a recurring card style.
- Only show a workflow or output after a public no-login demo actually supports it. Never create an account, enter personal data, use a paywall, or imply access to a private dashboard. If price, free tier, or trial is not documented on the approved product page, say it is not verified instead of inventing it.
- The description link is added by the pipeline from the verified UI source. Do not invent a product URL.
HYBRID VISUAL DIRECTION
Create {scene_count} scenes in exact narration order. Every scene must choose ONE visual_mode:
1) "ui" — use when the narration refers to a specific website/app/tool/interface and an approved source URL above can visually represent it. source_url MUST be copied exactly from an approved SOURCE_URL line.
2) "motion" — use for comparisons, concepts, steps, limitations, numbers, before/after ideas or anything stock footage would explain poorly. source_url must be empty.
3) "stock" — use only when real-world B-roll literally matches the narration, such as typing, using a phone, studying, filming or working at a desk. source_url must be empty.

Rules:
- Prefer ui or motion over generic stock. A premium tech channel should not look like random stock footage.
- Each scene narration should be a compact spoken beat that can naturally hold one visual idea.
- visual_query: 3-8 concrete words describing the exact scene. For ui scenes describe the interface area; for motion scenes describe the explanatory concept; for stock scenes use Pexels-searchable real-world wording.
- on_screen_text: 1-4 useful words that reinforce the narration; no clickbait, sentences, or repeated branding.
- purpose: a short label such as hook, demo, limitation, comparison, takeaway.
- Never use robots, glowing brains, futuristic servers or abstract AI imagery unless the narration specifically discusses those things.
- The visual must explain the exact narration beat, not merely share the same broad topic.

PACKAGING
- title: truthful, specific, curiosity-driven, ideally under 65 characters.
- description: concise and useful, no hype.
- tags: 5-10 relevant tags.
- thumbnail_text: 2-4 words, not misleading.
- thumbnail_brief: one simple focal concept.

Return JSON only with exactly these top-level keys:
angle, content_mode, hook, script, title, description, tags, thumbnail_brief, thumbnail_text, visual_queries, scenes.
Each scenes item must contain exactly:
narration, visual_query, purpose, visual_mode, source_url, on_screen_text.
scenes are the source of truth for the final script and visuals.
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
        review_prompt = f"""Act as a ruthless senior YouTube editor and visual producer for ByteVexa.
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
- unnecessary stock footage where real UI or a motion-graphic explainer would be clearer
- repeated laptop/office shots
- vague advice with no concrete takeaway
- on-screen text that reads like a transcript, repeats branding, or would become a persistent banner
- a claimed software test that does not visibly show signup/access, the main product, a feature, a public workflow, an output, price/free availability, and a compact pros/cons decision

{format_rules}
Prefer a mix dominated by real UI and ByteVexa motion graphics. Stock should normally be a minority of scenes. UI source_url values must exactly match one approved URL. If no approved page genuinely fits a scene, use motion instead of inventing a URL.
Use content_mode "tool_review" only for an honestly capturable public product walkthrough. A tool_review must use the exact purpose sequence signup, main, feature, workflow, output, pricing (or availability), pros_cons and takeaway; its signup/main/feature/workflow/output/pricing scenes must be UI. A private dashboard, login wall, price guess, or generic landing-page montage is not a product test.
For Shorts, start with the concrete payoff in the first 1.5 seconds; use a visual switch every 2-4 seconds; and keep on_screen_text to a 1-4 word emphasis only. Never imitate another channel's scripts, graphics, wording, or branding.

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
        return json.loads(text.strip())

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
