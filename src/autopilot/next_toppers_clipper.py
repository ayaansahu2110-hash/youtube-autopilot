"""Automated Next Toppers Trio (Prashant Kirad, Shobhit Nirwan, Digraj Singh Rajput) Shorts Clipper.

Fetches fresh videos from official creator channels (and optional reference channels),
cuts high-retention vertical Shorts via ClipForge (OpusClip engine) with Hinglish captions,
full-color emojis, BGM mixing, aesthetic color grading, and @handle watermark,
and optionally publishes them to YouTube via YouTubeUploader.
"""

from __future__ import annotations

import json
import logging
import random
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from autopilot.config import Settings
from autopilot.models import VideoPlan
from autopilot.providers.clipflow import ClipflowProvider
from autopilot.youtube import YouTubeUploader

logger = logging.getLogger(__name__)

# Official Next Toppers Trio & Vlog channels (highest-quality raw footage + spoken hooks)
DEFAULT_SOURCE_CHANNELS: list[dict[str, str]] = [
    {"id": "UCgoyBmLOMNWmsiVkj-MezyQ", "name": "Prashant Kirad (ExpHub)", "handle": "@ExpHub"},
    {"id": "UCdeH0IQxtPy1XKvbb8Kwgqg", "name": "Shobhit Nirwan", "handle": "@ShobhitNirwan17"},
    {"id": "UCFYE2GR8F1YlKLQ3F7bvY9Q", "name": "Digraj Singh Rajput", "handle": "@DigrajSinghRajput214"},
    {"id": "UCJGA6mvd7jIb-6YmzKFlrow", "name": "Prashant Kirad Vlogs", "handle": "@PrashantKiradvlogs"},
    {"id": "UC6k0UlWg59GNng1T-3X71DA", "name": "Next Toppers Official", "handle": "@NextToppers23"},
]

# Viral student-relatable Hinglish hook templates modeled after top-performing Trio Shorts
AESTHETIC_MEME_HOOKS: list[dict[str, str]] = [
    {
        "top": "KUCH LOGO KO MERI KHUSHI ACHI NHI LGTI 😭🥀",
        "bottom": "JB BHI HOTA FIELDING SET HO JATI HAI 💀🔥",
        "title": "Kuch logo ko meri khushi achi nhi lgti 😭🥀 #nexttoppers #prashantkirad #viral #ytshorts",
        "layout": "letterbox-meme",
        "mood": "funny",
    },
    {
        "top": "",
        "bottom": "",
        "center": "🗣️ He doesn't look good!! ➡️ 👑🔥",
        "title": "Watch the comeback 😮‍💨🔥 #nexttoppers @ExpHub #prashantkirad #class10 #viral #ytshorts",
        "layout": "letterbox-dark",
        "mood": "motivational",
    },
    {
        "top": "",
        "bottom": "",
        "center": "How I came for live class,\nAnd ended up focusing on Kirad jii instead 🫠💓",
        "title": "Kirad jii & Trio supremacy 🫠🫶 #nexttoppers @ExpHub #prashantkirad #viral #ytshorts",
        "layout": "letterbox-dark",
        "mood": "emotional",
    },
    {
        "top": "Jab 10th Boards Paas Aaye 😭📚",
        "bottom": "Aur Sir Bole: Abhi Bhi 95% Possible Hai 🔥⚡",
        "title": "Boards me 95% comeback plan 🔥📚 @ShobhitNirwan17 @DigrajSinghRajput214 #nexttoppers #ytshorts",
        "layout": "letterbox-meme",
        "mood": "motivational",
    },
    {
        "top": "Top 1% Teacher Trio For A Reason 👑🔥",
        "bottom": "Wait For The Last Reaction 😭💀",
        "title": "Wait for the Trio reaction 😭🔥 @NextToppers23 @ExpHub #shobhitnirwan #digrajsir #ytshorts",
        "layout": "letterbox-meme",
        "mood": "funny",
    },
]

SPEECH_TOP_HOOKS: list[str] = [
    "Har Student Ko Yeh Sunna Chahiye 🔥🎯",
    "Last 60 Days Comeback Formula ⚡📚",
    "Middle Class Student Ki Reality 😭🥀",
    "Toppers Yeh Galti Kabhi Nhi Krte 💀🔥",
    "Prashant & Shobhit Bhaiya Real Advice 👑💯",
]


def _pick_bgm(mood: str, bgm_dir: Path) -> Path | None:
    mood_map = {
        "motivational": "bgm_motivational_phonk.mp3",
        "emotional": "bgm_emotional_lofi.mp3",
        "funny": "bgm_energetic_upbeat.mp3",
        "aesthetic": "bgm_emotional_lofi.mp3",
    }
    candidate = bgm_dir / mood_map.get(mood, "bgm_motivational_phonk.mp3")
    if candidate.exists():
        return candidate
    any_mp3 = sorted(bgm_dir.glob("*.mp3"))
    return any_mp3[0] if any_mp3 else None


def _yt_dlp_bin() -> str:
    venv_bin = Path(r"E:\youtube-autopilot\.venv\Scripts\yt-dlp.exe")
    return str(venv_bin) if venv_bin.exists() else "yt-dlp"


