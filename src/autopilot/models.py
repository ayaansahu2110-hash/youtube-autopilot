from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class ResearchSource(BaseModel):
    title: str
    url: str
    publisher: str | None = None
    published_at: str | None = None
    snippet: str = ""


class TopicCandidate(BaseModel):
    title: str
    angle: str = "Practical, original explainer"
    score: float = Field(ge=0, le=100)
    reason: str
    source_urls: list[str] = Field(default_factory=list)


class ResearchPack(BaseModel):
    topic: str
    sources: list[ResearchSource] = Field(default_factory=list)
    research_notes: str = ""


class VisualAsset(BaseModel):
    local_path: Path
    source_page_url: str | None = None
    creator: str | None = None
    query: str = ""


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
    thumbnail_text: str = ""
    visual_queries: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)


class QualityReport(BaseModel):
    passed: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalyticsSnapshot(BaseModel):
    video_id: str
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: dict[str, float] = Field(default_factory=dict)


class PipelineRun(BaseModel):
    run_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["planned", "rendered", "uploaded", "failed"] = "planned"
    plan: VideoPlan
    research: ResearchPack | None = None
    quality: QualityReport | None = None
    video_path: Path | None = None
    thumbnail_path: Path | None = None
    youtube_video_id: str | None = None
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
