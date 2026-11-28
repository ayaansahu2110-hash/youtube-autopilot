from pathlib import Path

from PIL import Image

from autopilot.config import Settings
from autopilot.learning import DailyLearningLoop, learning_context
from autopilot.models import SceneBeat
from autopilot.providers.clipflow import ClipflowProvider
from autopilot.providers.gta6hub_planner import GTA6HubScriptPlanner
from autopilot.providers.hybrid_visuals import HybridVisualDirector
from autopilot.providers.llm import ScriptPlanner
from autopilot.providers.visuals import PexelsVideoProvider
from autopilot.render import FFmpegRenderer
from autopilot.state import StateStore
from autopilot.thumbnail import ThumbnailGenerator


def test_competitor_searches_tailored_for_wondertales_and_gta6hub() -> None:
    wt_queries = DailyLearningLoop.PROFILE_COMPETITOR_SEARCHES["wondertales"]
    gta_queries = DailyLearningLoop.PROFILE_COMPETITOR_SEARCHES["gta6hub"]
    assert any("rhyme" in q.lower() or "poem" in q.lower() or "kids" in q.lower() for q in wt_queries)
    assert any("gta 6" in q.lower() for q in gta_queries)


def test_learning_context_includes_niche_guidance_and_tags(tmp_path: Path) -> None:
    for profile, expected_phrase in (
        ("wondertales", "WonderTales Kids"),
        ("gta6hub", "GTA6Hub"),
    ):
        learn_path = tmp_path / f"{profile}_learning.json"
        learn_path.write_text(
            '{"competitors": [{"channel": "TopRef", "subscribers": 100000, "channel_views": 5000000, '
            '"high_performing_recent_videos": [{"views": 250000, "title": "Ref Viral Video", "tags": ["tag1", "tag2"]}]}]}',
            encoding="utf-8",
        )
        s = Settings(channel_profile=profile, learning_file=learn_path)
        ctx = learning_context(s)
        assert expected_phrase in ctx
        assert "Ref Viral Video [tags: tag1, tag2]" in ctx


def test_prompts_forbid_history_in_wondertales_and_include_learning_in_gta6hub(tmp_path: Path) -> None:
    learn_file = tmp_path / "learn.json"
    learn_file.write_text(
        '{"competitors": [{"channel": "TopChan", "subscribers": 50000, "channel_views": 1000000, '
        '"high_performing_recent_videos": [{"views": 99000, "title": "Viral Hook Example", "tags": ["a"]}]}]}',
        encoding="utf-8",
    )
    from autopilot.models import ResearchPack

    wt_settings = Settings(channel_profile="wondertales", learning_file=learn_file)
    wt_prompt = ScriptPlanner(wt_settings)._draft_prompt(
        ResearchPack(topic="Five Little Ducklings", research_notes="Duckling story"), "short"
    )
    assert "STRICTLY FORBIDDEN" in wt_prompt
    assert "Viral Hook Example" in wt_prompt

    gta_settings = Settings(channel_profile="gta6hub", learning_file=learn_file)
    gta_prompt = GTA6HubScriptPlanner(gta_settings)._draft_prompt(
        ResearchPack(topic="GTA 6 Secrets", research_notes="Leonida details"), "short"
    )
    assert "Viral Hook Example" in gta_prompt


def test_gta6_clip_matching_avoids_repeating_clips_in_same_video(tmp_path: Path, monkeypatch) -> None:
    clips_dir = tmp_path / "assets" / "gta6" / "clips"
    clips_dir.mkdir(parents=True)
    for name in (
        "01_lucia_prison_vert.mp4",
        "02_miami_sunset_freeway_vert.mp4",
        "03_speedboat_keys_vert.mp4",
    ):
        (clips_dir / name).write_bytes(b"fake-mp4")

    monkeypatch.chdir(tmp_path)
    director = HybridVisualDirector(PexelsVideoProvider(None), channel_profile="gta6hub")
    scenes = [
        SceneBeat(narration="Sunset over Vice City highway", visual_query="sunset freeway aerial", visual_mode="stock"),
        SceneBeat(narration="Another sunset over the Miami bridge", visual_query="sunset bridge skyline", visual_mode="stock"),
        SceneBeat(narration="Ocean speedboat chase", visual_query="speedboat ocean bay", visual_mode="stock"),
    ]
    used: set[str] = set()
    picked = []
    for idx, sc in enumerate(scenes):
        asset = director._match_gta6_clip(sc, tmp_path / f"out_{idx}.mp4", scene_index=idx, vertical=True, used_clips=used)
        assert asset is not None
        picked.append(asset.local_path.name)
    assert len(used) == 3


def test_clipflow_prompt_style_matches_channel(tmp_path: Path) -> None:
    captured_prompts: list[str] = []

    class FakeClipflow(ClipflowProvider):
        def generate_scene_video(self, prompt: str, out_path: Path, **kwargs):
            captured_prompts.append(prompt)
            out_path.write_bytes(b"video")
            return out_path

    for profile, expected_token in (
        ("wondertales", "Pixar-style cartoon"),
        ("gta6hub", "Vice City neon Miami sunset"),
    ):
        director = HybridVisualDirector(
            PexelsVideoProvider(None),
            channel_profile=profile,
            clipflow=FakeClipflow(enabled=True),
        )
        scene = SceneBeat(narration="Test scene", visual_query="cute bunny jumping", visual_mode="stock")
        director._generate_clipflow_asset(scene, tmp_path / f"{profile}.mp4", scene_index=0, vertical=True)

    assert "Pixar-style cartoon" in captured_prompts[0]
    assert "Vice City neon Miami sunset" in captured_prompts[1]


def test_thumbnails_use_channel_specific_designs(tmp_path: Path) -> None:
    feat = tmp_path / "feature.jpg"
    Image.new("RGB", (640, 360), (40, 120, 200)).save(feat)

    gen = ThumbnailGenerator()
    wt_out = gen.create(
        "HOP BUNNY HOP!",
        tmp_path / "wt.jpg",
        title="Five Little Ducklings",
        brand_name="WonderTales Kids",
        feature_image=feat,
        channel_profile="wondertales",
    )
    gta_out = gen.create(
        "INSANE SECRET",
        tmp_path / "gta.jpg",
        title="GTA 6 Hidden Detail",
        brand_name="GTA6Hub",
        feature_image=feat,
        channel_profile="gta6hub",
    )
    assert wt_out.exists() and wt_out.stat().st_size > 5000
    assert gta_out.exists() and gta_out.stat().st_size > 5000


def test_render_caption_filter_customizes_wondertales_and_gta6hub(tmp_path: Path) -> None:
    srt = tmp_path / "captions.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello!\n", encoding="utf-8")
    r = FFmpegRenderer()
    wt_filt = r._caption_filter(srt, vertical=True, channel_profile="wondertales")
    gta_filt = r._caption_filter(srt, vertical=True, channel_profile="gta6hub")
    assert "&H004CEBFF" in wt_filt
    assert "&H0038EEFF" in gta_filt
