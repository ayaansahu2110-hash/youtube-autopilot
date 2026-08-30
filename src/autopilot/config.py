from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    autopilot_env: str = "development"
    channel_profile: Literal["bytevexa", "curioaxiom"] = "bytevexa"
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
    youtube_category_id: str = "28"
    youtube_made_for_kids: bool = False

    # Gemini is the preferred no-cost scripting provider. OpenAI remains an optional fallback.
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
        """Give CurioAxiom isolated defaults even when only its profile is selected."""
        if self.channel_profile != "curioaxiom":
            return
        if self.channel_display_name == "ByteVexa":
            self.channel_display_name = "CurioAxiom"
        if self.artifacts_dir == Path("artifacts"):
            self.artifacts_dir = Path("artifacts/curioaxiom")
        if self.state_file == Path("state/history.json"):
            self.state_file = Path("state/curioaxiom/history.json")
        if self.learning_file == Path("state/learning.json"):
            self.learning_file = Path("state/curioaxiom/learning.json")
        if self.youtube_token_file == Path("secrets/youtube_token.json"):
            self.youtube_token_file = Path("secrets/youtube_token_curioaxiom.json")
        if self.channel_niche == "AI tools, technology and useful websites":
            self.channel_niche = (
                "verified cinematic facts across science, history, geography, mathematics, "
                "engineering, space, Formula 1 and automobiles"
            )
        if self.topic_queries == "AI tools,artificial intelligence,technology,useful websites,productivity apps":
            self.topic_queries = (
                "counterintuitive science,history discovery,geography mystery,mathematics paradox,"
                "space science,engineering explained,Formula 1 engineering,automotive engineering"
            )
        if self.max_visual_clips_short == 10:
            self.max_visual_clips_short = 24
        if self.min_visual_clips_short == 5:
            self.min_visual_clips_short = 20
        if self.visual_clip_seconds == 2.8:
            self.visual_clip_seconds = 2.0
        if self.shorts_per_day == 2:
            self.shorts_per_day = 3

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
