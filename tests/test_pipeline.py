from pathlib import Path

from autopilot.config import Settings
from autopilot.pipeline import AutopilotPipeline


def test_dry_run_creates_manifest(tmp_path: Path) -> None:
    settings = Settings(
        artifacts_dir=tmp_path,
        openai_api_key=None,
        enable_uploads=False,
        default_video_format="short",
    )

    result = AutopilotPipeline(settings).run(topic="Useful AI study tools", dry_run=True)

    manifest = tmp_path / result.run_id / "manifest.json"
    assert manifest.exists()
    assert result.status == "planned"
    assert result.youtube_video_id is None
    assert "Dry run" in result.notes[0]


def test_uploads_are_off_by_default() -> None:
    settings = Settings()
    assert settings.enable_uploads is False
    assert settings.upload_privacy_status == "private"
