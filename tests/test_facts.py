from pathlib import Path
from autopilot.config import Settings
from autopilot.cli import _settings_for_format
from autopilot.facts import (
    CurioAxiomEditorialSystem,
    FactCategoryRouter,
    FactScriptPlanner,
    FactVerifier,
    verified_curio_seed,
)
from autopilot.models import ResearchPack, ResearchSource, SceneBeat, TopicCandidate, VideoPlan
from autopilot.models import VisualAsset
from autopilot.render import FFmpegRenderer
from autopilot.pipeline import AutopilotPipeline
from autopilot.youtube import YouTubeUploader


def test_curioaxiom_defaults_are_isolated() -> None:
    settings = Settings(channel_profile="curioaxiom")
    assert settings.state_file == Path("state/curioaxiom/history.json")
    assert settings.learning_file == Path("state/curioaxiom/learning.json")
    assert settings.youtube_token_file == Path("secrets/youtube_token_curioaxiom.json")
    assert settings.max_visual_clips_short == 24
    assert settings.min_visual_clips_short == 20
    assert settings.visual_clip_seconds == 2.0
    assert settings.shorts_per_day == 2


def test_curioaxiom_public_short_setting_does_not_publish_long_form() -> None:
    settings = Settings(channel_profile="curioaxiom", shorts_public=True)
    short = _settings_for_format(settings, "short")
    long_form = _settings_for_format(settings, "long")
    assert short.upload_privacy_status == "public"
    assert short.allow_public_uploads is True
    assert long_form.upload_privacy_status == "private"
    assert long_form.allow_public_uploads is False


def test_youtube_duration_parser_supports_short_and_long_videos() -> None:
    assert YouTubeUploader._duration_seconds("PT59S") == 59
    assert YouTubeUploader._duration_seconds("PT1M1S") == 61
    assert YouTubeUploader._duration_seconds("PT1H2M3S") == 3723
    assert YouTubeUploader._duration_seconds("not-a-duration") == 0


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


def test_verified_curio_seed_is_authoritative_and_never_reuses_an_excluded_topic() -> None:
    first = verified_curio_seed()
    assert first is not None
    candidate, research = first
    verified = FactVerifier().verify(research)
    assert candidate.title == "Why Astronauts Float in Orbit"
    assert verified.confidence_score >= 65
    next_seed = verified_curio_seed(excluded_topics=[candidate.title])
    assert next_seed is not None
    assert next_seed[0].title != candidate.title
    semantic_next_seed = verified_curio_seed(excluded_topics=["The Physics of Falling Forever"])
    assert semantic_next_seed is not None
    assert semantic_next_seed[0].title != candidate.title


def test_verified_curio_reserve_continues_after_original_topics_are_used() -> None:
    seeded = verified_curio_seed(
        excluded_topics=[
            "Why Astronauts Float in Orbit",
            "Why Ocean Water Is Salty",
            "Why Heat Shields Burn on Purpose",
        ]
    )
    assert seeded is not None
    candidate, research = seeded
    assert candidate.title == "Why the Sky Is Blue but Sunsets Are Red"
    assert len(research.sources) == 2
    assert FactVerifier().verify(research).confidence_score >= 65


def test_curated_fact_category_survives_editorial_enrichment() -> None:
    seeded = verified_curio_seed(
        excluded_topics=[
            "Why Astronauts Float in Orbit",
            "Why Ocean Water Is Salty",
            "Why Heat Shields Burn on Purpose",
        ]
    )
    assert seeded is not None
    candidate, research = seeded
    enriched = CurioAxiomEditorialSystem().enrich(candidate, research)
    assert enriched.category == "science"
    assert FactVerifier().verify(enriched).confidence_score >= 65


def test_fact_editing_splits_long_visual_holds() -> None:
    asset = VisualAsset(local_path=Path("proof.jpg"), asset_kind="image", scene_index=0)
    timeline = FFmpegRenderer._rapid_timeline([(asset, 7.2)], max_seconds=2.65)
    assert len(timeline) == 3
    assert all(seconds <= 2.65 for _, seconds in timeline)
    assert abs(sum(seconds for _, seconds in timeline) - 7.2) < 0.001


