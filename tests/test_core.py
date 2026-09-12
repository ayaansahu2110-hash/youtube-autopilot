import json
from datetime import date
from pathlib import Path

from autopilot.captions import write_srt
from autopilot.config import Settings
from autopilot.models import PipelineRun, ResearchPack, ResearchSource, SceneBeat, VideoPlan
from autopilot.quality import QualityGate
from autopilot.state import StateStore


def _plan(topic: str = "Useful AI tools") -> VideoPlan:
    return VideoPlan(
        topic=topic,
        angle="Practical",
        format="short",
        hook="Try this",
        script=" ".join(["useful"] * 90),
        title="Useful AI tools that save time",
        description="Test description",
        tags=["AI"],
        thumbnail_brief="Simple",
        thumbnail_text="SAVE TIME",
        visual_queries=["person using laptop"],
    )


def test_captions_are_generated(tmp_path: Path) -> None:
    output = write_srt("one two three four five six seven eight", 8.0, tmp_path / "captions.srt", words_per_caption=4)
    text = output.read_text(encoding="utf-8")
    assert "00:00:00,000 -->" in text
    assert "one two three four" in text


def test_quality_rejects_recent_duplicate(tmp_path: Path) -> None:
    settings = Settings(state_file=tmp_path / "state.json", min_research_sources=1)
    state = StateStore(settings.state_file)
    old = _plan("Useful AI tools")
    state.record_run(PipelineRun(run_id="abc", plan=old))
    research = ResearchPack(topic=old.topic, sources=[ResearchSource(title="Source", url="https://example.com")])
    report = QualityGate(settings, state).evaluate(_plan("Useful AI tools"), research, strict=True)
    assert report.passed is False
    assert any("similar" in error.lower() for error in report.errors)


def test_public_upload_requires_explicit_unlock() -> None:
    settings = Settings(upload_privacy_status="public")
    assert settings.allow_public_uploads is False


def test_bytevexa_longform_requires_early_proof(tmp_path: Path) -> None:
    purposes = ["hook", "context", "explanation", "feature"] + ["demo"] * 25 + ["takeaway"]
    scenes = []
    for index, purpose in enumerate(purposes):
        narration = " ".join(f"useful{index}_{word}" for word in range(40))
        scenes.append(
            SceneBeat(
                narration=narration,
                visual_query=f"specific interface workflow {index}",
                purpose=purpose,
                visual_mode="motion",
                on_screen_text=f"STEP {index}",
            )
        )
    plan = VideoPlan(
        topic="A specific AI workflow",
        angle="Practical test",
        format="long",
        hook="See the result first",
        script=" ".join(scene.narration for scene in scenes),
        title="A Specific AI Workflow Tested",
        description="A researched practical test.",
        tags=["AI"],
        thumbnail_brief="One result and one interface",
        thumbnail_text="REAL RESULT",
        visual_queries=[scene.visual_query for scene in scenes],
        scenes=scenes,
    )
    settings = Settings(state_file=tmp_path / "state.json")
    report = QualityGate(settings, StateStore(settings.state_file)).evaluate(
        plan,
        ResearchPack(topic=plan.topic),
        strict=False,
    )
    assert any("first four scenes" in error.lower() for error in report.errors)


def test_upload_count_uses_channel_local_date_and_format(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "topics": [],
                "videos": [
                    {
                        "video_id": "short-a",
                        "format": "short",
                        "created_at": "2026-09-11T20:00:00+00:00",
                    },
                    {
                        "video_id": "long-a",
                        "format": "long",
                        "created_at": "2026-09-12T10:00:00+00:00",
                    },
                    {
                        "video_id": "short-old",
                        "format": "short",
                        "created_at": "2026-09-11T10:00:00+00:00",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    state = StateStore(state_file)
    assert state.upload_count_on_date(
        date(2026, 9, 12),
        timezone_name="Asia/Kolkata",
        video_format="short",
    ) == 1
    assert state.upload_count_on_date(
        date(2026, 9, 12),
        timezone_name="Asia/Kolkata",
        video_format="long",
    ) == 1
