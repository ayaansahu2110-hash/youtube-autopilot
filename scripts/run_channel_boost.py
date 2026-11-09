import json
import time
from pathlib import Path
from rich.console import Console

from autopilot.config import Settings
from autopilot.pipeline import AutopilotPipeline
from autopilot.state import StateStore

console = Console()

TARGET_PER_CHANNEL = 5
BOOST_CHANNELS = [
    ("wondertales", "WonderTales Kids"),
    ("mokshavani", "MokshaVani"),
    ("apexstoic", "ApexStoic"),
    ("chronosenigma", "ChronosEnigma"),
    ("empirepulse", "EmpirePulse"),
]

RESULTS_FILE = Path("logs/boost_results.json")

def load_results() -> dict:
    if RESULTS_FILE.exists():
        try:
            return json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"published": [], "rendered": [], "failed": []}

def save_results(data: dict) -> None:
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

def main() -> None:
    console.print("[bold green]=== Starting Day 1 Boost Production Fleet (Target: 5 Shorts Each) ===[/bold green]")
    results = load_results()

    for profile, display_name in BOOST_CHANNELS:
        s = Settings(
            channel_profile=profile,
            channel_display_name=display_name,
            youtube_token_file=Path(f"secrets/youtube_token_{profile}.json"),
            upload_privacy_status="public",
            allow_public_uploads=True,
            shorts_public=True,
            enable_uploads=True,
        )

        state = StateStore(s.state_file)
        current_uploaded = len(state.video_ids(limit=100))
        target_goal = TARGET_PER_CHANNEL
        needed = max(0, target_goal - current_uploaded)

        console.print("\n[bold cyan]--------------------------------------------------[/bold cyan]")
        console.print(f"[bold cyan]▶ Channel: {display_name} ({profile})[/bold cyan]")
        console.print(f"  Current Uploads: {current_uploaded} / {target_goal} (Need {needed} more)")
        console.print("[bold cyan]--------------------------------------------------[/bold cyan]")

        if needed <= 0:
            console.print(f"[green]✓ {display_name} already has {current_uploaded} videos. Moving to next channel.[/green]")
            continue

        attempts = 0
        max_attempts = needed + 3
        while len(state.video_ids(limit=100)) < target_goal and attempts < max_attempts:
            attempts += 1
            current = len(state.video_ids(limit=100))
            console.print(f"\n[yellow]Producing Short #{current + 1} (Attempt {attempts}) for {display_name}...[/yellow]")
            t0 = time.time()
            try:
                pipeline = AutopilotPipeline(s)
                res = pipeline.run(dry_run=False, video_format="short")
                elapsed = time.time() - t0

                if res.status == "uploaded" and res.youtube_video_id:
                    link = f"https://youtube.com/shorts/{res.youtube_video_id}"
                    console.print(f"[bold green]✓ SUCCESS: {res.plan.title}[/bold green] ({elapsed:.1f}s)")
                    console.print(f"  Live URL: {link}")
                    results["published"].append({
                        "channel": display_name,
                        "profile": profile,
                        "title": res.plan.title,
                        "video_id": res.youtube_video_id,
                        "url": link,
                        "elapsed_seconds": round(elapsed, 1),
                    })
                    save_results(results)
                elif res.status in {"rendered", "planned"}:
                    console.print(f"[bold yellow]○ RENDERED (Upload deferred/quota): {res.plan.title}[/bold yellow] ({elapsed:.1f}s)")
                    results["rendered"].append({
                        "channel": display_name,
                        "profile": profile,
                        "title": res.plan.title,
                        "video_path": str(res.video_path),
                        "elapsed_seconds": round(elapsed, 1),
                    })
                    save_results(results)
                else:
                    console.print(f"[bold red]✗ FAILED: {res.plan.title}[/bold red] ({elapsed:.1f}s)")
                    for err in (res.notes or []):
                        console.print(f"  - {err}")
                    results["failed"].append({
                        "channel": display_name,
                        "profile": profile,
                        "title": res.plan.title,
                        "notes": res.notes,
                    })
                    save_results(results)
            except Exception as exc:
                elapsed = time.time() - t0
                console.print(f"[bold red]✗ Error on {display_name} Attempt {attempts}: {exc}[/bold red]")
                results["failed"].append({
                    "channel": display_name,
                    "profile": profile,
                    "error": str(exc),
                })
                save_results(results)
            finally:
                state = StateStore(s.state_file)

    console.print("\n[bold green]==================================================[/bold green]")
    console.print("[bold green]Day 1 Boost Batch Finished![/bold green]")
    console.print(f"  Total Published In This Session: {len(results['published'])}")
    console.print(f"  Total Rendered / Stored: {len(results['rendered'])}")
    console.print(f"  Failures: {len(results['failed'])}")
    console.print("[bold green]==================================================[/bold green]\n")

    for item in results["published"]:
        console.print(f"• [{item['channel']}] {item['title']} -> {item['url']}")

if __name__ == "__main__":
    main()