def test_short_voice_normalization_only_allows_mild_speedup(tmp_path, monkeypatch) -> None:
    renderer = FFmpegRenderer()
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"original")
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"normalized")

    monkeypatch.setattr("autopilot.render.subprocess.run", fake_run)
    monkeypatch.setattr(renderer, "probe_duration", lambda path: 64.9)

    assert renderer.normalize_short_voice_duration(audio, 71.5) == 64.9
    assert any("atempo=1.100000" in part for part in calls[0])
    assert audio.read_bytes() == b"normalized"

    calls.clear()
    assert renderer.normalize_short_voice_duration(audio, 80.0) == 80.0
    assert calls == []


def test_fact_prompt_requires_zero_mismatch_storyboards() -> None:
    planner = FactScriptPlanner(Settings(channel_profile="curioaxiom"))
    prompt = planner._draft_prompt(
        ResearchPack(topic="Why oceans have trenches", category="geography"),
        "short",
    )
    assert "ZERO-MISMATCH STORYBOARD" in prompt
    assert "exact_visual_subject" in prompt
    assert "camera_and_lighting" in prompt
    assert "generator_prompt" in prompt
    assert "shot_type_camera_movement" in prompt
    assert "sfx_audio_cue" in prompt
    assert "direct_paste_script" in prompt
    assert "batch_prompts" in prompt
    assert "ZERO-REPETITION" in prompt
    assert "exactly 3" in prompt


def test_f1_brake_manual_topic_has_verified_source_seed(tmp_path: Path) -> None:
    pipeline = AutopilotPipeline(Settings(channel_profile="curioaxiom", artifacts_dir=tmp_path))
    pipeline.researcher.research = lambda candidate: ResearchPack(topic=candidate.title)
    candidate, _ = pipeline._candidate_with_research("Why Formula 1 brakes glow red")
    assert any("fia.com/regulations/formula-1" in url for url in candidate.source_urls)
    assert sum("brembo.com" in url for url in candidate.source_urls) == 2
    assert sum("formula1.com" in url for url in candidate.source_urls) == 2


def test_airplane_window_topic_has_faa_source_seed(tmp_path: Path) -> None:
    pipeline = AutopilotPipeline(Settings(channel_profile="curioaxiom", artifacts_dir=tmp_path))
    pipeline.researcher.research = lambda candidate: ResearchPack(topic=candidate.title)
    candidate, _ = pipeline._candidate_with_research("Why airplane windows are round")
    assert sum("faa.gov" in url for url in candidate.source_urls) == 3


def test_airplane_window_research_keeps_two_official_domains(tmp_path: Path) -> None:
    pipeline = AutopilotPipeline(Settings(channel_profile="curioaxiom", artifacts_dir=tmp_path))
    pipeline.researcher.research = lambda candidate: ResearchPack(topic=candidate.title)
    _, research = pipeline._candidate_with_research("Why airplane windows are round")
    domains = {source.url.split("/", 3)[2] for source in research.sources}
    assert {"www.faa.gov", "ntrs.nasa.gov"} <= domains
    assert "high stress concentrations" in research.research_notes


def test_fact_planner_rebuilds_visual_contract_after_scene_splitting() -> None:
    planner = FactScriptPlanner(Settings(channel_profile="curioaxiom"))
    base = VideoPlan(
        topic="Airplane windows",
        angle="engineering",
        format="short",
        hook="Why round?",
        script="",
        title="Why Airplane Windows Are Round",
        description="Test",
        thumbnail_brief="Window against sky",
        scenes=[
            SceneBeat(
                narration=("Cabin pressure pushes outward on the fuselage during every flight "
                           "and sharp window corners concentrate that repeated structural load"),
                visual_query="aircraft window fuselage pressure test",
                exact_visual_subject="aircraft window in a pressurized fuselage",
            )
            for _ in range(6)
        ],
    )
    planner._generate_json = lambda prompt: base.model_dump()
    plan = planner.create_plan(ResearchPack(topic="Airplane windows"), "short")
    assert len(plan.scenes) >= 20
    assert len({scene.shot_type_camera_movement for scene in plan.scenes}) == len(plan.scenes)
    assert len(plan.batch_prompts) == len(plan.scenes)
    assert all(prompt.endswith("--ar 9:16") for prompt in plan.batch_prompts)


