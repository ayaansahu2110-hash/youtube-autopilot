"""
GTA6Hub Premium Script Planner
-------------------------------
Specialized script planner for GTA6Hub gaming channel.
Produces high-energy, YouTube-gaming-channel-style scripts with:
- Punchy hooks in the first 2 seconds
- Fast-cut structure matched to energetic B-roll queries
- Viral gaming Short format (45-55s, 115-145 words)
- Long-form gaming guide format (8-12 min, 1200-1550 words)
- GTA-6-specific vocabulary and content angles
"""
from __future__ import annotations

import json

from autopilot.models import ResearchPack
from autopilot.providers.llm import ScriptPlanner


class GTA6HubScriptPlanner(ScriptPlanner):
    """High-energy gaming script planner — built exclusively for GTA6Hub."""

    # Pexels visual queries that ACTUALLY work for GTA 6 gaming content
    # (These return high-quality urban/action/vice-city-aesthetic footage)
    _GTA6_STOCK_QUERIES = [
        # Urban/Vice City aesthetic
        "miami beach aerial drone sunset neon",
        "night city neon lights aerial",
        "palm trees sunset miami beach florida",
        "neon city lights night time lapse",
        "luxury sports car highway speed",
        # Action/gameplay adjacent
        "urban street chase city night",
        "police car lights sirens night",
        "speedboat ocean miami sunset",
        "helicopter aerial city night lights",
        "luxury yacht marina ocean sunset",
        # Character/story
        "woman city street confident walking",
        "man running urban environment cinematic",
        "close up hands on car steering wheel",
        # Map/exploration
        "florida keys aerial turquoise water",
        "everglades alligator nature aerial",
        "miami skyline golden hour reflection",
        # Action B-roll
        "explosion urban building cinematic",
        "motorcycle speed city night blur",
        "skydiving aerial city view",
    ]

    def _draft_prompt(self, research: ResearchPack, video_format: str) -> str:
        source_text = research.research_notes[:18000]
        channel_name = "GTA6Hub"
        niche = "GTA 6 gaming commentary, secrets, and guides"

        if video_format == "short":
            return f"""You are the head writer for GTA6Hub, the fastest-growing GTA 6 YouTube channel.
Write a HIGH-ENERGY gaming Short about: {research.topic}

Research evidence:
{source_text}

MANDATORY GAMING SHORT FORMAT:
- Total spoken words: exactly 115-145 words (45-55 seconds at gaming pace)
- Structure: HOOK (5 words max, no intro) → REVEAL → 3 PUNCHY FACTS/DETAILS → SUBSCRIBE CTA
- Voice: Energetic, fast, authoritative gaming commentator — NOT a robot, NOT a news anchor
- Tone: Like the best GTA YouTubers (think SunsetDrive, Typical Gamer energy — fast, excited, specific)
- NEVER start with: "Hey guys", "Welcome back", "Did you know", "In today's video", "Imagine"
- MUST start with the most shocking/interesting thing immediately
- Every sentence is SHORT (5-12 words). No long winding sentences.
- Include EXACTLY one clear call to action at the end (subscribe / follow for more)

GAMING SHORT SCENES: Create exactly 10-12 fast-cut scenes.
Every scene narration = 10-15 words max (one punchy sentence per scene)
Every visual_query = exact description of GTA-aesthetic video B-roll:
  Examples: "miami neon night aerial drone", "luxury sports car highway night", 
  "urban street chase police lights city", "palm trees sunset florida beach aerial",
  "florida coastline aerial drone turquoise water", "neon city skyline time lapse night",
  "speedboat ocean miami sunset fast", "helicopter city aerial cinematic night",
  "woman confident city street night neon lights", "man running urban cinematic chase"

visual_mode: ALWAYS "stock" for GTA6Hub Shorts

PACKAGING — this is what gets clicks:
- title: Under 60 chars. Gaming viral format: "[Shocking Thing] in GTA 6 Nobody Noticed" or 
  "GTA 6 Hides [Secret] and Players Are LOSING IT" or "This GTA 6 Detail BREAKS THE INTERNET"
  — Include "GTA 6" in title for SEO. Use CAPS for 1 word for emphasis.
- description: First 2 lines must be hook sentences (shown in YouTube preview). Include 
  #GTA6 #GTA6Shorts #GrandTheftAutoVI #GTA6Secrets in description.
- tags: ["GTA 6", "GTA VI", "GTA 6 secrets", "GTA 6 Easter eggs", "GTA 6 tips", 
  "Grand Theft Auto 6", "GTA 6 gameplay", "Rockstar Games", "GTA 6 hidden", "GTA 6 guide"]
- thumbnail_text: 3-4 CAPS words like "NOBODY KNEW THIS" or "INSANE DETAIL" or "MIND BLOWN"
- thumbnail_brief: Bright neon Vice City aesthetic — close-up of shocking detail OR Jason/Lucia face

Return JSON only with these exact keys:
angle, content_mode, hook, script, title, description, tags, thumbnail_brief, thumbnail_text, visual_queries, scenes
Each scenes item: narration, visual_query, purpose, visual_mode, source_url, on_screen_text
"""
        else:
            return f"""You are the senior writer and video director for GTA6Hub, a premium GTA 6 YouTube channel.
Create a HIGH-QUALITY 8-12 minute GTA 6 guide video about: {research.topic}

Research evidence:
{source_text}

MANDATORY GAMING LONG-FORM FORMAT:
- Total spoken words: 1,200-1,550 words (8-10 minutes at gaming commentary pace)
- Scenes: exactly 30-36 fast-cut scene beats
- Narration per scene: 35-50 words (2-3 punchy sentences of real gaming commentary)
- Structure: EXPLOSIVE HOOK → CONTEXT (brief) → 4-5 MAIN DISCOVERIES/TIPS → 
  GTA5 COMPARISON → COMMUNITY REACTION → HOW TO FIND IT YOURSELF → SUBSCRIBE CTA
- Voice: Energetic gaming documentary narrator — confident, fast, specific, exciting
- NEVER use filler phrases like "as we all know", "it's worth noting", "interestingly enough"
- ALWAYS use gaming vocabulary: "Rockstar", "sandbox", "open world", "NPC AI", "RAGE engine",
  "Easter egg", "speedrun", "exploit", "glitch", "easter egg hunters"

VISUAL DIRECTION (critical for quality):
Every scene must use visual_mode="stock" and a GTA-aesthetic visual_query:
- Urban night scenes: "miami neon city night aerial drone 4k"
- Action scenes: "luxury sports car chase highway night speed"
- Florida locations: "florida beach aerial turquoise water palm trees"
- Vice City vibe: "neon signs retro palm trees night miami beach"
- Character scenes: "confident woman city street night neon lights"
- Exploration: "swamp everglades alligator aerial nature florida"
- Cars/speed: "supercar highway speed blur cinematic night"
- Water/ocean: "speedboat miami ocean sunset fast"
- City overview: "downtown miami skyscrapers golden hour aerial"

PACKAGING — optimized for discovery and CTR:
- title: 55-70 chars. Format: "GTA 6 [Topic]: [Shocking Claim] [Reaction]"
  Examples: "GTA 6 Leonida Map: 10 Secrets Rockstar Doesn't Want You to Find"
  or "GTA 6 Jason & Lucia: The Dark Story Nobody Explained (Full Breakdown)"
- description: 150-200 words. Hook sentence first. #GTA6 #GrandTheftAutoVI tags at end.
- thumbnail_text: 3 ALL-CAPS words (e.g. "10 HIDDEN SECRETS" or "NOBODY KNOWS THIS")
- thumbnail_brief: Dramatic GTA 6 scene — split image of Jason/Lucia vs Vice City skyline, 
  neon colors, bold yellow/white text overlay

Return JSON only with these exact keys:
angle, content_mode, hook, script, title, description, tags, thumbnail_brief, thumbnail_text, visual_queries, scenes
Each scenes item: narration, visual_query, purpose, visual_mode, source_url, on_screen_text
"""

    def _improve_plan(self, research: ResearchPack, video_format: str, draft: dict) -> dict | None:
        source_text = research.research_notes[:14000]
        draft_json = json.dumps(draft, ensure_ascii=False)

        if video_format == "short":
            format_rules = "Keep 115-145 total spoken words, 10-12 scene beats, every narration 10-15 words."
            quality_check = """- Weak, slow, or generic hook (must PUNCH in the first 5 words)
- Any scene narration over 15 words (keep it short and fast)
- Generic visual queries like "person talking" or "city footage" (must be GTA-aesthetic specific)
- Weak title (must include "GTA 6" and be viral-formatted)
- Thumbnail text that's boring (must be ALL CAPS and provocative)
- Missing #GTA6 hashtags in description"""
        else:
            format_rules = "Keep 1,200-1,550 total spoken words, 30-36 scenes, 35-50 words per narration."
            quality_check = """- Slow opening — must explode with the most shocking GTA 6 fact immediately
- Generic visual queries — every query must evoke GTA 6 / Vice City aesthetic
- Academic language — rewrite as energetic gaming commentary
- Narrations that are under 35 words (expand with specific GTA 6 details)
- Missing GTA5 comparison section
- Boring title — must be viral gaming format"""

        return_prompt = f"""You are the executive editor for GTA6Hub, the #1 GTA 6 YouTube channel.
Rewrite this draft to be the BEST GTA 6 video on the internet.

Topic: {research.topic}
Research evidence:
{source_text}

Draft JSON:
{draft_json}

FIX EVERY ONE OF THESE PROBLEMS:
{quality_check}

REQUIRED STANDARD:
{format_rules}
- Every visual_query must be: cinematic B-roll of Vice City/Miami/Florida/action scenes
  (NOT abstract, NOT "split screen", NOT "graphic", NOT "animation")
- Narration must sound like a real GTA gaming YouTuber — fast, specific, exciting
- Title must include "GTA 6" and use a proven viral gaming format
- Description must have #GTA6 #GrandTheftAutoVI #GTA6Secrets in the hashtag section

Return the complete corrected JSON only, same keys: 
angle, content_mode, hook, script, title, description, tags, thumbnail_brief, thumbnail_text, 
visual_queries, scenes (each with: narration, visual_query, purpose, visual_mode, source_url, on_screen_text)
"""
        try:
            return self._generate_json(return_prompt)
        except Exception:
            return draft

