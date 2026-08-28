from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from autopilot.config import Settings
from autopilot.models import VideoPlan


YOUTUBE_UPLOAD_SCOPE = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeUploader:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _credentials(self) -> Credentials:
        token_path = self.settings.youtube_token_file
        credentials: Credentials | None = None

        if token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_UPLOAD_SCOPE)

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())

        if not credentials or not credentials.valid:
            secrets_path = self.settings.youtube_client_secrets_file
            if not secrets_path.exists():
                raise FileNotFoundError(
                    f"YouTube OAuth client file not found: {secrets_path}. "
                    "Download a Desktop OAuth client JSON from Google Cloud and keep it outside Git."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), YOUTUBE_UPLOAD_SCOPE)
            credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")
        return credentials

    def upload(self, video_path: Path, plan: VideoPlan) -> str:
        if not self.settings.enable_uploads:
            raise RuntimeError("Uploads are disabled. Set ENABLE_UPLOADS=true only after testing.")
        if not video_path.exists():
            raise FileNotFoundError(video_path)

        youtube = build("youtube", "v3", credentials=self._credentials())
        request = youtube.videos().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": plan.title[:100],
                    "description": plan.description,
                    "tags": plan.tags,
                    "categoryId": "28",
                },
                "status": {"privacyStatus": self.settings.upload_privacy_status},
            },
            media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
        )
        response = request.execute()
        return response["id"]
