import json

from autopilot.learning import learning_context
from autopilot.models import ResearchPack
from autopilot.providers.llm import ScriptPlanner


class PremiumScriptPlanner(ScriptPlanner):
    """Keep the proven Shorts prompt, but use a deeper 8-12 minute plan for long-form."""

    def _draft_prompt(self, research: ResearchPack, video_format: str) -> str:
        if video_format != "long":
            return super()._draft_prompt(research, video_format)

        source_text = research.research_notes[:22000]
        source_catalog = self._source_catalog(research)
        learned = learning_context(self.settings)
        channel_name = self.settings.channel_display_name
        channel_niche = self.settings.channel_niche
        return f"""You are the senior writer, researcher and visual editor for {channel_name}, a premium channel specializing in {channel_niche}.
Create an ORIGINAL 8-12 minute YouTube long-form video about: {research.topic}
Channel promise: technology and scientific principles explained through useful real-world consequences, architecture, demos and honest limitations.

Research evidence:
{source_text}

Approved public source pages that may be visually captured:
{source_catalog}

Recent channel-learning signals:
{learned or 'No learning report is available yet.'}

Use those learning signals only to improve general patterns such as hook strength, topic specificity, pacing, title clarity, useful examples and viewer objections. Never copy another creator's wording, script structure beat-for-beat, thumbnail identity, catchphrases or branding.

CRITICAL MANDATORY LONG-FORM REQUIREMENTS:
- Total script MUST be between 1,200 and 1,550 spoken words (8 to 10 minutes spoken duration).
- Create exactly 32 to 38 scenes in exact chronological narration order.
- EVERY SINGLE SCENE'S 'narration' MUST BE 35 TO 50 SPOKEN WORDS (2 to 4 detailed spoken sentences explaining the setup, code, commands, mechanics, architecture, or evidence).
- DO NOT write 10-word outlines or brief bullet points. Each scene's narration will be synthesized as spoken voiceover.
- Cover one coherent topic deeply enough that a viewer finishes understanding what changed, how it works, where it helps, where it fails and whether it matters to them.
- State one concrete outcome, problem or surprising capability in the first 5 seconds. Do not begin with channel branding, history or broad context.
- Show proof of the promised result, a real demo step or decisive evidence within the first 30 seconds, before explaining the full setup.
- Structure the narrative: hook -> context -> what changed -> real workflow/demo -> concrete examples/results -> comparison -> limitations/catch -> who should use it -> practical takeaway.
- Include at least 5 concrete facts/actions/examples that are supported by research.
- Include at least one realistic use case for a normal person, student, creator, developer or knowledge worker when relevant.
- Explain jargon in plain English.
- Use transitions that create forward momentum without fake suspense.
- Every 30-45 seconds, reset attention with a useful question, visual proof, demo action, example, result, comparison, limitation or decision. Never stack more than five context/explanation scenes without one of these beats.
- Write for natural voiceover: vary sentence length, expand ambiguous acronyms on first use, avoid long comma-heavy lists, and use short transitions that sound conversational aloud.
- Never invent prices, dates, benchmarks, capabilities, quotes or statistics.
- Treat headlines as leads, not verified evidence.
- Do not imitate another creator's wording, pacing, catchphrases, graphics or brand identity.
- Avoid generic AI phrases such as 'game changer', 'the future is here', 'revolutionary', or 'this changes everything'.
- End with a concrete decision framework or action, not a generic subscribe-style conclusion.

LONG-FORM VISUAL DIRECTION
Create 32-38 scenes in exact narration order. Every scene must choose ONE visual_mode:
1) "ui" — real public product/interface evidence using an approved SOURCE_URL exactly.
2) "motion" — {channel_name} explanatory graphics for comparisons, concepts, steps, numbers, timelines, pros/cons, before/after and summaries.
3) "stock" — only literal real-world B-roll that directly matches the narration.

Visual rules:
- Prefer real UI + motion graphics; stock should remain a minority.
- Do not show the same landing-page state repeatedly. For product coverage, vary hero, feature section, examples/templates, input/demo, result/preview and limitation/support evidence when available.
- Each scene narration MUST be 35-50 spoken words.
- visual_query must describe the exact visual evidence needed.
- on_screen_text should be a 1-5 word visual emphasis, never a sentence, transcript or persistent banner.
- purpose should use clear labels such as hook, context, feature, workflow, demo, example, result, comparison, limitation, decision, takeaway.
- The visual must explain that exact narration beat.

PRODUCT WALKTHROUGH MODE
- Return content_mode "tool_review" only when an approved official product page can honestly support a public walkthrough. Otherwise use "news_explainer" or "general_explainer"; do not turn a landing page into a fake hands-on test.
- For tool_review, include and visibly label: signup/access, main product surface, feature, public workflow/input, visible output, official pricing/free availability, one compact pros_cons comparison, and takeaway. Signup/main/feature/workflow/output/pricing-or-availability must use real UI with the exact approved official URL.
- Do not create accounts, pass login walls, use paid credits or state a price/free tier without primary-source evidence. If a usable public workflow cannot be shown, choose an explainer instead of claiming a test.

PACKAGING
- title: truthful, specific and curiosity-driven, under 70 characters, promising one concrete outcome, test or decision.
- description: useful summary with no hype.
- tags: 6-12 relevant tags.
- thumbnail_text: 2-4 words.
- thumbnail_brief: one strong focal idea suitable for a premium tech thumbnail.

Return JSON only with exactly these top-level keys:
angle, content_mode, hook, script, title, description, tags, thumbnail_brief, thumbnail_text, visual_queries, scenes.
Each scenes item must contain exactly:
narration, visual_query, purpose, visual_mode, source_url, on_screen_text.
scenes are the source of truth for the final script and visuals.
"""

    def _improve_plan(self, research: ResearchPack, video_format: str, draft: dict) -> dict | None:
        if video_format != "long":
            return super()._improve_plan(research, video_format, draft)

        source_text = research.research_notes[:18000]
        source_catalog = self._source_catalog(research)
        learned = learning_context(self.settings)
        channel_name = self.settings.channel_display_name
        review_prompt = f"""Act as the executive editor for a premium {channel_name} 8-12 minute video.
Rewrite this draft until it is informative, tightly structured, visually varied and worth watching to the end.

Topic: {research.topic}
Research evidence:
{source_text}

Approved UI capture URLs:
{source_catalog}

Recent channel-learning signals:
{learned or 'No learning report is available yet.'}

Draft JSON:
{json.dumps(draft, ensure_ascii=False)}

REQUIRED FINAL STANDARD
- 1,200-1,550 total spoken words across 32-38 scene beats.
- EVERY scene narration MUST be 35-50 spoken words of substantive explanation (never short 10-word outlines).
- Strong real-world hook, not a generic introduction.
- At least 5 concrete researched facts/actions/examples.
- At least one workflow/demo sequence and one result/example sequence.
- At least one meaningful limitation/catch and one comparison/decision section.
- No filler, repeated conclusions, unsupported claims or vague praise.
- Make each section answer a new viewer question so the video keeps progressing; add a proof/demo/example/result/comparison/limitation/decision reset at least every five scenes.
- Make the narration conversational aloud: varied sentence length, clear acronym pronunciation and no long comma-heavy lists.
- Use recent learning to strengthen general audience-fit and retention patterns, but never imitate any creator or copy distinctive phrasing.
- Prefer actual UI evidence and custom motion graphics; stock remains a minority.
- Avoid repeating one public source page across many consecutive scenes.
- UI source_url values must exactly match an approved URL. If evidence is not visually capturable, use motion instead of inventing a URL.
- Preserve {channel_name}'s original voice; do not imitate any specific creator.

Return the complete corrected JSON only, preserving the required top-level keys including content_mode and exact scene keys: narration, visual_query, purpose, visual_mode, source_url, on_screen_text.
"""
        try:
            return self._generate_json(review_prompt)
        except Exception:
            return draft