def fetch_channel_candidates(channel_ids: list[str], limit_per_channel: int = 8) -> list[dict]:
    """Fetch recent long videos / vlogs / shorts from target YouTube channels via yt-dlp."""
    yt_dlp = _yt_dlp_bin()
    results: list[dict] = []
    for cid in channel_ids:
        cid_clean = cid.strip()
        if not cid_clean:
            continue
        base_url = (
            cid_clean
            if cid_clean.startswith("http")
            else f"https://www.youtube.com/channel/{cid_clean}/videos"
            if cid_clean.startswith("UC")
            else f"https://www.youtube.com/{cid_clean}/videos"
        )
        proc = subprocess.run(
            [yt_dlp, "--flat-playlist", "--dump-single-json", "--playlist-end", str(limit_per_channel), base_url],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            continue
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            continue
        ch_name = data.get("channel") or data.get("title") or cid_clean
        for entry in data.get("entries") or []:
            vid = entry.get("id")
            if not vid:
                continue
            results.append(
                {
                    "video_id": vid,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "title": entry.get("title") or "",
                    "duration": float(entry.get("duration") or 0),
                    "views": int(entry.get("view_count") or 0),
                    "channel_id": cid_clean,
                    "channel_name": ch_name,
                }
            )
    return results


class NextToppersTrioPipeline:
    """End-to-end automated pipeline for Next Toppers Trio viral Shorts."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        source_channel_ids: list[str] | None = None,
        watermark: str = "@NextToppersClips",
    ):
        self.settings = settings or Settings(
            channel_profile="nexttoppers",
            channel_display_name="NextToppersClips",
            youtube_token_file=Path("secrets/youtube_token_nexttoppers.json"),
        )
        self.source_channel_ids = source_channel_ids or [c["id"] for c in DEFAULT_SOURCE_CHANNELS]
        self.watermark = watermark
        self.state_dir = Path("state/nexttoppers").resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.state_dir / "clip_history.json"
        self.artifacts_dir = Path(self.settings.artifacts_dir).resolve()
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.bgm_dir = Path(__file__).resolve().parents[2] / "assets" / "bgm"
        self.clipflow = ClipflowProvider(
            base_url=self.settings.clipflow_base_url,
            api_key=self.settings.clipflow_api_key,
            enabled=self.settings.clipflow_enabled,
        )

    def _load_history(self) -> dict:
        if self.history_file.exists():
            try:
                return json.loads(self.history_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"processed_sources": [], "produced_clips": []}

    def _save_history(self, data: dict) -> None:
        self.history_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def run_batch(
        self,
        *,
        count: int = 2,
        style: str = "auto",  # 'auto' | 'speech' | 'meme' | 'both'
        video_url_override: str | None = None,
        upload: bool = False,
    ) -> list[dict]:
        """Select fresh source video(s), generate stylized Trio Shorts via ClipForge, and optionally upload."""
        history = self._load_history()
        used_ids = set(history.get("processed_sources", []))

        if video_url_override:
            candidates = [{"video_id": "manual", "url": video_url_override, "title": "Manual Trio Source", "duration": 600, "views": 0, "channel_name": "Manual"}]
        else:
            all_cands = fetch_channel_candidates(self.source_channel_ids, limit_per_channel=6)
            fresh = [c for c in all_cands if c["video_id"] not in used_ids and c["duration"] >= 45]
            if not fresh:
                fresh = [c for c in all_cands if c["duration"] >= 45]
            # Prioritize high-view / engaging videos
            fresh.sort(key=lambda x: x["views"], reverse=True)
            candidates = fresh

        if not candidates:
            raise RuntimeError("No eligible source videos found on Next Toppers Trio channels.")

        if not self.clipflow.is_available():
            raise RuntimeError(
                "ClipForge API server (127.0.0.1:4820) is not running. Start it with `npm run api` inside C:\\Users\\ayaan\\Desktop\\clone."
            )

        outputs: list[dict] = []
        source_idx = 0
        styles_cycle = ["speech", "meme"] if style in ("auto", "both") else [style]

        for i in range(count):
            src = candidates[source_idx % len(candidates)]
            source_idx += 1
            chosen_style = styles_cycle[i % len(styles_cycle)]

            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            clip_out_dir = self.artifacts_dir / f"{stamp}_{i+1}_{chosen_style}"
            clip_out_dir.mkdir(parents=True, exist_ok=True)

            if chosen_style == "meme":
                preset = AESTHETIC_MEME_HOOKS[(len(history.get("produced_clips", [])) + i) % len(AESTHETIC_MEME_HOOKS)]
                bgm = _pick_bgm(preset["mood"], self.bgm_dir)
                # Cut a vivid 15s segment around 25-45% of the video where peak gestures/smiles happen
                dur_ms = max(45000, int(src.get("duration", 300) * 1000))
                s_ms = min(dur_ms - 18000, int(dur_ms * (0.28 if i % 2 == 0 else 0.45)))
                e_ms = s_ms + 15500

                job = self.clipflow.clip_video(
                    video_url=src["url"],
                    aspect_ratio="9:16",
                    clip_count=1,
                    clip_duration_sec=15,
                    caption_preset="trio-hinglish",
                    resolution="1080p",
                    provider="mock",  # no ASR needed since original dialogue is muted & replaced with BGM
                    llm_provider="nvidia",
                    language="hinglish",
                    layout_mode=preset["layout"],
                    color_grade="viral-warm",
                    bgm_path=bgm,
                    bgm_volume=0.88,
                    mute_original=True,
                    speed_factor=0.90,
                    top_text=preset["top"],
                    bottom_text=preset["bottom"],
                    center_text=preset.get("center"),
                    watermark_text=self.watermark,
                    auto_emoji=True,
                    burn_captions=False,
                    start_ms=s_ms,
                    end_ms=e_ms,
                )
                yt_title = preset["title"][:100]
            else:
                bgm = _pick_bgm("motivational", self.bgm_dir)
                top_hook = SPEECH_TOP_HOOKS[(len(history.get("produced_clips", [])) + i) % len(SPEECH_TOP_HOOKS)]
                job = self.clipflow.clip_video(
                    video_url=src["url"],
                    aspect_ratio="9:16",
                    clip_count=1,
                    clip_duration_sec=24,
                    caption_preset="trio-hinglish",
                    resolution="1080p",
                    provider="gemini",
                    llm_provider="nvidia",
                    prompt=(
                        "Find the highest-energy motivational, emotional, or funny relatable punchline spoken by "
                        "Prashant Kirad, Shobhit Nirwan, or Digraj Singh Rajput for Class 9-12 students."
                    ),
                    language="hinglish",
                    layout_mode="fit-blur",
                    color_grade="viral-warm",
                    bgm_path=bgm,
                    bgm_volume=0.16,
                    mute_original=False,
                    speed_factor=1.0,
                    top_text=top_hook,
                    bottom_text="",  # Keep bottom free for animated ASS karaoke captions
                    watermark_text=self.watermark,
                    auto_emoji=True,
                    burn_captions=True,
                )
                out0 = (job or {}).get("outputs", [{}])[0]
                raw_title = out0.get("title") or top_hook
                em = out0.get("emoji") or "🔥"
                yt_title = f"{raw_title} {em} #nexttoppers #prashantkirad #viral #ytshorts"[:100]

            if not job or not job.get("outputs"):
                logger.warning(f"ClipForge did not produce outputs for {src['url']}")
                continue

            out0 = job["outputs"][0]
            src_mp4 = Path(out0["filePath"])
            final_mp4 = clip_out_dir / f"trio_{chosen_style}.mp4"
            if src_mp4.exists():
                final_mp4.write_bytes(src_mp4.read_bytes())

            desc = (
                f"{yt_title}\n\n"
                f"Credits & Original Creators:\n"
                f"@ExpHub @ShobhitNirwan17 @DigrajSinghRajput214 @NextToppers23 @PrashantKiradvlogs\n"
                f"Source: {src['url']}\n\n"
                f"#nexttoppers #prashantkirad #shobhitnirwan #digrajsinghrajput #class10 #class12 "
                f"#boards2027 #study #motivation #ytshorts #viral"
            )
            tags = [
                "next toppers",
                "prashant kirad",
                "shobhit nirwan",
                "digraj singh rajput",
                "exphub",
                "class 10",
                "study motivation",
                "shorts",
            ]
            meta_record = {
                "style": chosen_style,
                "source_video_id": src["video_id"],
                "source_url": src["url"],
                "title": yt_title,
                "description": desc,
                "tags": tags,
                "file_path": str(final_mp4),
                "duration_ms": out0.get("durationMs"),
                "score": out0.get("score"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "uploaded_video_id": None,
            }

            # Optional YouTube upload (only if token exists and upload=True)
            if upload:
                token_path = Path(self.settings.youtube_token_file)
                if token_path.exists():
                    uploader = YouTubeUploader(self.settings)
                    plan = VideoPlan(
                        topic=src["title"],
                        format="short",
                        title=yt_title,
                        description=desc,
                        tags=tags,
                        hook=yt_title,
                        script=out0.get("transcript") or yt_title,
                        cta="Subscribe for daily Next Toppers Trio edits!",
                        thumbnail_text=yt_title[:30],
                    )
                    upload_res = uploader.upload(final_mp4, plan, thumbnail_path=None)
                    meta_record["uploaded_video_id"] = upload_res.get("video_id")
                    meta_record["uploaded_url"] = upload_res.get("url")
                else:
                    logger.warning(f"Upload skipped: token missing at {token_path}. Video saved locally at {final_mp4}")

            (clip_out_dir / "metadata.json").write_text(json.dumps(meta_record, indent=2, ensure_ascii=False), encoding="utf-8")
            outputs.append(meta_record)

            if src["video_id"] != "manual" and src["video_id"] not in used_ids:
                history.setdefault("processed_sources", []).append(src["video_id"])
                used_ids.add(src["video_id"])
            history.setdefault("produced_clips", []).append(meta_record)
            self._save_history(history)

        return outputs
