from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


ChannelProfileType = Literal[
    "bytevexa",
    "curioaxiom",
    "wondertales",
    "mokshavani",
    "apexstoic",
    "chronosenigma",
    "empirepulse",
]

CHANNEL_PROFILES: list[str] = [
    "bytevexa",
    "curioaxiom",
    "wondertales",
    "mokshavani",
    "apexstoic",
    "chronosenigma",
    "empirepulse",
]

PROFILE_CONFIGS: dict[str, dict] = {
    "bytevexa": {
        "display_name": "ByteVexa",
        "niche": "AI tools, technology and useful websites",
        "topic_queries": "AI tools,artificial intelligence,technology,useful websites,productivity apps",
        "voice": "en-US-AndrewNeural",
        "rate": "+2%",
        "pitch": "-2Hz",
        "category_id": "28",
        "made_for_kids": False,
        "token_file": "secrets/youtube_token.json",
        "max_clips_short": 10,
        "min_clips_short": 5,
        "clip_seconds": 2.8,
        "shorts_per_day": 2,
    },
    "curioaxiom": {
        "display_name": "CurioAxiom",
        "niche": "verified cinematic facts across science, history, geography, mathematics, engineering, space, Formula 1 and automobiles",
        "topic_queries": "counterintuitive science,history discovery,geography mystery,mathematics paradox,space science,engineering explained,Formula 1 engineering,automotive engineering",
        "voice": "en-US-AndrewNeural",
        "rate": "+2%",
        "pitch": "-2Hz",
        "category_id": "28",
        "made_for_kids": False,
        "token_file": "secrets/youtube_token_curioaxiom.json",
        "max_clips_short": 24,
        "min_clips_short": 20,
        "clip_seconds": 2.0,
        "shorts_per_day": 2,
    },
    "wondertales": {
        "display_name": "WonderTales Kids",
        "niche": "animated nursery rhymes, children's poems, bedtime fairy tales and moral animal stories with vibrant cartoon visuals",
        "topic_queries": "kids nursery rhymes,animated bedtime stories,moral animal stories for kids,children's poems,fairytale adventures,preschool learning songs,fun animated kids stories",
        "voice": "en-US-AnaNeural",
        "rate": "-2%",
        "pitch": "+18Hz",
        "category_id": "27",
        "made_for_kids": True,
        "token_file": "secrets/youtube_token_wondertales.json",
        "max_clips_short": 16,
        "min_clips_short": 6,
        "clip_seconds": 2.2,
        "shorts_per_day": 2,
        "min_research_sources": 1,
    },
    "mokshavani": {
        "display_name": "MokshaVani",
        "niche": "sacred Sanskrit mantras, powerful Hindi bhajans, Gayatri Mantra, Mahamrityunjaya, Hanuman Chalisa and Vedic spiritual wisdom with meditative cosmic visuals",
        "topic_queries": "Gayatri mantra with meaning,Mahamrityunjaya mantra chanting,Hanuman Chalisa benefits,Shiv Tandav stotram,Krishna bhajan lyrics and meaning,peaceful morning mantras,vedic meditation wisdom",
        "voice": "hi-IN-MadhurNeural",
        "rate": "+0%",
        "pitch": "-1Hz",
        "category_id": "22",
        "made_for_kids": False,
        "token_file": "secrets/youtube_token_mokshavani.json",
        "max_clips_short": 20,
        "min_clips_short": 6,
        "clip_seconds": 2.5,
        "shorts_per_day": 2,
        "min_research_sources": 1,
    },
    "apexstoic": {
        "display_name": "ApexStoic",
        "niche": "Stoic philosophy, mental toughness, emotional mastery, Marcus Aurelius wisdom, and psychological discipline for high performance",
        "topic_queries": "Marcus Aurelius stoic rules,how to control your emotions,laws of human psychology,ancient stoicism for focus,Seneca wisdom on time,mental toughness rules,the power of moving in silence",
        "voice": "en-US-ChristopherNeural",
        "rate": "-2%",
        "pitch": "-3Hz",
        "category_id": "27",
        "made_for_kids": False,
        "token_file": "secrets/youtube_token_apexstoic.json",
        "max_clips_short": 18,
        "min_clips_short": 6,
        "clip_seconds": 2.2,
        "shorts_per_day": 2,
        "min_research_sources": 1,
    },
    "chronosenigma": {
        "display_name": "ChronosEnigma",
        "niche": "unsolved historical mysteries, lost ancient civilizations, forbidden archaeology, ocean anomalies, and ancient engineering secrets",
        "topic_queries": "Göbekli Tepe ancient mystery,lost city of Atlantis evidence,deep ocean anomalies,unsolved ancient Egyptian engineering secrets,mysterious archaeological discoveries,lost ancient civilizations,strange historical events",
        "voice": "en-US-GuyNeural",
        "rate": "+1%",
        "pitch": "-2Hz",
        "category_id": "28",
        "made_for_kids": False,
        "token_file": "secrets/youtube_token_chronosenigma.json",
        "max_clips_short": 20,
        "min_clips_short": 6,
        "clip_seconds": 2.2,
        "shorts_per_day": 2,
        "min_research_sources": 1,
    },
    "empirepulse": {
        "display_name": "EmpirePulse",
        "niche": "geopolitical docuseries, mega wealth, how small nations become financial superpowers, billionaire family dynasties, and trillion-dollar megaprojects",
        "topic_queries": "how Qatar built infinite wealth,the secret finances of Singapore,the world's oldest billionaire dynasty,trillion-dollar sovereign wealth funds,how Switzerland got so rich,the economics of mega luxury projects,global empire rise and fall",
        "voice": "en-GB-RyanNeural",
        "rate": "+1%",
        "pitch": "-1Hz",
        "category_id": "27",
        "made_for_kids": False,
        "token_file": "secrets/youtube_token_empirepulse.json",
        "max_clips_short": 18,
        "min_clips_short": 6,
        "clip_seconds": 2.4,
        "shorts_per_day": 2,
        "min_research_sources": 1,
    },
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    autopilot_env: str = "development"
    channel_profile: ChannelProfileType = "bytevexa"
    channel_display_name: str = "ByteVexa"
    expected_youtube_channel_id: str | None = None
    artifacts_dir: Path = Path("artifacts")
    state_file: Path = Path("state/history.json")
    learning_file: Path = Path("state/learning.json")

    channel_niche: str = "AI tools, technology and useful websites"
    default_video_format: Literal["short", "long"] = "short"
    topic_queries: str = "AI tools,artificial intelligence,technology,useful websites,productivity apps"
    discovery_regions: str = "US,IN,GB"
    min_research_sources: int = 2

    enable_uploads: bool = False
    upload_privacy_status: Literal["private", "unlisted", "public"] = "private"
    allow_public_uploads: bool = False
    shorts_public: bool = False
    youtube_category_id: str = "28"
    youtube_made_for_kids: bool = False

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"

    pexels_api_key: str | None = None
    max_visual_clips_short: int = 10
    max_visual_clips_long: int = 42
    visual_clip_seconds: float = 2.8
    min_visual_clips_short: int = 5
    min_visual_clips_long: int = 28

    edge_tts_voice: str = "en-US-AndrewNeural"
    edge_tts_rate: str = "+2%"
    edge_tts_pitch: str = "-2Hz"
    edge_tts_volume: str = "+0%"

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"

    youtube_client_secrets_file: Path = Path("secrets/client_secret.json")
    youtube_token_file: Path = Path("secrets/youtube_token.json")

    schedule_timezone: str = "Asia/Kolkata"
    schedule_hour: int = 18
    schedule_minute: int = 0
    shorts_per_day: int = 2
    longform_enabled: bool = True
    longform_every_days: int = 2
    longform_anchor_date: str = "2026-08-29"
    analytics_lookback_days: int = 28

    def model_post_init(self, __context) -> None:
        """Apply isolated defaults for the selected channel profile."""
        profile = self.channel_profile
        cfg = PROFILE_CONFIGS.get(profile)
        if not cfg:
            return

        # Brand display name
        if self.channel_display_name in {"ByteVexa", "CurioAxiom"} or profile != "bytevexa":
            if self.channel_display_name == "ByteVexa" and profile != "bytevexa":
                self.channel_display_name = cfg["display_name"]

        # Storage and credential isolation per channel profile
        if profile != "bytevexa":
            if self.artifacts_dir == Path("artifacts"):
                self.artifacts_dir = Path(f"artifacts/{profile}")
            if self.state_file == Path("state/history.json"):
                self.state_file = Path(f"state/{profile}/history.json")
            if self.learning_file == Path("state/learning.json"):
                self.learning_file = Path(f"state/{profile}/learning.json")
            if self.youtube_token_file == Path("secrets/youtube_token.json"):
                self.youtube_token_file = Path(cfg["token_file"])

        # Niche and query configuration
        if self.channel_niche == "AI tools, technology and useful websites" and profile != "bytevexa":
            self.channel_niche = cfg["niche"]
        if self.topic_queries == "AI tools,artificial intelligence,technology,useful websites,productivity apps" and profile != "bytevexa":
            self.topic_queries = cfg["topic_queries"]

        # Voice persona configuration
        if self.edge_tts_voice == "en-US-AndrewNeural" and profile != "bytevexa":
            self.edge_tts_voice = cfg["voice"]
            self.edge_tts_rate = cfg["rate"]
            self.edge_tts_pitch = cfg["pitch"]

        # Category, COPPA & visual pacing
        if profile != "bytevexa":
            self.youtube_category_id = cfg["category_id"]
            self.youtube_made_for_kids = cfg["made_for_kids"]
            self.max_visual_clips_short = cfg["max_clips_short"]
            self.min_visual_clips_short = cfg["min_clips_short"]
            self.visual_clip_seconds = cfg["clip_seconds"]
            self.shorts_per_day = cfg["shorts_per_day"]
            if "min_research_sources" in cfg:
                self.min_research_sources = cfg["min_research_sources"]

    @property
    def topic_query_list(self) -> list[str]:
        return [item.strip() for item in self.topic_queries.split(",") if item.strip()]

    @property
    def discovery_region_list(self) -> list[str]:
        return [item.strip().upper() for item in self.discovery_regions.split(",") if item.strip()]

    @property
    def llm_configured(self) -> bool:
        return bool(self.gemini_api_key or self.openai_api_key)

    @property
    def llm_provider_name(self) -> str:
        if self.gemini_api_key:
            return "Gemini"
        if self.openai_api_key:
            return "OpenAI"
        return "fallback"

    def ensure_artifacts_dir(self) -> Path:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        return self.artifacts_dir


settings = Settings()
