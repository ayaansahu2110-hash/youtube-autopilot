from unittest.mock import MagicMock, patch

from autopilot.config import Settings
from autopilot.youtube import YouTubeUploader


def test_channel_preflight_checks_identity_without_video_details():
    uploader = YouTubeUploader(Settings(expected_youtube_channel_id="expected"))
    service = MagicMock()
    service.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "expected"}]
    }
    with patch("autopilot.youtube.build", return_value=service), patch.object(
        uploader.auth, "credentials", return_value=MagicMock()
    ):
        uploader.verify_channel()
    service.channels.return_value.list.return_value.execute.assert_called_once_with(num_retries=3)
    service.videos.assert_not_called()


def test_recent_uploads_retries_transient_read_errors():
    uploader = YouTubeUploader(Settings(expected_youtube_channel_id="expected"))
    service = MagicMock()
    channel_request = service.channels.return_value.list.return_value
    channel_request.execute.side_effect = [
        {"items": [{"id": "expected"}]},
        {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "uploads"}}}]},
    ]
    service.playlistItems.return_value.list.return_value.execute.return_value = {
        "items": [{"contentDetails": {"videoId": "abc"}, "snippet": {"title": "Fact"}}]
    }
    service.videos.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "abc", "contentDetails": {"duration": "PT30S"}}]
    }
    with patch("autopilot.youtube.build", return_value=service), patch.object(
        uploader.auth, "credentials", return_value=MagicMock()
    ):
        result = uploader.recent_uploads(limit=1)
    assert result[0]["format"] == "short"
    assert channel_request.execute.call_count == 2
    assert all(call.kwargs == {"num_retries": 3} for call in channel_request.execute.call_args_list)
    service.playlistItems.return_value.list.return_value.execute.assert_called_once_with(num_retries=3)
    service.videos.return_value.list.return_value.execute.assert_called_once_with(num_retries=3)
