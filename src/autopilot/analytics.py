from datetime import date, timedelta

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from autopilot.config import Settings
from autopilot.state import StateStore
from autopilot.youtube import YouTubeAuth


class AnalyticsClient:
    def __init__(self, settings: Settings, state: StateStore):
        self.settings = settings
        self.state = state
        self.auth = YouTubeAuth(settings)

    def refresh(self) -> int:
        video_ids = set(self.state.video_ids(limit=100))
        if not video_ids or not self.settings.youtube_token_file.exists():
            return 0
        try:
            service = build("youtubeAnalytics", "v2", credentials=self.auth.credentials(interactive=False))
            end = date.today()
            start = end - timedelta(days=self.settings.analytics_lookback_days)
            report = service.reports().query(
                ids="channel==MINE",
                startDate=start.isoformat(),
                endDate=end.isoformat(),
                metrics="views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares,subscribersGained",
                dimensions="video",
                sort="-views",
                maxResults=200,
            ).execute()
        except (HttpError, FileNotFoundError, RuntimeError):
            return 0

        headers = [item["name"] for item in report.get("columnHeaders", [])]
        updated = 0
        for row in report.get("rows", []) or []:
            data = dict(zip(headers, row, strict=False))
            video_id = str(data.pop("video", ""))
            if video_id not in video_ids:
                continue
            metrics = {key: float(value or 0) for key, value in data.items()}
            self.state.update_analytics(video_id, metrics)
            updated += 1
        return updated
