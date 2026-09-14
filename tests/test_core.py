import json
from datetime import date
from pathlib import Path

from autopilot.captions import write_srt
from autopilot.cli import _longform_due
from autopilot.config import Settings
from autopilot.learning import learning_context
from autopilot.models import PipelineRun, ResearchPack, ResearchSource, SceneBeat, VideoPlan
from autopilot.providers.hybrid_visuals import HybridVisualDirector
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


def test_bytevexa_rejects_text_heavy_visual_overlays(tmp_path: Path) -> None:
    scenes = [
        SceneBeat(
            narration=f"Concrete visual proof {index}.",
            visual_query=f"specific product result {index}",
            purpose="proof" if index == 0 else "takeaway",
            visual_mode="motion",
            on_screen_text="THIS IS A FULL SENTENCE NOT A VISUAL LABEL",
        )
        for index in range(8)
    ]
    plan = VideoPlan(
        topic="A specific product test",
        angle="Visual proof",
        format="short",
        hook="See the result",
        script=" ".join(scene.narration for scene in scenes),
        title="A Specific Product Test",
        description="A concise, researched test.",
        tags=["AI"],
        thumbnail_brief="One clear result",
        thumbnail_text="REAL RESULT",
        visual_queries=[scene.visual_query for scene in scenes],
        scenes=scenes,
    )
    settings = Settings(state_file=tmp_path / "visual-label-state.json", min_research_sources=1)
    report = QualityGate(settings, StateStore(settings.state_file)).evaluate(
        plan,
        ResearchPack(topic=plan.topic, sources=[ResearchSource(title="Source", url="https://example.com")]),
        strict=False,
    )
    assert any("visual emphasis" in error.lower() for error in report.errors)


def test_bytevexa_visual_label_stays_compact() -> None:
    scene = SceneBeat(
        narration="A long spoken explanation should not become a banner on the visual.",
        visual_query="specific product output",
        on_screen_text="THIS SHOULD BECOME A COMPACT VISUAL EMPHASIS ONLY",
    )
    assert HybridVisualDirector._visual_label(scene) == "THIS SHOULD BECOME A"


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
    assert state.latest_upload_date(
        timezone_name="Asia/Kolkata",
        video_format="long",
    ) == date(2026, 9, 12)


def test_missed_longform_becomes_due_without_bulk_catchup(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "topics": [],
                "videos": [
                    {
                        "video_id": "long-old",
                        "format": "long",
                        "created_at": "2026-09-10T12:00:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        state_file=state_file,
        longform_every_days=2,
        schedule_timezone="Asia/Kolkata",
    )
    state = StateStore(state_file)
    assert _longform_due(settings, state, date(2026, 9, 12)) is True
    assert _longform_due(settings, state, date(2026, 9, 11)) is False


def test_bytevexa_accepts_concrete_flow_output_as_evidence(tmp_path: Path) -> None:
    purposes = ["hook", "flow_input", "flow_action", "flow_output", "limitation", "takeaway"]
    purposes += ["demo"] * 24
    scenes = []
    for index, purpose in enumerate(purposes):
        narration = " ".join(f"specific{index}_{word}" for word in range(40))
        scenes.append(
            SceneBeat(
                narration=narration,
                visual_query=f"specific workflow evidence {index}",
                purpose=purpose,
                visual_mode="motion",
                on_screen_text=f"PROOF {index}",
            )
        )
    plan = VideoPlan(
        topic="A verified browser workflow",
        angle="Proof first",
        format="long",
        hook="See the output",
        script=" ".join(scene.narration for scene in scenes),
        title="A Verified Browser Workflow",
        description="A researched workflow.",
        tags=["AI"],
        thumbnail_brief="One visible output",
        thumbnail_text="REAL OUTPUT",
        visual_queries=[scene.visual_query for scene in scenes],
        scenes=scenes,
    )
    settings = Settings(state_file=tmp_path / "evidence-state.json")
    report = QualityGate(settings, StateStore(settings.state_file)).evaluate(
        plan,
        ResearchPack(topic=plan.topic),
        strict=False,
    )
    assert not any("concrete evidence" in error.lower() for error in report.errors)


def test_learning_baselines_do_not_overfit_tiny_samples(tmp_path: Path) -> None:
    learning_file = tmp_path / "learning.json"
    learning_file.write_text(
        json.dumps(
            {
                "own_analytics": [
                    {
                        "title": "Tiny Looping Sample",
                        "format": "short",
                        "metrics": {
                            "views": 25,
                            "averageViewPercentage": 180,
                            "subscribersGained": 1,
                        },
                    },
                    {
                        "title": "Reliable Retention Baseline",
                        "format": "short",
                        "metrics": {
                            "views": 180,
                            "averageViewPercentage": 80,
                            "subscribersGained": 3,
                        },
                    },
                ],
                "own_comments": [],
            }
        ),
        encoding="utf-8",
    )
    context = learning_context(Settings(learning_file=learning_file))
    assert "Own retention baseline: Reliable Retention Baseline" in context
    assert "Own subscriber-conversion baseline: Reliable Retention Baseline" in context
