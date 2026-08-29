import json

from autopilot.models import ResearchPack
from autopilot.providers.llm import ScriptPlanner


class PremiumScriptPlanner(ScriptPlanner):
    """Keep the proven Shorts prompt, but use a deeper 8-12 minute plan for long-form."""

    def _draft_prompt(self, research: ResearchPack, video_format: str) -> str:
        if video_format != "long":
            return super()._draft_prompt(research, video_format)

        source_text = research.research_notes[:22000]
        source_catalog = self._source_catalog(research)
        return f"""You are the senior writer, researcher and visual editor for ByteVexa, a premium faceless technology channel.
Create an ORIGINAL 8-12 minute YouTube long-form video about: {research.topic}
Channel promise: current AI and technology explained through useful real-world consequences, demos and honest limitations.

Research evidence:
{source_text}

Approved public source pages that may be visually captured:
{source_catalog}

LONG-FORM CONTENT STANDARD
- Target 1,250-1,750 spoken words. Do not pad with filler.
- Cover one coherent topic deeply enough that a viewer finishes understanding what changed, how it works, where it helps, where it fails and whether it matters to them.
- Open with a specific real-world consequence or surprising capability in the first 15 seconds.
- Structure the narrative: hook -> context -> what changed -> real workflow/demo -> concrete examples/results -> comparison -> limitations/catch -> who should use it -> practical takeaway.
- Include at least 5 concrete facts/actions/examples that are supported by research.
- Include at least one realistic use case for a normal person, student, creator, developer or knowledge worker when relevant.
- Explain jargon in plain English.
- Use transitions that create forward momentum without fake suspense.
- Every 30-60 seconds, introduce a new useful question, example, comparison, result or limitation so retention does not flatten.
- Never invent prices, dates, benchmarks, capabilities, quotes or statistics.
- Treat headlines as leads, not verified evidence.
- Do not imitate another creator's wording, pacing, catchphrases, graphics or brand identity.
- Avoid generic AI phrases such as 'game changer', 'the future is here', 'revolutionary', or 'this changes everything'.
- End with a concrete decision framework or action, not a generic subscribe-style conclusion.

LONG-FORM VISUAL DIRECTION
Create 26-34 scenes in exact narration order. Every scene must choose ONE visual_mode:
1) "ui" — real public product/interface evidence using an approved SOURCE_URL exactly.
2) "motion" — ByteVexa explanatory graphics for comparisons, concepts, steps, numbers, timelines, pros/cons, before/after and summaries.
3) "stock" — only literal real-world B-roll that directly matches the narration.

Visual rules:
- Prefer real UI + motion graphics; stock should remain a minority.
- Do not show the same landing-page state repeatedly. For product coverage, vary hero, feature section, examples/templates, input/demo, result/preview and limitation/support evidence when available.
- Each scene narration should normally be 25-60 spoken words so visuals change regularly without becoming frantic.
- visual_query must describe the exact visual evidence needed.
- on_screen_text should be 2-7 useful words.
- purpose should use clear labels such as hook, context, feature, workflow, demo, example, result, comparison, limitation, decision, takeaway.
- The visual must explain that exact narration beat.

PACKAGING
- title: truthful, specific and curiosity-driven, ideally under 65 characters.
- description: useful summary with no hype.
- tags: 6-12 relevant tags.
- thumbnail_text: 2-4 words.
- thumbnail_brief: one strong focal idea suitable for a premium tech thumbnail.

Return JSON only with exactly these top-level keys:
angle, hook, script, title, description, tags, thumbnail_brief, thumbnail_text, visual_queries, scenes.
Each scenes item must contain exactly:
narration, visual_query, purpose, visual_mode, source_url, on_screen_text.
scenes are the source of truth for the final script and visuals.
"""

    def _improve_plan(self, research: ResearchPack, video_format: str, draft: dict) -> dict | None:
        if video_format != "long":
            return super()._improve_plan(research, video_format, draft)

        source_text = research.research_notes[:18000]
        source_catalog = self._source_catalog(research)
        review_prompt = f"""Act as the executive editor for a premium ByteVexa 8-12 minute technology video.
Rewrite this draft until it is informative, tightly structured, visually varied and worth watching to the end.

Topic: {research.topic}
Research evidence:
{source_text}

Approved UI capture URLs:
{source_catalog}

Draft JSON:
{json.dumps(draft, ensure_ascii=False)}

REQUIRED FINAL STANDARD
- 1,250-1,750 spoken words and 26-34 scene beats.
- Strong real-world hook, not a generic introduction.
- At least 5 concrete researched facts/actions/examples.
- At least one workflow/demo sequence and one result/example sequence.
- At least one meaningful limitation/catch and one comparison/decision section.
- No filler, repeated conclusions, unsupported claims or vague praise.
- Make each section answer a new viewer question so the video keeps progressing.
- Prefer actual UI evidence and custom motion graphics; stock remains a minority.
- Avoid repeating one public source page across many consecutive scenes.
- UI source_url values must exactly match an approved URL. If evidence is not visually capturable, use motion instead of inventing a URL.
- Preserve ByteVexa's original voice; do not imitate any specific creator.

Return the complete corrected JSON only, preserving the required top-level keys and exact scene keys: narration, visual_query, purpose, visual_mode, source_url, on_screen_text.
"""
        try:
            return self._generate_json(review_prompt)
        except Exception:
            return draft
