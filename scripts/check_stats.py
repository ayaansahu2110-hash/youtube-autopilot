from pathlib import Path
from googleapiclient.discovery import build
from rich.console import Console
from rich.table import Table

from autopilot.config import Settings
from autopilot.youtube import YouTubeAuth

console = Console()

CHANNELS = [
    ("bytevexa", "ByteVexa", "UC09G9D1CBuQBBWa7ZY8fRnQ", Path("secrets/youtube_token.json")),
    ("curioaxiom", "CurioAxiom", "UCpddoAgL5DCidscCMx4WMHQ", Path("secrets/youtube_token_curioaxiom.json")),
    ("wondertales", "WonderTales Kids", "UCgpwDJEsds9CfjR9JJXqI6Q", Path("secrets/youtube_token_wondertales.json")),
    ("mokshavani", "MokshaVani", "UCfLZBTZFO2SfgJJ-iGrlBBA", Path("secrets/youtube_token_mokshavani.json")),
    ("apexstoic", "ApexStoic", "UChPKS0EQQJPnMReTR-2pcvw", Path("secrets/youtube_token_apexstoic.json")),
    ("chronosenigma", "ChronosEnigma", "UCkskXfpnzm8lQnZGHOVMfQQ", Path("secrets/youtube_token_chronosenigma.json")),
    ("empirepulse", "EmpirePulse", "UC6rE9fs_Os6NSXdTN1oBNdw", Path("secrets/youtube_token_empirepulse.json")),
]

def main():
    table = Table(title="YouTube Channel Fleet Real-Time Performance & Stats")
    table.add_column("Channel Name", style="bold cyan")
    table.add_column("Profile", style="green")
    table.add_column("Subscribers", justify="right")
    table.add_column("Total Views", justify="right")
    table.add_column("Live Videos", justify="right")
    table.add_column("Auth Status", style="bold yellow")

    for profile, name, cid, token in CHANNELS:
        if not token.exists():
            table.add_row(name, profile, "N/A", "N/A", "N/A", "[red]Token Missing[/red]")
            continue

        s = Settings(
            channel_profile=profile,
            channel_display_name=name,
            expected_youtube_channel_id=cid,
            youtube_token_file=token,
        )
        auth = YouTubeAuth(s)
        try:
            creds = auth.credentials(interactive=False)
            yt = build("youtube", "v3", credentials=creds)
            res = yt.channels().list(part="snippet,statistics", id=cid).execute()
            items = res.get("items", [])
            if not items:
                table.add_row(name, profile, "N/A", "N/A", "N/A", "[yellow]Channel Not Found[/yellow]")
                continue
            stats = items[0].get("statistics", {})
            subs = stats.get("subscriberCount", "0")
            views = stats.get("viewCount", "0")
            vids = stats.get("videoCount", "0")
            table.add_row(name, profile, subs, views, vids, "[bold green]Active & Verified[/bold green]")
        except Exception as exc:
            table.add_row(name, profile, "N/A", "N/A", "N/A", f"[red]Error: {exc}[/red]"[:40])

    console.print(table)

if __name__ == "__main__":
    main()
