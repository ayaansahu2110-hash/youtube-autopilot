from pathlib import Path
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
from autopilot.youtube import YouTubeUploader

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


ALL_CHANNELS = [
    ("bytevexa", "ByteVexa", "UC09G9D1CBuQBBWa7ZY8fRnQ", Path("secrets/youtube_token.json")),
    ("curioaxiom", "CurioAxiom", "UCpddoAgL5DCidscCMx4WMHQ", Path("secrets/youtube_token_curioaxiom.json")),
    ("wondertales", "WonderTales Kids", "UCgpwDJEsds9CfjR9JJXqI6Q", Path("secrets/youtube_token_wondertales.json")),
    ("mokshavani", "MokshaVani", "UCfLZBTZFO2SfgJJ-iGrlBBA", Path("secrets/youtube_token_mokshavani.json")),
    ("apexstoic", "ApexStoic", "UChPKS0EQQJPnMReTR-2pcvw", Path("secrets/youtube_token_apexstoic.json")),
    ("chronosenigma", "ChronosEnigma", "UCkskXfpnzm8lQnZGHOVMfQQ", Path("secrets/youtube_token_chronosenigma.json")),
    ("empirepulse", "EmpirePulse", "UC6rE9fs_Os6NSXdTN1oBNdw", Path("secrets/youtube_token_empirepulse.json")),
]


def _settings_for_format(settings: Settings, video_format: str) -> Settings:
    if video_format == "short" and settings.shorts_public:
        return settings.model_copy(
            update={"upload_privacy_status": "public", "allow_public_uploads": True}
        )
    return settings


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
    """Run the one-time browser OAuth flow for upload + analytics access (ByteVexa)."""
    settings = load_settings()
    token = YouTubeAuth(settings).authorize()
    console.print(f"[bold green]YouTube authorized.[/bold green] Token saved to {token}")


@app.command("auth-curioaxiom")
def auth_curioaxiom() -> None:
    """Run browser OAuth flow for CurioAxiom (channel ID: UCpddoAgL5DCidscCMx4WMHQ)."""
    settings = Settings(
        channel_profile="curioaxiom",
        channel_display_name="CurioAxiom",
        expected_youtube_channel_id="UCpddoAgL5DCidscCMx4WMHQ",
        youtube_token_file=Path("secrets/youtube_token_curioaxiom.json"),
    )
    token = YouTubeAuth(settings).authorize()
    console.print(f"[bold green]CurioAxiom authorized.[/bold green] Token saved to {token}")


@app.command("auth-channel")
def auth_channel(
    profile: str = typer.Option(
        ..., "--profile", "-p",
        help="Channel profile: bytevexa, curioaxiom, wondertales, mokshavani, apexstoic, chronosenigma, empirepulse"
    ),
) -> None:
    """Run browser OAuth flow to link and authorize any of the 7 YouTube channels."""
    from autopilot.config import CHANNEL_PROFILES, PROFILE_CONFIGS
    norm_profile = profile.strip().lower()
    if norm_profile not in CHANNEL_PROFILES:
        raise typer.BadParameter(f"Unknown profile: {profile}. Valid options: {', '.join(CHANNEL_PROFILES)}")
    cfg = PROFILE_CONFIGS[norm_profile]
    settings = Settings(
        channel_profile=norm_profile,
        channel_display_name=cfg["display_name"],
        youtube_token_file=Path(cfg["token_file"]),
    )
    token = YouTubeAuth(settings).authorize()
    console.print(f"[bold green]{cfg['display_name']} ({norm_profile}) authorized.[/bold green] Token saved to {token}")


@app.command("verify-youtube")
def verify_youtube() -> None:
    """Verify the OAuth token belongs to the configured isolated channel."""
    settings = load_settings()
    uploader = YouTubeUploader(settings)
    uploader.recent_uploads(limit=1)
    console.print(
        f"[bold green]Channel verified:[/bold green] {settings.channel_display_name} "
        f"({settings.expected_youtube_channel_id or 'identity lock not configured'})"
    )


@app.command("verify-all")
def verify_all() -> None:
    """Verify OAuth tokens and live authorization for all 7 channels."""
    for profile, display_name, expected_id, token_path in ALL_CHANNELS:
        s = Settings(
            channel_profile=profile,
            channel_display_name=display_name,
            expected_youtube_channel_id=expected_id,
            youtube_token_file=token_path,
        )
        if not token_path.exists():
            console.print(f"[yellow]○ {display_name}[/yellow] ({profile}): Token not created yet. Run: python -m autopilot.cli auth-channel --profile {profile}")
            continue
        try:
            uploader = YouTubeUploader(s)
            uploader.recent_uploads(limit=1)
            console.print(f"[bold green]✓ {display_name}[/bold green] ({profile}): Authorized and live on YouTube.")
        except Exception as exc:
            console.print(f"[bold red]✗ {display_name}[/bold red] ({profile}) verification notice: {exc}")


