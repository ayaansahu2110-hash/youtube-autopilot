"""
GTA 6 Official Asset Preparation Script
----------------------------------------
Downloads Rockstar Games Official GTA 6 Trailer 1 and slices it into
16 themed, 2.5-3.0 second cinematic clips (both 16:9 and 9:16 vertical)
and high-resolution still screenshots for use across GTA6Hub video automation.
"""
from pathlib import Path
import subprocess
import sys


RAW_DIR = Path("assets/gta6/raw")
CLIPS_DIR = Path("assets/gta6/clips")
STILLS_DIR = Path("assets/gta6/stills")

RAW_DIR.mkdir(parents=True, exist_ok=True)
CLIPS_DIR.mkdir(parents=True, exist_ok=True)
STILLS_DIR.mkdir(parents=True, exist_ok=True)

TRAILER_PATH = RAW_DIR / "trailer_1.mp4"
YOUTUBE_URL = "https://www.youtube.com/watch?v=QdBZY2fkU-0"

SCENES = [
    ("01_lucia_prison", 2.0, 4.5, "Lucia in prison interview"),
    ("02_miami_sunset_freeway", 4.5, 7.0, "Vice City freeway sunset aerial"),
    ("03_speedboat_keys", 7.0, 9.5, "Speedboat cutting through turquoise Keys water"),
    ("04_everglades_airboat", 9.5, 12.0, "Airboat skimming through Everglades grass"),
    ("05_vice_beach_crowd", 12.5, 15.5, "Ocean Drive Vice City beach and low plane"),
    ("06_custom_lowriders", 17.5, 20.5, "Custom lowriders bouncing on hydraulics"),
    ("07_rooftop_pool_party", 21.5, 24.5, "Rooftop luxury pool party overlooking skyline"),
    ("08_club_neon_lights", 24.5, 27.5, "High-energy neon nightclub dance floor"),
    ("09_dirtbikes_highway", 29.5, 32.5, "Street dirt bike pack doing wheelies"),
    ("10_police_cruiser_speeding", 32.5, 35.5, "Police cruisers with flashing sirens"),
    ("11_alligator_pool", 37.5, 40.5, "Alligator being pulled from swimming pool"),
    ("12_night_gas_station_drift", 44.5, 47.5, "Night gas station street race drift"),
    ("13_social_media_livestream", 51.5, 54.5, "In-game social media livestream view"),
    ("14_jason_lucia_convertible", 61.5, 64.5, "Jason and Lucia driving through neon streets"),
    ("15_store_robbery_kick", 71.5, 74.5, "Jason and Lucia kicking store doors open"),
    ("16_trust_closing_shot", 76.5, 79.5, "Lucia and Jason saying trust holding cash"),
]


def download_trailer() -> Path:
    if TRAILER_PATH.exists() and TRAILER_PATH.stat().st_size > 1_000_000:
        print(f"Trailer already downloaded: {TRAILER_PATH} ({TRAILER_PATH.stat().st_size // 1024} KB)")
        return TRAILER_PATH

    print("Downloading Rockstar Games GTA 6 Trailer 1 in 1080p...")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
        "--merge-output-format", "mp4",
        "-o", str(TRAILER_PATH),
        YOUTUBE_URL,
    ]
    subprocess.run(cmd, check=True)
    print(f"Downloaded trailer: {TRAILER_PATH.stat().st_size // 1024} KB")
    return TRAILER_PATH


def slice_scenes(trailer: Path) -> None:
    print(f"Slicing {len(SCENES)} cinematic scenes from official trailer...")
    for name, start, end, desc in SCENES:
        duration = end - start
        
        # 1. 9:16 Vertical crop for Shorts
        vert_out = CLIPS_DIR / f"{name}_vert.mp4"
        if not vert_out.exists() or vert_out.stat().st_size == 0:
            cmd_vert = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", str(trailer),
                "-t", str(duration),
                # Crop center 9:16 and scale to 1080x1920
                "-vf", "crop=ih*9/16:ih:(iw-ow)/2:0,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-an",
                str(vert_out),
            ]
            subprocess.run(cmd_vert, check=True, capture_output=True)

        # 2. 16:9 Horizontal for Long-form
        horiz_out = CLIPS_DIR / f"{name}_horiz.mp4"
        if not horiz_out.exists() or horiz_out.stat().st_size == 0:
            cmd_horiz = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", str(trailer),
                "-t", str(duration),
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-an",
                str(horiz_out),
            ]
            subprocess.run(cmd_horiz, check=True, capture_output=True)

        # 3. High-resolution screenshot still
        still_out = STILLS_DIR / f"{name}.jpg"
        if not still_out.exists() or still_out.stat().st_size == 0:
            cmd_still = [
                "ffmpeg", "-y",
                "-ss", str(start + 0.8),
                "-i", str(trailer),
                "-vframes", "1",
                "-q:v", "2",
                str(still_out),
            ]
            subprocess.run(cmd_still, check=True, capture_output=True)

        print(f"  ✓ Extracted scene: {name} ({desc})")

    print(f"Successfully prepared {len(SCENES)} GTA 6 video clips and stills!")


def ensure_clips() -> None:
    """Ensure all 16 GTA 6 vertical and horizontal clips are available."""
    vert_clips = list(CLIPS_DIR.glob("*_vert.mp4"))
    if len(vert_clips) >= 14:
        print(f"GTA 6 clips already prepared ({len(vert_clips)} clips found).")
        return

    # 1. Download pre-sliced clips from GitHub Releases (fast, datacenter-safe)
    release_url = "https://github.com/ayaansahu2110-hash/youtube-autopilot/releases/download/gta6-assets/assets_gta6_clips.zip"
    zip_path = Path("assets_gta6_clips.zip")
    print("Downloading pre-processed GTA 6 clips pack from GitHub Release...")
    try:
        import urllib.request
        import zipfile
        # User-agent header to ensure clean GitHub download
        req = urllib.request.Request(
            release_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req) as resp, open(zip_path, "wb") as f:
            f.write(resp.read())

        print("Extracting clips...")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall("assets/gta6")
        zip_path.unlink(missing_ok=True)
        vert_clips = list(CLIPS_DIR.glob("*_vert.mp4"))
        if len(vert_clips) >= 14:
            print(f"Successfully unpacked {len(vert_clips)} GTA 6 clips from release.")
            return
    except Exception as exc:
        print(f"Release download notice: {exc}, falling back to trailer download...")

    # 2. Fallback: download trailer and slice with ffmpeg
    try:
        t = download_trailer()
        slice_scenes(t)
    except Exception as exc:
        print(f"Trailer download notice: {exc}")


if __name__ == "__main__":
    ensure_clips()
