import sys
import time
from pathlib import Path
from rich.console import Console

from autopilot.config import Settings
from autopilot.pipeline import AutopilotPipeline

console = Console()

def main():
    profile = sys.argv[1] if len(sys.argv) > 1 else "chronosenigma"
    name = {
        "chronosenigma": "ChronosEnigma",
        "empirepulse": "EmpirePulse",
        "wondertales": "WonderTales Kids",
        "mokshavani": "MokshaVani",
        "apexstoic": "ApexStoic",
    }.get(profile, profile)

    s = Settings(
        channel_profile=profile,
        channel_display_name=name,
        youtube_token_file=Path(f"secrets/youtube_token_{profile}.json"),
        upload_privacy_status="public",
        allow_public_uploads=True,
        shorts_public=True,
        enable_uploads=True,
    )
    console.print(f"[bold cyan]▶ Starting run for {name} ({profile})...[/bold cyan]")
    t0 = time.time()
    p = AutopilotPipeline(s)
    res = p.run(dry_run=False, video_format="short")
    elapsed = time.time() - t0
    if res.status == "uploaded" and res.youtube_video_id:
        link = f"https://youtube.com/shorts/{res.youtube_video_id}"
        console.print(f"[bold green]✓ SUCCESS: {res.plan.title}[/bold green] ({elapsed:.1f}s)")
        console.print(f"  Live URL: {link}")
    else:
        console.print(f"[bold red]✗ FAILED: {res.plan.title if res.plan else 'No plan'}[/bold red] ({elapsed:.1f}s)")
        console.print(f"  Notes: {res.notes}")

if __name__ == "__main__":
    main()
