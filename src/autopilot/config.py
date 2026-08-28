from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    autopilot_env: str = "development"
    artifacts_dir: Path = Path("artifacts")
    channel_niche: str = "AI tools, technology and useful websites"
    default_video_format: Literal["short", "long"] = "short"

    enable_uploads: bool = False
    upload_privacy_status: Literal["private", "unlisted", "public"] = "private"

    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    edge_tts_voice: str = "en-US-GuyNeural"
    ffmpeg_binary: str = "ffmpeg"

    youtube_client_secrets_file: Path = Path("secrets/client_secret.json")
    youtube_token_file: Path = Path("secrets/youtube_token.json")

    schedule_timezone: str = "Asia/Kolkata"
    schedule_hour: int = 18
    schedule_minute: int = 0

    def ensure_artifacts_dir(self) -> Path:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        return self.artifacts_dir


settings = Settings()
