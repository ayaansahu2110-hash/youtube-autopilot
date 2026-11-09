from autopilot.config import Settings
from autopilot.models import ResearchPack
from autopilot.providers.llm import ScriptPlanner


def _draft(count: int) -> dict:
    return {
        "angle": "A verified result",
        "hook": "Here is what happened.",
        "script": "",
        "title": "A technology result",
        "description": "An evidence-based explainer.",
        "tags": ["technology"],
        "thumbnail_brief": "One clear result",
        "thumbnail_text": "THE RESULT",
        "visual_queries": [],
        "scenes": [
            {
                "narration": f"Evidence beat number {index} explains a distinct step.",
                "visual_query": f"Evidence step {index}",
                "purpose": "evidence",
                "visual_mode": "motion",
                "source_url": "",
                "on_screen_text": f"STEP {index}",
            }
            for index in range(count)
        ],
    }


def test_short_planner_repairs_collapsed_visual_story(monkeypatch) -> None:
    planner = ScriptPlanner(Settings(gemini_api_key="test"))
    draft = _draft(5)
    repaired = _draft(9)
    prompts = []

    def generate(prompt: str) -> dict:
        prompts.append(prompt)
        return draft if len(prompts) == 1 else repaired

    monkeypatch.setattr(planner, "_generate_json", generate)
    monkeypatch.setattr(planner, "_improve_plan", lambda research, fmt, data: data)
    plan = planner.create_plan(ResearchPack(topic="Verified technology result"), "short")

    assert len(plan.scenes) == 9
    assert "distinct visual subject/action" in prompts[1]
