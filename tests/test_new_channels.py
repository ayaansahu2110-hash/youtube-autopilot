from pathlib import Path

from autopilot.config import CHANNEL_PROFILES, PROFILE_CONFIGS, Settings
from autopilot.editorial import (
    ApexStoicEditorialSystem,
    ByteVexaEditorialSystem,
    ChronosEnigmaEditorialSystem,
    EmpirePulseEditorialSystem,
    MokshaVaniEditorialSystem,
    WonderTalesEditorialSystem,
    editorial_system_for,
)
from autopilot.discovery import TopicDiscovery
from autopilot.facts import CurioAxiomEditorialSystem
from autopilot.models import SceneBeat
from autopilot.providers.hybrid_visuals import HybridVisualDirector
from autopilot.providers.visuals import PexelsVideoProvider
from autopilot.state import StateStore


def test_all_seven_channels_defined() -> None:
    expected = [
        "bytevexa",
        "curioaxiom",
        "wondertales",
        "mokshavani",
        "apexstoic",
        "chronosenigma",
        "empirepulse",
    ]
    assert CHANNEL_PROFILES == expected
    for profile in expected:
        assert profile in PROFILE_CONFIGS
        cfg = PROFILE_CONFIGS[profile]
        assert "display_name" in cfg
        assert "niche" in cfg
        assert "voice" in cfg
        assert "token_file" in cfg


def test_profile_isolation_and_settings() -> None:
    # WonderTales
    wt = Settings(channel_profile="wondertales")
    assert wt.channel_display_name == "WonderTales Kids"
    assert wt.youtube_made_for_kids is True
    assert wt.youtube_category_id == "27"
    assert wt.edge_tts_voice == "en-US-AnaNeural"
    assert wt.youtube_token_file == Path("secrets/youtube_token_wondertales.json")
    assert wt.artifacts_dir == Path("artifacts/wondertales")
    assert wt.state_file == Path("state/wondertales/history.json")

    # MokshaVani
    mv = Settings(channel_profile="mokshavani")
    assert mv.channel_display_name == "MokshaVani"
    assert mv.youtube_made_for_kids is False
    assert mv.youtube_category_id == "22"
    assert mv.edge_tts_voice == "hi-IN-MadhurNeural"
    assert mv.youtube_token_file == Path("secrets/youtube_token_mokshavani.json")
    assert mv.artifacts_dir == Path("artifacts/mokshavani")

    # ApexStoic
    stoic = Settings(channel_profile="apexstoic")
    assert stoic.channel_display_name == "ApexStoic"
    assert stoic.edge_tts_voice == "en-US-ChristopherNeural"
    assert stoic.youtube_token_file == Path("secrets/youtube_token_apexstoic.json")

    # ChronosEnigma
    ce = Settings(channel_profile="chronosenigma")
    assert ce.channel_display_name == "ChronosEnigma"
    assert ce.edge_tts_voice == "en-US-GuyNeural"
    assert ce.youtube_category_id == "28"

    # EmpirePulse
    ep = Settings(channel_profile="empirepulse")
    assert ep.channel_display_name == "EmpirePulse"
    assert ep.edge_tts_voice == "en-GB-RyanNeural"
    assert ep.youtube_token_file == Path("secrets/youtube_token_empirepulse.json")


def test_editorial_systems_factory() -> None:
    assert isinstance(editorial_system_for("bytevexa"), ByteVexaEditorialSystem)
    assert isinstance(editorial_system_for("curioaxiom"), CurioAxiomEditorialSystem)
    assert isinstance(editorial_system_for("wondertales"), WonderTalesEditorialSystem)
    assert isinstance(editorial_system_for("mokshavani"), MokshaVaniEditorialSystem)
    assert isinstance(editorial_system_for("apexstoic"), ApexStoicEditorialSystem)
    assert isinstance(editorial_system_for("chronosenigma"), ChronosEnigmaEditorialSystem)
    assert isinstance(editorial_system_for("empirepulse"), EmpirePulseEditorialSystem)


def test_discovery_for_new_channels(tmp_path: Path) -> None:
    for profile in ["wondertales", "mokshavani", "apexstoic", "chronosenigma", "empirepulse"]:
        s = Settings(channel_profile=profile, state_file=tmp_path / f"{profile}_history.json")
        state = StateStore(s.state_file)
        discovery = TopicDiscovery(s, state)
        candidates = discovery.discover(max_candidates=10)
        assert len(candidates) > 0, f"Discovery returned no candidates for {profile}"
        assert all(isinstance(c.title, str) and len(c.title) > 5 for c in candidates)


def test_hybrid_visual_queries_include_niche_fallbacks() -> None:
    pexels = PexelsVideoProvider(None)
    director_mv = HybridVisualDirector(pexels, channel_profile="mokshavani")
    scene = SceneBeat(narration="Chanting the sacred Gayatri mantra brings immense inner peace.", visual_query="cinematic 4k shot of sacred golden light rising over mountains")
    queries_mv = director_mv._stock_queries(scene)
    assert any("diya" in q or "temple" in q or "sunrise" in q for q in queries_mv)

    director_stoic = HybridVisualDirector(pexels, channel_profile="apexstoic")
    scene_stoic = SceneBeat(narration="Marcus Aurelius never cared about the opinions of others.", visual_query="statue of the roman emperor standing tall in the rain")
    queries_stoic = director_stoic._stock_queries(scene_stoic)
    assert any("statue" in q or "roman" in q or "rock" in q for q in queries_stoic)

    director_wt = HybridVisualDirector(pexels, channel_profile="wondertales")
    scene_wt = SceneBeat(narration="The little bunny hopped happily across the green meadow.", visual_query="animated cartoon style little cute bunny hopping")
    queries_wt = director_wt._stock_queries(scene_wt)
    assert any("rabbit" in q or "bunny" in q or "forest" in q for q in queries_wt)

