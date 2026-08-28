import json
import time

import httpx
from openai import OpenAI

from autopilot.config import Settings
from autopilot.models import ResearchPack, TopicCandidate, VideoPlan


class ScriptPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings

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
            "Choose ONE YouTube topic with the best combination of freshness, useful audience value, "
            "click potential and ability to make an original video without copying creators. "
            "Avoid politics, medical advice, financial promises and celebrity gossip. "
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

        target = "90-145 words" if video_format == "short" else "800-1200 words"
        visual_count = "4-7" if video_format == "short" else "10-16"
        source_text = research.research_notes[:16000]
        prompt = f"""You are producing an ORIGINAL YouTube {video_format} for this niche: {self.settings.channel_niche}.
Topic: {research.topic}
Research material follows. Treat it as evidence, not prose to copy:
{source_text}

Rules:
- Do not imitate, quote, paraphrase closely, or mention another creator's script.
- Write a fresh explanation from the verified facts in the supplied research.
- Do not invent statistics, dates, prices, product capabilities or quotes.
- Treat the topic/headline as a lead, NOT as verified evidence.
- Never call a product 'free', 'open source', 'unlimited', 'private', or similar unless the research itself supports that exact claim and you include material restrictions or licensing conditions when relevant.
- If sources conflict, prefer the more specific primary-source limitation and phrase the claim conservatively.
- If evidence is uncertain, say so briefly rather than guessing.
- Script target: {target}.
- Open with a strong non-clickbait hook and deliver useful information immediately.
- No fake urgency, guaranteed money claims, medical/financial advice, or unsupported superlatives.
- visual_queries must be generic stock-footage search phrases, not copyrighted brand footage requests.
- Generate {visual_count} visual_queries.
- thumbnail_text must be 2-4 punchy words and not misleading.

Return JSON only with keys: angle, hook, script, title, description, tags (array),
thumbnail_brief, thumbnail_text, visual_queries (array).
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
        configured = self.settings.gemini_model.strip()
        models = []
        # Prefer the current stable Flash model even if a stale repository variable
        # still points at an older model. Keep the configured model as a fallback.
        for model in (
            "gemini-3.7-flash",
            configured,
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
        ):
            if model and model not in models:
                models.append(model)

        transient_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None

        for model in models:
            for attempt in range(3):
                try:
                    return self._gemini_json_with_model(prompt, model)
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status = exc.response.status_code
                    if status == 404:
                        # Retired/unavailable model: move immediately to the next model.
                        break
                    if status in transient_statuses:
                        if attempt < 2:
                            time.sleep(2**attempt)
                            continue
                        # Repeated overload/rate-limit: try a different Flash model.
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
        raise RuntimeError("No Gemini model was available")

    def _gemini_json_with_model(self, prompt: str, model: str) -> dict:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        generation_config: dict[str, object] = {"responseMimeType": "application/json"}
        # Gemini 3.x migration guidance recommends removing legacy sampling
        # parameters. Keep temperature only for older compatible models.
        if not model.startswith("gemini-3"):
            generation_config["temperature"] = 0.4

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
                    f"Today we are looking at {topic}, without the hype.",
                    "The useful question is not whether a new tool sounds impressive, but what problem it actually solves, what evidence supports the claim, and what tradeoffs come with using it.",
                    "Start by checking the original product or announcement, then compare coverage from more than one independent source. Look for concrete capabilities, limitations, pricing changes, privacy implications and who the tool is actually meant for.",
                    "Next, test the idea on a small real task. Time the old workflow and the new workflow. If the new method saves time without reducing quality, it may be useful. If it only adds novelty, skip it.",
                    "For students and everyday users, the biggest wins usually come from removing repetitive work, organizing information, explaining difficult material, drafting first versions and helping you discover better resources. The final judgment still needs to stay with you.",
                    "The takeaway is simple: verify the source, test the workflow and keep only the tools that create a measurable improvement. That approach is much more useful than chasing every new launch.",
                ]
                * 4
            )
        else:
            script = (
                f"Everyone is talking about {topic}, but the headline is not the useful part. "
                "Check what the original source actually says, compare it with at least one independent report, "
                "then test the feature on one real task. Measure whether it saves time or improves quality. "
                "If it does neither, the hype does not matter. If it does, you found a workflow worth keeping. "
                "That simple verify-test-measure rule is the fastest way to separate useful technology from noise."
            )
        return VideoPlan(
            topic=topic,
            angle="Practical explainer focused on evidence and usefulness",
            format=video_format,
            hook=f"The headline about {topic} is not the useful part.",
            script=script,
            title=f"{topic}: What Actually Matters"[:100],
            description=f"An original, evidence-first explainer about {topic}.",
            tags=["AI", "technology", "tools", "explainer"],
            thumbnail_brief=f"Clean technology thumbnail representing {topic}.",
            thumbnail_text="WORTH THE HYPE?",
            visual_queries=["person using laptop", "technology workspace", "student productivity", "mobile app close up"],
            source_urls=[source.url for source in research.sources if source.url],
        )
