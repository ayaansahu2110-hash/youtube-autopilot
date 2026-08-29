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

        scenes = [SceneBeat(**scene) for scene in data.get("scenes", [])]
        if scenes:
            script = " ".join(scene.narration.strip() for scene in scenes if scene.narration.strip())
            data["script"] = script
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

    def _draft_prompt(self, research: ResearchPack, video_format: str) -> str:
        target = "105-145 words" if video_format == "short" else "850-1150 words"
        scene_count = "8-11" if video_format == "short" else "14-20"
        source_text = research.research_notes[:18000]
        return f"""You are the senior writer and visual editor for ByteVexa, a premium faceless technology channel.
Create an ORIGINAL YouTube {video_format} about: {research.topic}
Channel promise: useful technology explained quickly, clearly and without hype.

Research material follows. It is evidence, NOT prose to copy:
{source_text}

CONTENT STANDARD
- Script target: {target}.
- Cover ONE clear idea. Do not cram several unrelated developments into one Short.
- The viewer must learn at least 2 concrete, useful facts or actions that are supported by the research.
- The first sentence must create curiosity through a specific problem, capability, contrast or consequence.
- Never begin with 'Everyone is talking about', 'Did you know', 'In today's video', 'Imagine this', 'Here's the thing', or 'This changes everything'.
- Build one clean narrative: hook -> what is actually happening -> how it works -> why it matters -> practical takeaway.
- Prefer named features, concrete user actions and specific limitations supported by the evidence.
- Remove filler, generic praise, broad claims and repeated conclusions.
- Write for spoken delivery with contractions and natural sentence rhythm.
- Do not imitate or closely paraphrase another creator.
- Do not invent statistics, dates, prices, capabilities or quotes.
- Treat headlines as leads, not verified evidence.
- Never call something free, private, unlimited, open-source, best, revolutionary or game-changing unless evidence directly supports it and relevant limitations are included.
- If evidence is uncertain, state the uncertainty briefly.

SCENE-TO-VOICE ALIGNMENT
- Create {scene_count} scenes in exact narration order.
- Each scene must contain narration for ONLY that beat and ONE matching Pexels-friendly visual_query.
- The visual must literally illustrate what the narration is discussing at that moment.
- If narration says someone is typing a prompt, show a person typing on a laptop.
- If narration discusses a phone feature, show a phone being used.
- If narration discusses comparing results, show side-by-side work, reviewing screens or checking information.
- Do NOT use unrelated futuristic servers, robots, abstract AI graphics or generic office footage unless the narration specifically discusses infrastructure or offices.
- visual_query should be 3-8 concrete searchable words. Avoid brand names because stock search often fails on them.
- Vary framing only when it still matches the narration.

PACKAGING
- title: truthful, specific, curiosity-driven, ideally under 65 characters.
- description: concise and useful, no hype.
- tags: 5-10 relevant tags.
- thumbnail_text: 2-4 words, not misleading.
- thumbnail_brief: one simple focal concept.

Return JSON only with exactly these keys:
angle, hook, script, title, description, tags, thumbnail_brief, thumbnail_text, visual_queries, scenes.
scenes must be an array of objects with exactly: narration, visual_query, purpose.
The script and visual_queries should match the scenes, but scenes are the source of truth.
"""

    def _improve_plan(self, research: ResearchPack, video_format: str, draft: dict) -> dict | None:
        source_text = research.research_notes[:15000]
        review_prompt = f"""Act as a ruthless senior YouTube editor. Rewrite this draft only if needed so it feels specific, useful and visually coherent.

Topic: {research.topic}
Format: {video_format}
Research evidence:
{source_text}

Draft JSON:
{json.dumps(draft, ensure_ascii=False)}

Fix all of these problems if present:
- generic AI wording or filler
- weak hook
- claims not clearly supported by the research
- narration that says little beyond the headline
- scenes whose stock-video query does not literally match the narration beat
- too many abstract 'AI', server, robot, code or office shots
- repeated visual ideas
- vague advice with no concrete user takeaway

For Shorts, preserve a tight 105-145 word total and 8-11 scene beats. Every scene narration should usually be one short sentence or clause. Each scene visual_query must be 3-8 concrete Pexels-searchable words describing what should be on screen during that exact narration.

Return the complete corrected JSON only, using exactly the same keys as the draft, including scenes.
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
        scenes = [
            SceneBeat(
                narration=f"The useful question behind {topic} is what it changes in a real task.",
                visual_query="person using laptop at desk",
                purpose="hook",
            ),
            SceneBeat(
                narration="Start with the original source instead of the headline.",
                visual_query="person reading website on laptop",
                purpose="verify",
            ),
            SceneBeat(
                narration="Then compare one independent report for limitations and context.",
                visual_query="person comparing information on computer",
                purpose="compare",
            ),
            SceneBeat(
                narration="Test the feature on one small task you already do.",
                visual_query="hands typing laptop workflow",
                purpose="test",
            ),
            SceneBeat(
                narration="Keep it only if it saves time or improves the result.",
                visual_query="person reviewing finished work laptop",
                purpose="takeaway",
            ),
        ]
        if video_format == "long":
            scenes = scenes * 4
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
