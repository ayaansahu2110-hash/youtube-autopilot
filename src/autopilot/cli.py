import shutil
from pathlib import Path

import typer
from apscheduler.schedulers.blocking import BlockingScheduler
from rich.console import Console
from rich.table import Table

from autopilot.config import Settings
from autopilot.pipeline import AutopilotPipeline

app = typer.Typer(no_args_is_help=True, help="YouTube Autopilot control CLI")
console = Console()


def load_settings() -> Settings:
    return Settings()


@app.command()
def doctor() -> None:
    """Check local prerequisites without exposing secrets."""
    settings = load_settings()
    table = Table(title="YouTube Autopilot Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_row("FFmpeg", "OK" if shutil.which(settings.ffmpeg_binary) else "MISSING")
    table.add_row("OpenAI key", "configured" if settings.openai_api_key else "optional / not configured")
    table.add_row(
        "YouTube OAuth client",
        "configured" if settings.youtube_client_secrets_file.exists() else "not configured",
    )
    table.add_row("Uploads", "ENABLED" if settings.enable_uploads else "disabled (safe default)")
    table.add_row("Upload privacy", settings.upload_privacy_status)
    console.print(table)


@app.command("run")
def run_once(
    topic: str | None = typer.Option(None, help="Optional topic override"),
    dry_run: bool = typer.Option(True, "--dry-run/--render", help="Plan only or render media"),
) -> None:
    settings = load_settings()
    result = AutopilotPipeline(settings).run(topic=topic, dry_run=dry_run)
    console.print(f"[bold green]Run {result.run_id} complete[/bold green]")
    console.print(f"Status: {result.status}")
    console.print(f"Title: {result.plan.title}")
    console.print(f"Artifacts: {settings.artifacts_dir / result.run_id}")


@app.command()
def schedule() -> None:
    """Run the pipeline once per day at the configured local time."""
    settings = load_settings()
    scheduler = BlockingScheduler(timezone=settings.schedule_timezone)

    def job() -> None:
        AutopilotPipeline(load_settings()).run(dry_run=not load_settings().enable_uploads)

    scheduler.add_job(
        job,
        "cron",
        hour=settings.schedule_hour,
        minute=settings.schedule_minute,
        id="daily-youtube-autopilot",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    console.print(
        f"Scheduler active: daily at {settings.schedule_hour:02d}:{settings.schedule_minute:02d} "
        f"({settings.schedule_timezone})"
    )
    scheduler.start()


if __name__ == "__main__":
    app()
