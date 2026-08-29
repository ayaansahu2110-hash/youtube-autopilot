from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from autopilot.config import Settings
from autopilot.models import VideoPlan


YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


class YouTubeAuth:
    def __init__(self, settings: Settings):
        self.settings = settings

    def credentials(self, *, interactive: bool) -> Credentials:
        token_path = self.settings.youtube_token_file
        credentials: Credentials | None = None
        if token_path.exists():
            try:
                credentials = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_SCOPES)
            except (ValueError, OSError):
                credentials = None

        if credentials and not credentials.has_scopes(YOUTUBE_SCOPES):
            credentials = None
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        if credentials and credentials.valid:
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(credentials.to_json(), encoding="utf-8")
            return credentials

        if not interactive:
            raise RuntimeError("YouTube OAuth token is missing/invalid; run `youtube-autopilot auth-youtube` locally.")

        secrets_path = self.settings.youtube_client_secrets_file
        if not secrets_path.exists():
            raise FileNotFoundError(
                f"YouTube OAuth client file not found: {secrets_path}. Download a Desktop OAuth client JSON from Google Cloud."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), YOUTUBE_SCOPES)
        credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")
        return credentials

    def authorize(self) -> Path:
        self.credentials(interactive=True)
        return self.settings.youtube_token_file


class YouTubeUploader:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.auth = YouTubeAuth(settings)

    def _service(self):
        return build("youtube", "v3", credentials=self.auth.credentials(interactive=False))

    def recent_uploads(self, limit: int = 30) -> list[dict[str, str]]:
        """Return the channel's most recent real uploads for cross-run duplicate protection."""
        youtube = self._service()
        channel_items = youtube.channels().list(part="contentDetails", mine=True, maxResults=1).execute().get("items", [])
        if not channel_items:
            return []
        uploads_playlist = (
            channel_items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        )
        if not uploads_playlist:
            return []
        data = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads_playlist,
            maxResults=max(1, min(50, limit)),
        ).execute()
        output: list[dict[str, str]] = []
        for item in data.get("items", []) or []:
            snippet = item.get("snippet", {})
            video_id = str(item.get("contentDetails", {}).get("videoId") or "")
            title = str(snippet.get("title") or "").strip()
            if video_id and title:
                output.append(
                    {
                        "video_id": video_id,
                        "title": title,
                        "published_at": str(snippet.get("publishedAt") or ""),
                    }
                )
        return output

    def delete_video(self, video_id: str) -> None:
        """Delete one owned YouTube upload by ID."""
        if not video_id:
            raise ValueError("video_id is required")
        self._service().videos().delete(id=video_id).execute()

    def upload(self, video_path: Path, plan: VideoPlan, thumbnail_path: Path | None = None) -> str:
        if not self.settings.enable_uploads:
            raise RuntimeError("Uploads are disabled. Set ENABLE_UPLOADS=true only after testing.")
        if self.settings.upload_privacy_status == "public" and not self.settings.allow_public_uploads:
            raise RuntimeError("Public uploads are locked. Set ALLOW_PUBLIC_UPLOADS=true only after channel/API review.")
        if not video_path.exists():
            raise FileNotFoundError(video_path)

        youtube = self._service()
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": plan.title[:100],
                    "description": plan.description[:5000],
                    "tags": plan.tags[:30],
                    "categoryId": self.settings.youtube_category_id,
                },
                "status": {
                    "privacyStatus": self.settings.upload_privacy_status,
                    "selfDeclaredMadeForKids": self.settings.youtube_made_for_kids,
                },
            },
            media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
        )
        response = None
        while response is None:
            _, response = request.next_chunk()
        video_id = str(response["id"])

        if thumbnail_path and thumbnail_path.exists():
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg", resumable=False),
            ).execute()
        return video_id