@app.command("run")
def run_once(
    topic: str | None = typer.Option(None, help="Optional topic override"),
    video_format: str | None = typer.Option(None, "--format", help="short or long"),
    dry_run: bool = typer.Option(True, "--dry-run/--render", help="Plan only or render media"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Channel profile to run"),
) -> None:
    settings = Settings(channel_profile=profile.strip().lower()) if profile else load_settings()
    chosen_format = video_format or settings.default_video_format
    production_settings = _settings_for_format(settings, chosen_format)
    result = AutopilotPipeline(production_settings).run(
        topic=topic, dry_run=dry_run, video_format=chosen_format
    )
    _print_result(result, production_settings)
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
    slot: str = typer.Option("all", "--slot", help="morning, midday, evening, or all"),
) -> None:
    """Run a scheduled production slot for the selected isolated channel profile."""
    settings = load_settings()
    state = StateStore(settings.state_file)
    DailyLearningLoop(settings, state).refresh()
    dry_run = not live
    slot = slot.strip().lower()
    if slot not in {"morning", "midday", "evening", "all"}:
        raise typer.BadParameter("slot must be morning, midday, evening, or all")

    results = []
    short_count = max(1, settings.shorts_per_day) if slot == "all" else 1
    short_settings = _settings_for_format(settings, "short")
    for _ in range(short_count):
        short_result = AutopilotPipeline(short_settings).run(dry_run=dry_run, video_format="short")
        results.append(short_result)
        _print_result(short_result, short_settings)
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
        AutopilotPipeline(_settings_for_format(settings, "short")).run(
            dry_run=not settings.enable_uploads,
            video_format="short",
        )

    def evening_job() -> None:
        state = StateStore(settings.state_file)
        DailyLearningLoop(settings, state).refresh()
        result = AutopilotPipeline(_settings_for_format(settings, "short")).run(
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


@app.command("run-all")
def run_all(
    slot: str = typer.Option("all", "--slot", help="morning, evening, or all"),
    live: bool = typer.Option(False, "--live", help="Render and publish; otherwise planning only"),
) -> None:
    """Run production cycle across both ByteVexa and CurioAxiom."""
    slot = slot.strip().lower()
    dry_run = not live
    for profile, display_name, expected_id, token_path in ALL_CHANNELS:
        try:
            console.print(f"\n[bold cyan]=== Running {display_name} [{profile}] ({slot}) ===[/bold cyan]")
            s = Settings(
                channel_profile=profile,
                channel_display_name=display_name,
                expected_youtube_channel_id=expected_id,
                youtube_token_file=token_path,
            )
            # If live requested but token does not exist yet, produce full video artifacts safely
            effective_dry = dry_run or not token_path.exists()
            if not dry_run and not token_path.exists():
                console.print(f"[yellow]Notice: {display_name} YouTube token not linked yet; rendering full video to artifacts for review.[/yellow]")

            state = StateStore(s.state_file)
            try:
                DailyLearningLoop(s, state).refresh()
            except Exception:
                pass

            short_count = max(1, s.shorts_per_day) if slot == "all" else 1
            short_settings = _settings_for_format(s, "short")
            for _ in range(short_count):
                short_res = AutopilotPipeline(short_settings).run(dry_run=effective_dry, video_format="short")
                _print_result(short_res, short_settings)

            if slot in {"evening", "all"} and _longform_due(s):
                console.print(f"[cyan]Alternate-day long-form due for {display_name}...[/cyan]")
                long_res = AutopilotPipeline(s).run(dry_run=effective_dry, video_format="long")
                _print_result(long_res, s)
        except Exception as exc:
            console.print(f"[bold red]Error in automated slot for {display_name}: {exc}[/bold red]")


@app.command("schedule-all")
def schedule_all() -> None:
    """Run unified 2-channel background scheduler at 12:00 and 18:00 IST for ByteVexa & CurioAxiom."""
    settings = load_settings()
    scheduler = BlockingScheduler(timezone=settings.schedule_timezone)

    def execute_slot(slot_name: str, is_morning: bool) -> None:
        console.print(f"\n[bold green]Executing {slot_name} production slot across all 7 channels ({settings.schedule_timezone})...[/bold green]")
        for profile, display_name, expected_id, token_path in ALL_CHANNELS:
            try:
                s = Settings(
                    channel_profile=profile,
                    channel_display_name=display_name,
                    expected_youtube_channel_id=expected_id,
                    youtube_token_file=token_path,
                )
                state = StateStore(s.state_file)
                try:
                    DailyLearningLoop(s, state).refresh()
                except Exception:
                    pass

                should_upload = s.enable_uploads and token_path.exists()
                short_s = _settings_for_format(s, "short")
                short_res = AutopilotPipeline(short_s).run(
                    dry_run=not should_upload,
                    video_format="short",
                )
                _print_result(short_res, short_s)

                if not is_morning and short_res.status != "failed" and _longform_due(s):
                    long_res = AutopilotPipeline(s).run(
                        dry_run=not should_upload,
                        video_format="long",
                    )
                    _print_result(long_res, s)
            except Exception as exc:
                console.print(f"[bold red]Slot error for {display_name}:[/bold red] {exc}")

    scheduler.add_job(
        lambda: execute_slot("12:00 Noon", True),
        "cron",
        hour=12,
        minute=0,
        id="both-channels-noon-short",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        lambda: execute_slot("18:00 Evening", False),
        "cron",
        hour=18,
        minute=0,
        id="both-channels-evening-short-long",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    console.print(f"[bold green]Unified 7-Channel Scheduler active at 12:00 and 18:00 ({settings.schedule_timezone}) across all channels[/bold green]")
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
