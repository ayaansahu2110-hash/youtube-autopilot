from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class TopicCandidate(BaseModel):
    title: str
    angle: str
    score: float = Field(ge=0, le=100)
    reason: str


class VideoPlan(BaseModel):
    topic: str
    angle: str
    format: Literal["short", "long"]
    hook: str
    script: str
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    thumbnail_brief: str


class PipelineRun(BaseModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["planned", "rendered", "uploaded", "failed"] = "planned"
    plan: VideoPlan
    video_path: Path | None = None
    youtube_video_id: str | None = None
    notes: list[str] = Field(default_factory=list)
