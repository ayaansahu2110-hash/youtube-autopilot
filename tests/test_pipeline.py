from pathlib import Path

from autopilot.config import Settings
from autopilot.pipeline import AutopilotPipeline
from autopilot.providers.tts import EdgeTTSProvider


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


def test_tts_uses_gemini_fallback_after_edge_outage(tmp_path: Path, monkeypatch) -> None:
    provider = EdgeTTSProvider("en-US-AndrewNeural", gemini_api_key="configured")
    output = tmp_path / "voice.mp3"

    async def fail_edge(text: str, path: Path) -> None:
        raise RuntimeError("Edge WebSocket returned 403")

    def save_gemini(text: str, path: Path) -> None:
        assert text == "Verified narration."
        path.write_bytes(b"premium-audio")

    monkeypatch.setattr(provider, "_save_edge_with_retry", fail_edge)
    monkeypatch.setattr(provider, "_save_with_gemini", save_gemini)

    assert provider.synthesize("Verified narration.", output) == output
    assert output.read_bytes() == b"premium-audio"


def test_tts_does_not_hide_edge_failure_without_fallback_key(tmp_path: Path, monkeypatch) -> None:
    provider = EdgeTTSProvider("en-US-AndrewNeural")
    output = tmp_path / "voice.mp3"

    async def fail_edge(text: str, path: Path) -> None:
        raise RuntimeError("Edge WebSocket returned 403")

    monkeypatch.setattr(provider, "_save_edge_with_retry", fail_edge)

    try:
        provider.synthesize("Verified narration.", output)
    except RuntimeError as exc:
        assert "GEMINI_API_KEY is empty" in str(exc)
    else:
        raise AssertionError("TTS outage should remain visible when no safe fallback is configured")
