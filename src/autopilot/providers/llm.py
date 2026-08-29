import json
import time

import httpx
from openai import OpenAI

from autopilot.config import Settings
from autopilot.models import ResearchPack, TopicCandidate, VideoPlan


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

        target = "105-145 words" if video_format == "short" else "850-1150 words"
        visual_count = "9-12" if video_format == "short" else "16-22"
        source_text = research.research_notes[:18000]
        prompt = f"""You are the senior writer and editor for ByteVexa, a premium faceless technology channel.
Create an ORIGINAL YouTube {video_format} about: {research.topic}
Channel promise: useful technology explained quickly, clearly and without hype.

Research material follows. It is evidence, NOT prose to copy:
{source_text}

WRITING STANDARD
- Script target: {target}.
- Write for spoken delivery, not an article. Use natural contractions and varied sentence lengths.
- The first sentence must create curiosity through a concrete fact, problem, contrast or demonstration.
- Never begin with 'Everyone is talking about', 'Did you know', 'In today's video', 'Imagine this', 'Here's the thing', or 'This changes everything'.
- Give the viewer useful information within the first 2 sentences.
- Build one clean narrative: hook -> what changed/problem -> how it works -> why it matters -> practical takeaway.
- Avoid generic filler, motivational language, repetitive conclusions and obvious AI-writing phrases.
- Prefer specific examples supported by the research over broad claims.
- Do not imitate, quote, or closely paraphrase another creator.
- Do not invent statistics, dates, prices, capabilities or quotes.
- Treat headlines as leads, not verified evidence.
- Never call something free, private, unlimited, open-source, best, revolutionary or game-changing unless the evidence directly supports it and relevant limitations are included.
- If evidence is uncertain, say so briefly rather than guessing.
- No fake urgency, guaranteed money claims, medical/financial advice or unsupported superlatives.

EDITING / VISUAL STANDARD
- Generate {visual_count} visual_queries in the SAME ORDER as the narration beats.
- Each query must describe a concrete stock-video shot, e.g. 'close up hands typing laptop dark desk', not an abstract phrase like 'AI innovation'.
- Vary shot types: close-up, over-shoulder, phone usage, laptop workflow, reaction, study/office environment, device detail and server/data footage only when relevant.
- Do not request logos, copyrighted creator footage, YouTube screenshots or impossible footage.
- Do not repeat the same laptop shot with slightly different wording.

PACKAGING
- title: specific and curiosity-driven but truthful; ideally under 65 characters.
- description: 1-2 concise paragraphs explaining the payoff; no hype.
- tags: 5-10 relevant tags.
- thumbnail_text: 2-4 words, high contrast idea, not misleading.
- thumbnail_brief: one simple focal concept, not a cluttered collage.

Return JSON only with exactly these keys:
angle, hook, script, title, description, tags (array), thumbnail_brief, thumbnail_text, visual_queries (array).
"""
        data = self._generate_json(prompt)
        urls = [source.url for source in research.sources if source.url]
        return VideoPlan(topic=research.topic, format=video_format, source_urls=urls, **data)

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
            generation_config["temperature"] = 0.55

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
        if video_format == "long":
            script = " ".join(
                [
                    f"There is one useful question behind {topic}: what actually changes for the person using it?",
                    "Start with the original source, then compare independent coverage and look for concrete capabilities, limitations, pricing and privacy details.",
                    "Test the workflow on one small real task and compare the result with the old method. If it saves time without reducing quality, it may be worth keeping.",
                    "The point is not to chase every launch. It is to find technology that makes a measurable difference in a real workflow.",
                ]
                * 6
            )
        else:
            script = (
                f"The useful part of {topic} is not the headline. It is what changes in a real workflow. "
                "Check the original source, compare one independent report, then test the feature on a small task. "
                "Measure time saved and whether the result is actually better. If neither improves, skip the hype. "
                "That verify, test and measure rule is a faster way to find technology worth keeping."
            )
        return VideoPlan(
            topic=topic,
            angle="Practical explainer focused on evidence and usefulness",
            format=video_format,
            hook=f"The useful part of {topic} is not the headline.",
            script=script,
            title=f"{topic}: What Actually Matters"[:100],
            description=f"An original, evidence-first explainer about {topic}.",
            tags=["AI", "technology", "tools", "explainer"],
            thumbnail_brief=f"Clean technology thumbnail representing {topic}.",
            thumbnail_text="WORTH IT?",
            visual_queries=[
                "close up hands typing laptop dark desk",
                "over shoulder person using laptop software",
                "phone app close up hand scrolling",
                "modern study desk laptop screen",
                "person comparing information on computer",
                "close up keyboard and monitor workspace",
                "student using technology at desk",
                "minimal server room data center footage",
                "person finishing task on laptop",
            ],
            source_urls=[source.url for source in research.sources if source.url],
        )
