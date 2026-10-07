import importlib.util
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from typer.testing import CliRunner

from autopilot import cli
from autopilot.config import Settings
from autopilot.editorial import ByteVexaEditorialSystem
from autopilot.facts import FactVerifier, verified_curio_seed
_spec = importlib.util.spec_from_file_location("persist_state", Path(__file__).parents[1] / "scripts" / "persist_state.py")
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
merge_history = _module.merge_history


def test_live_slot_counts_actual_uploads_before_publishing(monkeypatch, tmp_path):
    settings = Settings(state_file=tmp_path / "history.json", shorts_per_day=2)
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli.DailyLearningLoop, "refresh", lambda self: {})
    monkeypatch.setattr(cli, "_longform_due", lambda *args: False)
    now = datetime.now(ZoneInfo(settings.schedule_timezone)).isoformat()
    uploads = [
        {"video_id": "live-a", "title": "AI agent one", "format": "short", "published_at": now},
        {"video_id": "live-b", "title": "AI agent two", "format": "short", "published_at": now},
    ]
    monkeypatch.setattr(cli.YouTubeUploader, "recent_uploads", lambda self, limit: uploads)
    monkeypatch.setattr(cli.AutopilotPipeline, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("duplicate publication")))
    result = CliRunner().invoke(cli.app, ["daily", "--live", "--slot", "morning"])
    assert result.exit_code == 0, result.output


def test_concurrent_histories_preserve_both_upload_ids():
    remote = {"videos": [{"video_id": "remote", "created_at": "2026-10-07T12:00:00Z"}], "topics": []}
    local = {"videos": [{"video_id": "local", "created_at": "2026-10-07T13:00:00Z"}], "topics": []}
    merged = merge_history(remote, local)
    assert {video["video_id"] for video in merged["videos"]} == {"remote", "local"}


def test_bytevexa_blocks_off_niche_local_news():
    editorial = ByteVexaEditorialSystem()
    assert not editorial.is_relevant_topic("STL County Issues Condemnation Threat to Local Apartment Complex")
    assert editorial.is_relevant_topic("AI Coding Agents Running Local Commands")
    assert editorial.is_relevant_topic("LibreOffice Spreadsheet Security Update")


def test_aurora_reserve_uses_two_authoritative_agencies():
    seed = verified_curio_seed(requested_topic="Why Auroras Glow in Different Colors")
    assert seed is not None
    assert {source.publisher for source in seed[1].sources} == {"NASA Science", "NOAA NESDIS"}
    assert FactVerifier().verify(seed[1]).confidence_score >= 65
