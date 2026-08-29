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

        scenes = []
        for raw_scene in data.get("scenes", []):
            scene = dict(raw_scene or {})
            for field in ("narration", "visual_query", "purpose", "source_url", "on_screen_text"):
                scene[field] = str(scene.get(field) or "")
            scene["visual_mode"] = str(scene.get("visual_mode") or "motion")
            scenes.append(SceneBeat(**scene))
        if scenes:
            data["script"] = " ".join(
                scene.narration.strip() for scene in scenes if scene.narration.strip()
            )
            data["visual_queries"] = [scene.visual_query for scene in scenes]
        data.pop("scenes", None)

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
HYBRID VISUAL DIRECTION
Create {scene_count} scenes in exact narration order. Every scene must choose ONE visual_mode:
1) "ui" — use when the narration refers to a specific website/app/tool/interface and an approved source URL above can visually represent it. source_url MUST be copied exactly from an approved SOURCE_URL line.
2) "motion" — use for comparisons, concepts, steps, limitations, numbers, before/after ideas or anything stock footage would explain poorly. source_url must be empty.
3) "stock" — use only when real-world B-roll literally matches the narration, such as typing, using a phone, studying, filming or working at a desk. source_url must be empty.

Rules:
- Prefer ui or motion over generic stock. A premium tech channel should not look like random stock footage.
- Each scene narration should be a compact spoken beat that can naturally hold one visual idea.
- visual_query: 3-8 concrete words describing the exact scene. For ui scenes describe the interface area; for motion scenes describe the explanatory concept; for stock scenes use Pexels-searchable real-world wording.
- on_screen_text: 2-7 useful words that reinforce the narration; no clickbait.
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
angle, hook, script, title, description, tags, thumbnail_brief, thumbnail_text, visual_queries, scenes.
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

{format_rules}
Prefer a mix dominated by real UI and ByteVexa motion graphics. Stock should normally be a minority of scenes. UI source_url values must exactly match one approved URL. If no approved page genuinely fits a scene, use motion instead of inventing a URL.

Return the complete corrected JSON only, preserving the required top-level keys and these exact scene keys: narration, visual_query, purpose, visual_mode, source_url, on_screen_text.
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
