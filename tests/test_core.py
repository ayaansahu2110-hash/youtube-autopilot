from pathlib import Path

from autopilot.captions import write_srt
from autopilot.config import Settings
from autopilot.models import PipelineRun, ResearchPack, ResearchSource, VideoPlan
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
