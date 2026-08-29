import shutil
from datetime import date, datetime
from zoneinfo import ZoneInfo

import typer
from apscheduler.schedulers.blocking import BlockingScheduler
from rich.console import Console
from rich.table import Table

from autopilot.analytics import AnalyticsClient
from autopilot.config import Settings
from autopilot.learning import DailyLearningLoop
from autopilot.pipeline import AutopilotPipeline
from autopilot.state import StateStore
from autopilot.youtube import YouTubeAuth

app = typer.Typer(no_args_is_help=True, help="YouTube Autopilot control CLI")
console = Console()


def load_settings() -> Settings:
    return Settings()


def _longform_due(settings: Settings) -> bool:
    if not settings.longform_enabled:
        return False
    local_today = datetime.now(ZoneInfo(settings.schedule_timezone)).date()
    anchor = date.fromisoformat(settings.longform_anchor_date)
    interval = max(1, settings.longform_every_days)
    return (local_today - anchor).days >= 0 and (local_today - anchor).days % interval == 0


@app.command()
def doctor() -> None:
    """Check local prerequisites without exposing secrets."""
    settings = load_settings()
    table = Table(title="YouTube Autopilot Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_row("Channel profile", settings.channel_profile)
    table.add_row("Channel name", settings.channel_display_name)
    table.add_row("Isolation lock", settings.expected_youtube_channel_id or "not configured")
    table.add_row("FFmpeg", "OK" if shutil.which(settings.ffmpeg_binary) else "MISSING")
    table.add_row("FFprobe", "OK" if shutil.which(settings.ffprobe_binary) else "MISSING")
    table.add_row("Gemini API", "configured" if settings.gemini_api_key else "not configured")
    table.add_row("OpenAI API", "configured" if settings.openai_api_key else "optional")
    table.add_row(
        "AI scripting",
        f"configured ({settings.llm_provider_name})" if settings.llm_configured else "fallback only",
    )
    table.add_row("Pexels API", "configured" if settings.pexels_api_key else "optional; fallback visuals")
    table.add_row("YouTube OAuth client", "configured" if settings.youtube_client_secrets_file.exists() else "not configured")
    table.add_row("YouTube token", "configured" if settings.youtube_token_file.exists() else "not authorized")
    table.add_row("Uploads", "ENABLED" if settings.enable_uploads else "disabled (safe default)")
    table.add_row("Upload privacy", settings.upload_privacy_status)
    table.add_row("Shorts per day", str(settings.shorts_per_day))
    table.add_row("Long-form cadence", f"every {settings.longform_every_days} days")
    console.print(table)


@app.command("auth-youtube")
def auth_youtube() -> None:
    """Run the one-time browser OAuth flow for upload + analytics access."""
    settings = load_settings()
    token = YouTubeAuth(settings).authorize()
    console.print(f"[bold green]YouTube authorized.[/bold green] Token saved to {token}")


@app.command("run")
def run_once(
    topic: str | None = typer.Option(None, help="Optional topic override"),
    video_format: str | None = typer.Option(None, "--format", help="short or long"),
    dry_run: bool = typer.Option(True, "--dry-run/--render", help="Plan only or render media"),
) -> None:
    settings = load_settings()
    result = AutopilotPipeline(settings).run(topic=topic, dry_run=dry_run, video_format=video_format)
    _print_result(result, settings)
    if result.status == "failed":
        raise typer.Exit(code=1)


@app.command()
def analytics() -> None:
    settings = load_settings()
    state = StateStore(settings.state_file)
    count = AnalyticsClient(settings, state).refresh()
    console.print(f"Updated analytics for {count} tracked video(s).")


@app.command()
def learn() -> None:
    """Refresh competitor patterns plus ByteVexa analytics/comments."""
    settings = load_settings()
    state = StateStore(settings.state_file)
    report = DailyLearningLoop(settings, state).refresh()
    console.print(
        f"Learning refreshed: {len(report.get('competitors', []))} competitor channels, "
        f"{len(report.get('own_comments', []))} comments."
    )


@app.command()
def daily(
    live: bool = typer.Option(False, "--live", help="Render and publish; otherwise run planning only"),
    slot: str = typer.Option("all", "--slot", help="morning, evening, or all"),
) -> None:
    """Run a scheduled production slot for the selected isolated channel profile."""
    settings = load_settings()
    state = StateStore(settings.state_file)
    DailyLearningLoop(settings, state).refresh()
    dry_run = not live
    slot = slot.strip().lower()
    if slot not in {"morning", "evening", "all"}:
        raise typer.BadParameter("slot must be morning, evening, or all")

    results = []
    short_count = max(1, settings.shorts_per_day) if slot == "all" else 1
    for _ in range(short_count):
        short_result = AutopilotPipeline(settings).run(dry_run=dry_run, video_format="short")
        results.append(short_result)
        _print_result(short_result, settings)
        if short_result.status == "failed":
            break

    should_make_long = slot in {"evening", "all"} and _longform_due(settings)
    if not any(result.status == "failed" for result in results) and should_make_long:
        long_result = AutopilotPipeline(settings).run(dry_run=dry_run, video_format="long")
        results.append(long_result)
        _print_result(long_result, settings)

    if any(result.status == "failed" for result in results):
        raise typer.Exit(code=1)


@app.command()
def schedule() -> None:
    """Keep a local machine running and execute two daily production slots."""
    settings = load_settings()
    scheduler = BlockingScheduler(timezone=settings.schedule_timezone)

    def morning_job() -> None:
        state = StateStore(settings.state_file)
        DailyLearningLoop(settings, state).refresh()
        AutopilotPipeline(settings).run(
            dry_run=not settings.enable_uploads,
            video_format="short",
        )

    def evening_job() -> None:
        state = StateStore(settings.state_file)
        DailyLearningLoop(settings, state).refresh()
        result = AutopilotPipeline(settings).run(
            dry_run=not settings.enable_uploads,
            video_format="short",
        )
        if result.status != "failed" and _longform_due(settings):
            AutopilotPipeline(settings).run(
                dry_run=not settings.enable_uploads,
                video_format="long",
            )

    scheduler.add_job(
        morning_job,
        "cron",
        hour=12,
        minute=0,
        id=f"{settings.channel_profile}-noon-short",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        evening_job,
        "cron",
        hour=18,
        minute=0,
        id=f"{settings.channel_profile}-evening-short-long",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    console.print(f"Scheduler active at 12:00 and 18:00 ({settings.schedule_timezone})")
    scheduler.start()


def _print_result(result, settings: Settings) -> None:
    style = "green" if result.status in {"planned", "rendered", "uploaded"} else "red"
    console.print(f"[bold {style}]Run {result.run_id}: {result.status}[/bold {style}]")
    console.print(f"Title: {result.plan.title}")
    if result.quality and result.quality.errors:
        for error in result.quality.errors:
            console.print(f"[red]- {error}[/red]")
    console.print(f"Artifacts: {settings.artifacts_dir / result.run_id}")


if __name__ == "__main__":
    app()
