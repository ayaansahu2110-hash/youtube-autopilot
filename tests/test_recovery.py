from typer.testing import CliRunner

from autopilot import cli
from autopilot.config import Settings
from autopilot.facts import FactVerifier, verified_curio_seed


def test_new_reserve_is_verified_and_excludes_used_concept():
    title = "Why the Moon Changes Shape Without Changing Its Shape"
    seed = verified_curio_seed(requested_topic=title)
    assert seed is not None
    assert FactVerifier().verify(seed[1]).confidence_score >= 65
    assert verified_curio_seed(
        requested_topic=title, excluded_topics=["Moon phases explained"]
    ) is None


def test_short_discovery_exception_does_not_block_due_long(monkeypatch, tmp_path):
    settings = Settings(state_file=tmp_path / "history.json")
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli.DailyLearningLoop, "refresh", lambda self: {})
    monkeypatch.setattr(cli, "_longform_due", lambda *args: True)
    formats = []

    def fail(self, *, dry_run, video_format):
        formats.append(video_format)
        raise RuntimeError("No verified candidates")

    monkeypatch.setattr(cli.AutopilotPipeline, "run", fail)
    result = CliRunner().invoke(cli.app, ["daily", "--live", "--slot", "evening"])
    assert result.exit_code == 1
    assert formats == ["short", "long"]
