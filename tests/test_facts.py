from pathlib import Path

from autopilot.config import Settings
from autopilot.facts import FactCategoryRouter, FactVerifier
from autopilot.models import ResearchPack, ResearchSource
from autopilot.models import VisualAsset
from autopilot.render import FFmpegRenderer


def test_curioaxiom_defaults_are_isolated() -> None:
    settings = Settings(channel_profile="curioaxiom")
    assert settings.state_file == Path("state/curioaxiom/history.json")
    assert settings.learning_file == Path("state/curioaxiom/learning.json")
    assert settings.youtube_token_file == Path("secrets/youtube_token_curioaxiom.json")
    assert settings.max_visual_clips_short == 16
    assert settings.min_visual_clips_short == 10
    assert settings.visual_clip_seconds == 2.2


def test_fact_category_router_handles_f1() -> None:
    assert FactCategoryRouter().route("Why Formula 1 brakes glow red") == "f1_automotive"


def test_fact_verifier_rewards_authoritative_diverse_sources() -> None:
    research = ResearchPack(
        topic="Why F1 brakes glow red",
        category="f1_automotive",
        sources=[
            ResearchSource(title="FIA", url="https://fia.com/example", snippet="x" * 400),
            ResearchSource(title="SAE", url="https://sae.org/example", snippet="y" * 400),
        ],
    )
    verified = FactVerifier().verify(research)
    assert verified.confidence_score >= 65
    assert any(note.startswith("2 category-authoritative") for note in verified.verification_notes)


def test_fact_editing_splits_long_visual_holds() -> None:
    asset = VisualAsset(local_path=Path("proof.jpg"), asset_kind="image", scene_index=0)
    timeline = FFmpegRenderer._rapid_timeline([(asset, 7.2)], max_seconds=2.65)
    assert len(timeline) == 3
    assert all(seconds <= 2.65 for _, seconds in timeline)
    assert abs(sum(seconds for _, seconds in timeline) - 7.2) < 0.001
