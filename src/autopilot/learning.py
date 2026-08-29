from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from autopilot.analytics import AnalyticsClient
from autopilot.config import Settings
from autopilot.state import StateStore
from autopilot.youtube import YouTubeAuth


class DailyLearningLoop:
    """Collect lightweight public competitor signals + ByteVexa feedback.

    This intentionally studies patterns (topics, packaging, cadence, audience response)
    rather than copying scripts, wording, thumbnails or a creator's identity.
    """

    SEARCHES = (
        "AI tools productivity",
        "best AI tools workflow",
        "AI news tools explained",
    )

    def __init__(self, settings: Settings, state: StateStore):
        self.settings = settings
        self.state = state
        self.auth = YouTubeAuth(settings)

    def refresh(self) -> dict:
        AnalyticsClient(self.settings, self.state).refresh()
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "competitors": [],
            "own_comments": [],
            "own_analytics": self._own_analytics_snapshot(),
        }
        if not self.settings.youtube_token_file.exists():
            return self._write(report)
        try:
            youtube = build("youtube", "v3", credentials=self.auth.credentials(interactive=False))
            report["competitors"] = self._competitor_snapshot(youtube)
            report["own_comments"] = self._own_comments(youtube)
        except (HttpError, RuntimeError, FileNotFoundError):
            pass
        return self._write(report)

    def _competitor_snapshot(self, youtube) -> list[dict]:
        channel_ids: list[str] = []
        for query in self.SEARCHES:
            try:
                data = youtube.search().list(
                    part="snippet", q=query, type="channel", maxResults=5, order="relevance"
                ).execute()
            except HttpError:
                continue
            for item in data.get("items", []):
                cid = item.get("snippet", {}).get("channelId") or item.get("id", {}).get("channelId")
                if cid and cid not in channel_ids:
                    channel_ids.append(cid)

        if not channel_ids:
            return []
        channels = youtube.channels().list(
            part="snippet,statistics,contentDetails", id=",".join(channel_ids[:15]), maxResults=15
        ).execute().get("items", [])

        scored = []
        for channel in channels:
            stats = channel.get("statistics", {})
            subscribers = int(stats.get("subscriberCount") or 0)
            views = int(stats.get("viewCount") or 0)
            videos = int(stats.get("videoCount") or 0)
            scored.append((subscribers, views, videos, channel))
        scored.sort(reverse=True, key=lambda row: (row[0], row[1]))

        output: list[dict] = []
        for subscribers, views, videos, channel in scored[:3]:
            uploads = (
                channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            )
            recent = []
            if uploads:
                try:
                    playlist = youtube.playlistItems().list(
                        part="snippet,contentDetails", playlistId=uploads, maxResults=8
                    ).execute()
                    ids = [
                        item.get("contentDetails", {}).get("videoId")
                        for item in playlist.get("items", [])
                        if item.get("contentDetails", {}).get("videoId")
                    ]
                    if ids:
                        details = youtube.videos().list(
                            part="snippet,statistics,contentDetails", id=",".join(ids)
                        ).execute()
                        for video in details.get("items", []):
                            st = video.get("statistics", {})
                            sn = video.get("snippet", {})
                            recent.append({
                                "title": sn.get("title", ""),
                                "views": int(st.get("viewCount") or 0),
                                "likes": int(st.get("likeCount") or 0),
                                "comments": int(st.get("commentCount") or 0),
                                "published_at": sn.get("publishedAt", ""),
                                "description_excerpt": (sn.get("description") or "")[:350],
                            })
                        recent.sort(key=lambda item: item["views"], reverse=True)
                except HttpError:
                    pass
            output.append({
                "channel": channel.get("snippet", {}).get("title", ""),
                "subscribers": subscribers,
                "channel_views": views,
                "video_count": videos,
                "high_performing_recent_videos": recent[:5],
            })
        return output

    def _own_comments(self, youtube) -> list[dict]:
        comments: list[dict] = []
        for video_id in self.state.video_ids(limit=12):
            try:
                data = youtube.commentThreads().list(
                    part="snippet", videoId=video_id, maxResults=20, order="relevance", textFormat="plainText"
                ).execute()
            except HttpError:
                continue
            for item in data.get("items", []):
                top = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                text = (top.get("textDisplay") or "").strip()
                if text:
                    comments.append({
                        "video_id": video_id,
                        "text": text[:600],
                        "likes": int(top.get("likeCount") or 0),
                    })
        comments.sort(key=lambda item: item["likes"], reverse=True)
        return comments[:40]

    def _own_analytics_snapshot(self) -> list[dict]:
        data = self.state.load()
        runs = data.get("runs", []) if isinstance(data, dict) else []
        rows = []
        for run in runs[-30:]:
            if not isinstance(run, dict):
                continue
            metrics = run.get("analytics") or {}
            if metrics:
                rows.append({
                    "title": run.get("title", ""),
                    "format": run.get("format", ""),
                    "metrics": metrics,
                })
        return rows[-20:]

    def _write(self, report: dict) -> dict:
        path = self.settings.learning_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report


def learning_context(settings: Settings, max_chars: int = 9000) -> str:
    path: Path = settings.learning_file
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    lines = ["DAILY CHANNEL LEARNING — use patterns only; never copy wording or creator identity."]
    for item in data.get("competitors", [])[:3]:
        lines.append(
            f"Channel: {item.get('channel')} | subs={item.get('subscribers', 0)} | views={item.get('channel_views', 0)}"
        )
        for video in item.get("high_performing_recent_videos", [])[:4]:
            lines.append(f"- {video.get('views', 0)} views: {video.get('title', '')}")
    analytics = data.get("own_analytics", [])[-10:]
    if analytics:
        lines.append("ByteVexa recent performance:")
        for item in analytics:
            lines.append(f"- {item.get('title', '')}: {json.dumps(item.get('metrics', {}), ensure_ascii=False)}")
    comments = data.get("own_comments", [])[:15]
    if comments:
        lines.append("Viewer feedback themes from our comments:")
        for item in comments:
            lines.append(f"- {item.get('text', '')}")
    return "\n".join(lines)[:max_chars]