def test_scheduled_fact_selection_skips_weakly_sourced_headline(tmp_path: Path) -> None:
    pipeline = AutopilotPipeline(Settings(channel_profile="curioaxiom", artifacts_dir=tmp_path))
    weak = TopicCandidate(title="Why an inventor hid his identity", score=90, reason="viral")
    strong = TopicCandidate(title="Why NASA heat shields char", score=70, reason="verified")
    pipeline.discovery.discover = lambda: [weak, strong]
    pipeline.planner.choose_topic = lambda candidates: candidates[0]

    def research(candidate: TopicCandidate) -> ResearchPack:
        if candidate.title == weak.title:
            return ResearchPack(
                topic=candidate.title,
                sources=[ResearchSource(title="Blog", url="https://example.com/a", snippet="x" * 400)],
            )
        return ResearchPack(
            topic=candidate.title,
            sources=[
                ResearchSource(title="NASA", url="https://www.nasa.gov/a", snippet="x" * 400),
                ResearchSource(title="ESA", url="https://www.esa.int/b", snippet="y" * 400),
            ],
        )

    pipeline.researcher.research = research
    candidate, _ = pipeline._candidate_with_research(None)
    assert candidate.title == strong.title


def test_fact_short_duration_guard_preserves_all_scenes() -> None:
    scenes = [
        SceneBeat(narration="one two three four five six seven eight nine ten", visual_query=f"shot {i}")
        for i in range(22)
    ]
    plan = VideoPlan(
        topic="Mars",
        angle="science",
        format="short",
        hook="Mars moved.",
        script=" ".join(scene.narration for scene in scenes),
        title="What InSight Heard Inside Mars",
        description="Test",
        thumbnail_brief="Mars cutaway",
        scenes=scenes,
    )
    planner = FactScriptPlanner(Settings(channel_profile="curioaxiom"))
    planner._generate_json = lambda prompt: {"narrations": ["The instrument measured a seismic wave."] * 22}
    planner._fit_short_narration(plan, target_words=145)
    assert all(scene.narration == "The instrument measured a seismic wave." for scene in plan.scenes)
    assert len(plan.script.split()) <= 165
    assert len(plan.scenes) == 22
    assert all(len(scene.narration.split()) >= 3 for scene in plan.scenes)


def test_fact_short_rewrite_failure_preserves_original_for_quality_gate() -> None:
    scenes = [
        SceneBeat(narration="one two three four five six seven eight", visual_query=f"literal shot {i}")
        for i in range(22)
    ]
    plan = VideoPlan(
        topic="Ocean salt",
        angle="science",
        format="short",
        hook="Why salty?",
        script=" ".join(scene.narration for scene in scenes),
        title="Why Is The Ocean Salty?",
        description="Test",
        thumbnail_brief="Ocean cross-section",
        scenes=scenes,
    )
    original = [scene.narration for scene in plan.scenes]
    planner = FactScriptPlanner(Settings(channel_profile="curioaxiom"))
    planner._generate_json = lambda prompt: {"narrations": ["too short"]}

    planner._fit_short_narration(plan, target_words=145)

    assert [scene.narration for scene in plan.scenes] == original
    assert plan.script == " ".join(original)


def test_failed_live_research_uses_only_verified_fact_reserve(tmp_path: Path) -> None:
    pipeline = AutopilotPipeline(Settings(channel_profile="curioaxiom", artifacts_dir=tmp_path))
    candidate = TopicCandidate(title="Prompting is Not Programming", score=90, reason="news")
    pipeline.discovery.discover = lambda: [candidate]
    pipeline.planner.choose_topic = lambda candidates: candidate
    pipeline.researcher.research = lambda candidate: ResearchPack(topic=candidate.title)
    fallback_candidate, fallback_research = pipeline._candidate_with_research(None)
    assert fallback_candidate.title != candidate.title
    verified = FactVerifier().verify(fallback_research)
    assert verified.confidence_score >= 65
    assert len(fallback_research.sources) >= pipeline.settings.min_research_sources


def test_facts_fallback_uses_cached_official_feed(tmp_path: Path) -> None:
    pipeline = AutopilotPipeline(Settings(channel_profile="curioaxiom", artifacts_dir=tmp_path))
    calls = []
    def feed(url):
        calls.append(url)
        return [{"title": "NASA science"}]
    pipeline.discovery._rss_search = feed
    assert pipeline.discovery._hacker_news("space") == [{"title": "NASA science"}]
    pipeline.discovery._hacker_news("engineering")
    assert calls == ["https://www.nasa.gov/feed/"]
