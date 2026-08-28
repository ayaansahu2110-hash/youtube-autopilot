import json

from openai import OpenAI

from autopilot.config import Settings
from autopilot.models import VideoPlan


class ScriptPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def create_plan(self, topic: str, video_format: str) -> VideoPlan:
        if not self.settings.openai_api_key:
            return self._fallback_plan(topic, video_format)

        client = OpenAI(api_key=self.settings.openai_api_key)
        prompt = f"""Create an ORIGINAL YouTube {video_format} plan for the niche: {self.settings.channel_niche}.
Topic: {topic}
Do not imitate or paraphrase any specific creator. Return JSON only with keys:
angle, hook, script, title, description, tags (array), thumbnail_brief.
Make claims cautious and fact-checkable. Avoid fabricated statistics. Keep the script {'under 150 words' if video_format == 'short' else '900-1200 words'}.
"""
        response = client.responses.create(model=self.settings.openai_model, input=prompt)
        data = json.loads(response.output_text)
        return VideoPlan(topic=topic, format=video_format, **data)

    def _fallback_plan(self, topic: str, video_format: str) -> VideoPlan:
        script = (
            f"Most people hear about {topic} after it is already everywhere. "
            "Here is the useful part: what it is, why it matters, and one practical way to test it today. "
            "Before trusting any claim, check the original source, pricing, privacy terms, and whether the result actually saves you time. "
            "That simple test is more useful than hype."
        )
        return VideoPlan(
            topic=topic,
            angle="Practical explainer focused on usefulness rather than hype",
            format=video_format,
            hook=f"Before you ignore {topic}, know this.",
            script=script,
            title=f"{topic}: What Actually Matters",
            description=f"A concise, original explainer about {topic}. Verify tools and claims before relying on them.",
            tags=["AI", "technology", "tools", "explainer"],
            thumbnail_brief=f"Clean high-contrast thumbnail representing {topic}; 2-4 words maximum.",
        )
