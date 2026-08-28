from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    autopilot_env: str = "development"
    artifacts_dir: Path = Path("artifacts")
    state_file: Path = Path("state/history.json")

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
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"

    pexels_api_key: str | None = None
    max_visual_clips_short: int = 6
    max_visual_clips_long: int = 16
    visual_clip_seconds: float = 5.0

    edge_tts_voice: str = "en-US-GuyNeural"
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"

    youtube_client_secrets_file: Path = Path("secrets/client_secret.json")
    youtube_token_file: Path = Path("secrets/youtube_token.json")

    schedule_timezone: str = "Asia/Kolkata"
    schedule_hour: int = 18
    schedule_minute: int = 0
    longform_enabled: bool = True
    longform_days: str = "mon,wed,fri"
    analytics_lookback_days: int = 28

    @property
    def topic_query_list(self) -> list[str]:
        return [item.strip() for item in self.topic_queries.split(",") if item.strip()]

    @property
    def discovery_region_list(self) -> list[str]:
        return [item.strip().upper() for item in self.discovery_regions.split(",") if item.strip()]

    @property
    def longform_day_set(self) -> set[str]:
        return {item.strip().lower()[:3] for item in self.longform_days.split(",") if item.strip()}

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
