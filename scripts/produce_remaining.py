import time
from pathlib import Path
from rich.console import Console

from autopilot.config import Settings
from autopilot.pipeline import AutopilotPipeline
from autopilot.state import StateStore

console = Console()
TARGET = 5

CHANNELS = [
    ("chronosenigma", "ChronosEnigma"),
    ("empirepulse", "EmpirePulse"),
]

def main():
    console.print("[bold green]=== Completing Remaining Quota (Target: 5 Shorts Each) ===[/bold green]")
    for profile, name in CHANNELS:
        s = Settings(
            channel_profile=profile,
            channel_display_name=name,
            youtube_token_file=Path(f"secrets/youtube_token_{profile}.json"),
            upload_privacy_status="public",
            allow_public_uploads=True,
            shorts_public=True,
            enable_uploads=True,
        )
        state = StateStore(s.state_file)
        current = len(state.video_ids(100))
        needed = max(0, TARGET - current)
        console.print(f"\n[cyan]▶ {name} ({profile}): {current}/{TARGET} uploads. Need {needed} more.[/cyan]")

        attempts = 0
        while len(state.video_ids(100)) < TARGET and attempts < needed + 2:
            attempts += 1
            idx = len(state.video_ids(100)) + 1
            console.print(f"[yellow]Producing Short #{idx} for {name} (Attempt {attempts})...[/yellow]")
            t0 = time.time()
            try:
                pipeline = AutopilotPipeline(s)
                res = pipeline.run(dry_run=False, video_format="short")
                elapsed = time.time() - t0
                if res.status == "uploaded" and res.youtube_video_id:
                    link = f"https://youtube.com/shorts/{res.youtube_video_id}"
                    console.print(f"[bold green]✓ SUCCESS: {res.plan.title}[/bold green] ({elapsed:.1f}s)")
                    console.print(f"  Live URL: {link}")
                else:
                    console.print(f"[bold red]✗ FAILED: {res.plan.title if res.plan else 'No plan'}[/bold red] ({elapsed:.1f}s)")
                    console.print(f"  Notes: {res.notes}")
            except Exception as exc:
                elapsed = time.time() - t0
                console.print(f"[bold red]✗ Exception: {exc}[/bold red] ({elapsed:.1f}s)")
            finally:
                state = StateStore(s.state_file)

    console.print("\n[bold green]=== Batch Completed! ===[/bold green]")

if __name__ == "__main__":
    main()
