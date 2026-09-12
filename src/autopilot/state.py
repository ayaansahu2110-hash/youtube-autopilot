import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from autopilot.models import PipelineRun


STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with", "is", "are",
    "this", "that", "you", "your", "how", "why", "what", "new", "best", "top", "ai",
}


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"videos": [], "topics": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"videos": [], "topics": []}
        data.setdefault("videos", [])
        data.setdefault("topics", [])
        return data

    def load(self) -> dict[str, Any]:
        return self.data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def recent_topics(self, limit: int = 60) -> list[str]:
        return [str(item.get("topic", "")) for item in self.data["topics"][-limit:] if item.get("topic")]

    def sync_recent_uploads(self, uploads: list[dict[str, str]]) -> None:
        """Seed topic memory from actual YouTube uploads, across Shorts and long-form."""
        if not uploads:
            return
        known_video_ids = {str(item.get("video_id")) for item in self.data["videos"] if item.get("video_id")}
        known_titles = {str(item.get("title", "")).strip().lower() for item in self.data["topics"] if item.get("title")}
        now = datetime.now(timezone.utc).isoformat()
        for upload in reversed(uploads):
            video_id = str(upload.get("video_id") or "")
            title = str(upload.get("title") or "").strip()
            video_format = str(upload.get("format") or "unknown")
            if not video_id or not title:
                continue
            if title.lower() not in known_titles:
                self.data["topics"].append(
                    {
                        "topic": title,
                        "title": title,
                        "format": video_format,
                        "created_at": upload.get("published_at") or now,
                        "source": "youtube_sync",
                    }
                )
                known_titles.add(title.lower())
            if video_id not in known_video_ids:
                self.data["videos"].append(
                    {
                        "video_id": video_id,
                        "topic": title,
                        "title": title,
                        "format": video_format,
                        "script_preview": "",
                        "created_at": upload.get("published_at") or now,
                        "analytics": {},
                        "source": "youtube_sync",
                    }
                )
                known_video_ids.add(video_id)
            elif video_format != "unknown":
                for item in self.data["videos"]:
                    if item.get("video_id") == video_id and item.get("format") == "unknown":
                        item["format"] = video_format
                for item in self.data["topics"]:
                    if item.get("title", "").strip().lower() == title.lower() and item.get("format") == "unknown":
                        item["format"] = video_format
        self.data["topics"] = self.data["topics"][-300:]
        self.data["videos"] = self.data["videos"][-300:]
        self.save()

    def record_run(self, run: PipelineRun) -> None:
        created = datetime.now(timezone.utc).isoformat()
        self.data["topics"].append(
            {"topic": run.plan.topic, "title": run.plan.title, "format": run.plan.format, "created_at": created}
        )
        if run.youtube_video_id:
            self.data["videos"].append(
                {
                    "video_id": run.youtube_video_id,
                    "topic": run.plan.topic,
                    "title": run.plan.title,
                    "format": run.plan.format,
                    "script_preview": run.plan.script[:600],
                    "created_at": created,
                    "analytics": {},
                }
            )
        self.data["topics"] = self.data["topics"][-300:]
        self.data["videos"] = self.data["videos"][-300:]
        self.save()

    def video_ids(self, limit: int = 100) -> list[str]:
        return [str(item["video_id"]) for item in self.data["videos"][-limit:] if item.get("video_id")]

    def upload_count_on_date(
        self,
        target_date: date,
        *,
        timezone_name: str,
        video_format: str,
    ) -> int:
        """Count completed uploads on a channel-local date, including synced videos."""
        count = 0
        local_zone = ZoneInfo(timezone_name)
        for item in self.data["videos"]:
            if item.get("format") != video_format or not item.get("video_id"):
                continue
            created_at = str(item.get("created_at") or "").strip()
            if not created_at:
                continue
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created.astimezone(local_zone).date() == target_date:
                count += 1
        return count

    def update_analytics(self, video_id: str, metrics: dict[str, float]) -> None:
        for item in self.data["videos"]:
            if item.get("video_id") == video_id:
                item["analytics"] = metrics
                item["analytics_updated_at"] = datetime.now(timezone.utc).isoformat()
                break
        self.save()

    def performance_terms(self, limit: int = 12) -> list[str]:
        counter: Counter[str] = Counter()
        for item in self.data["videos"]:
            views = float(item.get("analytics", {}).get("views", 0) or 0)
            if views <= 0:
                continue
            words = re.findall(r"[a-z0-9]+", str(item.get("title", "")).lower())
            for word in words:
                if len(word) >= 3 and word not in STOPWORDS:
                    counter[word] += max(1, int(views))
        return [word for word, _ in counter.most_common(limit)]

    def top_performers(self, limit: int = 5) -> list[dict[str, Any]]:
        """Return meaningful channel baselines, weighted for retention and engagement.

        A few raw views alone are a weak signal, especially for a new channel. This
        deliberately prefers videos that also keep viewers watching and earn real
        engagement, so future plans learn patterns rather than chase clickbait.
        """
        scored: list[tuple[float, dict[str, Any]]] = []
        for video in self.data["videos"]:
            metrics = video.get("analytics") or {}
            views = float(metrics.get("views", 0) or 0)
            retention = float(metrics.get("averageViewPercentage", 0) or 0)
            likes = float(metrics.get("likes", 0) or 0)
            comments = float(metrics.get("comments", 0) or 0)
            shares = float(metrics.get("shares", 0) or 0)
            if views <= 0:
                continue
            engagement_per_100_views = 100 * (likes + comments + shares) / max(views, 1)
            score = views * (1 + retention / 100) * (1 + engagement_per_100_views / 100)
            scored.append((score, video))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [video for _, video in scored[:limit]]
