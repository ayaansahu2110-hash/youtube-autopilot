"""Automated Next Toppers Trio (Prashant Kirad, Shobhit Nirwan, Digraj Singh Rajput) Comedy & Roasting Clipper.

Finds funny/roasting moments from:
  1. Official Next Toppers Trio live classes, meme-reaction videos, and streams
  2. Proven Next Toppers comedy/roasting clip & compilation channels on YouTube
  3. Live YouTube search for latest Prashant / Shobhit / Digraj funny & roasting clips

Verifies via OpenCV face detection that a teacher's face is clearly on screen (rejecting slides/animations),
auto-centers the crop on their face, applies the white rounded pill banner ("PK Bhaiya Roasting Day By Day 📈⚡"),
warm contrast polish, @handle watermark, Hinglish captions, and BGM, and optionally uploads to YouTube.
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import cv2

from autopilot.config import Settings
from autopilot.models import VideoPlan
from autopilot.providers.clipflow import ClipflowProvider
from autopilot.youtube import YouTubeUploader

logger = logging.getLogger(__name__)

# Official channels (live sessions + meme reaction videos + vlogs)
OFFICIAL_LIVE_CHANNELS: list[dict[str, str]] = [
    {"id": "UCgoyBmLOMNWmsiVkj-MezyQ", "name": "ExpHub (Prashant Kirad)", "handle": "@ExpHub"},
    {"id": "UCdeH0IQxtPy1XKvbb8Kwgqg", "name": "Shobhit Nirwan", "handle": "@ShobhitNirwan17"},
    {"id": "UCFYE2GR8F1YlKLQ3F7bvY9Q", "name": "Digraj Singh Rajput", "handle": "@DigrajSinghRajput214"},
    {"id": "UCJGA6mvd7jIb-6YmzKFlrow", "name": "Prashant Kirad Vlogs", "handle": "@PrashantKiradvlogs"},
    {"id": "UC6k0UlWg59GNng1T-3X71DA", "name": "Next Toppers Official", "handle": "@NextToppers23"},
]

# High-performing comedy & roasting clip/compilation channels found via YouTube research
COMEDY_CLIP_CHANNELS: list[dict[str, str]] = [
    {"id": "UCcRv4COoX94JIlBd8xuGbjA", "name": "NextTopper Harsh", "tab": "shorts"},
    {"id": "UCsxA17djxwN1lWVEawbX56g", "name": "Nexttoppers Hub", "tab": "videos"},
    {"id": "UCcsbHSRLQNcugDQwaUup-pA", "name": "Shobby ki Olivia", "tab": "videos"},
    {"id": "UCEB1A2-aK7ITZxu1ibq8v4Q", "name": "Next topper op", "tab": "videos"},
    {"id": "UC2Eun_8tVb5jheSIM9WYeig", "name": "NextToppers feels", "tab": "videos"},
    {"id": "UC-h6NNu_QgPijTTR5r5bgqw", "name": "DSP Moments", "tab": "videos"},
    {"id": "UCGM1myHrBasW_WuGX7fGrJQ", "name": "DSP GOAT Editz", "tab": "videos"},
    {"id": "UCe226-9kFQO3QkNGb_hBkow", "name": "Next toppers addict", "tab": "videos"},
]

ROAST_SEARCH_QUERIES: list[str] = [
    "Prashant Kirad roasting funny live class",
    "Shobhit Nirwan funny comedy roast",
    "Digraj Sir funny comedy class moments",
    "Next Toppers funny moments class",
]

PILL_HOOKS: list[dict[str, str]] = [
    {"pill": "PK Bhaiya Roasting Day By Day 📈⚡", "title": "PK Bhaiya Roasting Day By Day 📈🔥 #nexttoppers #prashantkirad #funny #roasting #ytshorts"},
    {"pill": "Wait For Bhaiya's Savage Reply 💀😂", "title": "Bhaiya's Savage Reply 💀😂 #nexttoppers @ExpHub #prashantkirad #comedy #ytshorts"},
    {"pill": "Next Toppers Live Class Comedy 😂⚡", "title": "Live Class Gone Funny 😂🔥 @ExpHub @ShobhitNirwan17 #nexttoppers #funny #ytshorts"},
    {"pill": "Shobhit & PK Bhaiya Hesitate Pls 😭💀", "title": "Bhaiya Please Hesitate 😭💀 @ShobhitNirwan17 @ExpHub #nexttoppers #roasting #ytshorts"},
    {"pill": "Digraj Sir Comedy Mode On 🤣👑", "title": "Digraj Sir Unexpected Comedy 🤣🔥 @DigrajSinghRajput214 #nexttoppers #funny #ytshorts"},
]


def _yt_dlp_bin() -> str:
    venv_bin = Path(r"E:\youtube-autopilot\.venv\Scripts\yt-dlp.exe")
    return str(venv_bin) if venv_bin.exists() else "yt-dlp"


def _pick_comedy_bgm(bgm_dir: Path) -> Path | None:
    for name in ("bgm_motivational_phonk.mp3", "bgm_energetic_upbeat.mp3"):
        p = bgm_dir / name
        if p.exists():
            return p
    return None


def verify_face_presence_and_center(video_path: Path, start_ms: int = 0, end_ms: int | None = None, sample_count: int = 8) -> tuple[float, float]:
    """Scan frames with OpenCV Haar cascade and return (face_ratio, avg_face_center_x)."""
    if not video_path.exists():
        return 0.0, 0.5
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(str(cascade_path))
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 0.0, 0.5

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        total_ms = (total_frames / fps) * 1000.0 if fps > 0 else 0
        s_ms = max(0.0, float(start_ms))
        e_ms = min(total_ms, float(end_ms)) if end_ms and total_ms > 0 else total_ms
        if e_ms <= s_ms:
            e_ms = total_ms

        hits = 0
        xs: list[float] = []
        steps = max(3, sample_count)
        for i in range(steps):
            t_ms = s_ms + ((e_ms - s_ms) * (i + 0.5) / steps)
            cap.set(cv2.CAP_PROP_POS_MSEC, t_ms)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            h, w = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=4, minSize=(42, 42))
            if len(faces) > 0:
                hits += 1
                fx, fy, fw, fh = max(faces, key=lambda b: b[2] * b[3])
                xs.append((fx + fw / 2.0) / max(1, w))

        ratio = hits / steps
        avg_x = sum(xs) / len(xs) if xs else 0.5
        return ratio, max(0.15, min(0.85, avg_x))
    finally:
        cap.release()


def find_best_face_window(video_path: Path, target_sec: float = 22.0, scan_step_sec: float = 20.0) -> tuple[int, int, float, float]:
    """Scan a downloaded compilation/live video to pick a window where teacher's face is clearly visible."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 0, int(target_sec * 1000), 0.0, 0.5
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur_sec = total_frames / fps if fps > 0 else 60.0
    cap.release()

    if dur_sec <= target_sec + 5:
        r, cx = verify_face_presence_and_center(video_path, 0, int(dur_sec * 1000), sample_count=8)
        return 0, int(min(dur_sec, target_sec) * 1000), r, cx

    best = (0, int(target_sec * 1000), 0.0, 0.5)
    t = 12.0
    checked = 0
    while t + target_sec < dur_sec - 2.0 and checked < 5:
        s_ms = int(t * 1000)
        e_ms = int((t + target_sec) * 1000)
        ratio, cx = verify_face_presence_and_center(video_path, s_ms, e_ms, sample_count=5)
        checked += 1
        if ratio > best[2]:
            best = (s_ms, e_ms, ratio, cx)
        if ratio >= 0.70:
            return s_ms, e_ms, ratio, cx
        t += max(scan_step_sec, dur_sec / 6.0)
    return best


def fetch_comedy_candidates(
    source_channel_ids: list[str] | None = None,
    limit_per_source: int = 6,
    include_live_search: bool = True,
) -> list[dict]:
    """Discover funny/roasting videos from curated comedy channels, live streams, and YouTube search."""
    yt_dlp = _yt_dlp_bin()
    urls_to_fetch: list[tuple[str, str]] = []

    if source_channel_ids:
        for cid in source_channel_ids:
            c = cid.strip()
            if c.startswith("http"):
                urls_to_fetch.append((c, c))
            elif c.startswith("UC"):
                urls_to_fetch.append((f"https://www.youtube.com/channel/{c}/shorts", c))
                urls_to_fetch.append((f"https://www.youtube.com/channel/{c}/videos", c))
            else:
                urls_to_fetch.append((f"https://www.youtube.com/{c}/videos", c))
    else:
        for ch in COMEDY_CLIP_CHANNELS:
            urls_to_fetch.append((f"https://www.youtube.com/channel/{ch['id']}/{ch['tab']}", ch["name"]))
        for ch in OFFICIAL_LIVE_CHANNELS:
            urls_to_fetch.append((f"https://www.youtube.com/channel/{ch['id']}/streams", ch["name"]))
            urls_to_fetch.append((f"https://www.youtube.com/channel/{ch['id']}/videos", ch["name"]))

    if include_live_search:
        for q in ROAST_SEARCH_QUERIES:
            urls_to_fetch.append((f"ytsearch8:{q}", f"search:{q}"))

    seen_ids: set[str] = set()
    results: list[dict] = []
    funny_keywords = ("roast", "funny", "comedy", "meme", "react", "hesitate", "dark", "chaotic", "laugh", "shayari", "masti")

    for url, label in urls_to_fetch:
        proc = subprocess.run(
            [yt_dlp, "--flat-playlist", "--dump-single-json", "--playlist-end", str(limit_per_source), url],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            continue
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            continue
        for entry in data.get("entries") or []:
            vid = entry.get("id")
            if not vid or vid in seen_ids:
                continue
            seen_ids.add(vid)
            title = entry.get("title") or ""
            dur = float(entry.get("duration") or 0)
            views = int(entry.get("view_count") or 0)
            low = title.lower()
            is_short_remix = "/shorts" in url or (12 <= dur <= 70)
            is_comedy_title = any(k in low for k in funny_keywords)
            priority_score = views + (500_000 if is_comedy_title else 0) + (150_000 if "roast" in low or "funny" in low else 0)
            results.append(
                {
                    "video_id": vid,
                    "url": f"https://www.youtube.com/shorts/{vid}" if is_short_remix else f"https://www.youtube.com/watch?v={vid}",
                    "title": title,
                    "duration": dur,
                    "views": views,
                    "source_label": label,
                    "is_short_remix": is_short_remix,
                    "is_comedy_title": is_comedy_title,
                    "priority_score": priority_score,
                }
            )

    results.sort(key=lambda x: x["priority_score"], reverse=True)
    return results


class NextToppersTrioPipeline:
    """Automated pipeline for Next Toppers Trio face-focused comedy & roasting Shorts."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        source_channel_ids: list[str] | None = None,
        watermark: str = "@NextToppersRoast",
    ):
        self.settings = settings or Settings(
            channel_profile="nexttoppers",
            channel_display_name="NextToppersClips",
            youtube_token_file=Path("secrets/youtube_token_nexttoppers.json"),
        )
        self.source_channel_ids = source_channel_ids
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

    def _download_to_cache(self, url: str, video_id: str) -> Path | None:
        cache_dir = Path(r"D:\ClipForgeData\renders\url_cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / f"yt_{video_id}.mp4"
        if cached.exists() and cached.stat().st_size > 20000:
            return cached
        yt_dlp = _yt_dlp_bin()
        proc = subprocess.run(
            [
                yt_dlp,
                "--no-playlist",
                "--no-part",
                "--js-runtimes", "node",
                "--merge-output-format", "mp4",
                "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/mp4/best",
                "-o", str(cached),
                url,
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and cached.exists() and cached.stat().st_size > 20000:
            return cached
        return None

    def run_batch(
        self,
        *,
        count: int = 2,
        style: str = "auto",  # 'auto' | 'roast-live' | 'roast-remix' | 'both'
        video_url_override: str | None = None,
        upload: bool = False,
    ) -> list[dict]:
        """Find face-verified comedy/roasting moments, render Shorts via ClipForge, and optionally upload."""
        history = self._load_history()
        used_ids = set(history.get("processed_sources", []))

        if video_url_override:
            vid = video_url_override.split("v=")[-1].split("/shorts/")[-1].split("?")[0][:11]
            candidates = [{
                "video_id": vid or "manual",
                "url": video_url_override,
                "title": "Manual Comedy Source",
                "duration": 0,
                "views": 0,
                "is_short_remix": "/shorts/" in video_url_override,
                "is_comedy_title": True,
            }]
        else:
            all_cands = fetch_comedy_candidates(self.source_channel_ids, limit_per_source=6, include_live_search=True)
            fresh = [c for c in all_cands if c["video_id"] not in used_ids]
            candidates = fresh if fresh else all_cands

        if not candidates:
            raise RuntimeError("No comedy/roasting source videos found.")
        if not self.clipflow.is_available():
            raise RuntimeError("ClipForge API server (127.0.0.1:4820) is not running.")

        outputs: list[dict] = []
        bgm = _pick_comedy_bgm(self.bgm_dir)
        cand_cursor = 0

        for i in range(count):
            chosen_output = None
            attempts = 0
            while cand_cursor < len(candidates) and attempts < 8:
                src = candidates[cand_cursor]
                cand_cursor += 1
                attempts += 1

                local_src = self._download_to_cache(src["url"], src["video_id"])
                if not local_src:
                    continue

                is_remix = (style == "roast-remix") or (style in ("auto", "both") and src.get("is_short_remix"))
                if is_remix:
                    face_ratio, face_cx = verify_face_presence_and_center(local_src, 0, None, sample_count=8)
                    if face_ratio < 0.60:
                        logger.info(f"Skipping {src['video_id']} (face_ratio={face_ratio:.2f} < 0.60)")
                        continue
                    s_ms, e_ms = None, None
                else:
                    s_ms, e_ms, face_ratio, face_cx = find_best_face_window(local_src, target_sec=24.0, scan_step_sec=25.0)
                    if face_ratio < 0.60:
                        logger.info(f"Skipping {src['video_id']} (no clear face window found: {face_ratio:.2f})")
                        continue

                hook_cfg = PILL_HOOKS[(len(history.get("produced_clips", [])) + i) % len(PILL_HOOKS)]
                chosen_style = "roast-remix" if is_remix else "roast-live"

                if is_remix:
                    probe = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(local_src)],
                        capture_output=True, text=True,
                    )
                    dur_ms = int(min(58.0, float(probe.stdout.strip() or 25.0)) * 1000)
                    job = self.clipflow.clip_video(
                        file_path=local_src,
                        aspect_ratio="9:16",
                        clip_count=1,
                        clip_duration_sec=max(10, dur_ms // 1000),
                        caption_preset="trio-hinglish",
                        resolution="1080p",
                        provider="mock",
                        llm_provider="nvidia",
                        language="hinglish",
                        layout_mode="face-zoom",
                        color_grade="viral-warm",
                        crop_offset_x=face_cx,
                        bgm_path=bgm,
                        bgm_volume=0.10,
                        mute_original=False,
                        speed_factor=1.02,
                        top_text=hook_cfg["pill"],
                        top_pill=True,
                        watermark_text=self.watermark,
                        auto_emoji=False,
                        burn_captions=False,
                        start_ms=0,
                        end_ms=dur_ms,
                    )
                else:
                    job = self.clipflow.clip_video(
                        file_path=local_src,
                        aspect_ratio="9:16",
                        clip_count=1,
                        clip_duration_sec=24,
                        caption_preset="trio-hinglish",
                        resolution="1080p",
                        provider="gemini",
                        llm_provider="nvidia",
                        prompt=(
                            "Cut the funniest comedy joke, student roast, or savage comeback spoken by "
                            "Prashant Kirad, Shobhit Nirwan, or Digraj Sir. Keep their dialogue crisp."
                        ),
                        language="hinglish",
                        layout_mode="face-zoom",
                        color_grade="viral-warm",
                        crop_offset_x=face_cx,
                        bgm_path=bgm,
                        bgm_volume=0.12,
                        mute_original=False,
                        speed_factor=1.0,
                        top_text=hook_cfg["pill"],
                        top_pill=True,
                        watermark_text=self.watermark,
                        auto_emoji=False,
                        burn_captions=True,
                        start_ms=s_ms,
                        end_ms=e_ms,
                    )

                if job and job.get("outputs"):
                    chosen_output = (src, chosen_style, hook_cfg, face_ratio, job["outputs"][0])
                    break

            if not chosen_output:
                continue

            src, chosen_style, hook_cfg, face_ratio, out0 = chosen_output
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            clip_out_dir = self.artifacts_dir / f"{stamp}_{i+1}_{chosen_style}"
            clip_out_dir.mkdir(parents=True, exist_ok=True)

            src_mp4 = Path(out0["filePath"])
            final_mp4 = clip_out_dir / f"{chosen_style}.mp4"
            if src_mp4.exists():
                final_mp4.write_bytes(src_mp4.read_bytes())

            yt_title = hook_cfg["title"][:100]
            desc = (
                f"{yt_title}\n\n"
                f"Credits & Original Channels:\n"
                f"@ExpHub @ShobhitNirwan17 @DigrajSinghRajput214 @NextToppers23 @PrashantKiradvlogs\n"
                f"Source: {src['url']}\n\n"
                f"#nexttoppers #prashantkirad #shobhitnirwan #digrajsinghrajput "
                f"#roasting #comedy #funny #class10 #studentlife #ytshorts #viral"
            )
            tags = [
                "next toppers",
                "prashant kirad roasting",
                "shobhit nirwan funny",
                "digraj sir comedy",
                "next toppers comedy",
                "class 10 funny",
                "shorts",
            ]
            meta_record = {
                "style": chosen_style,
                "face_coverage": round(face_ratio, 2),
                "source_video_id": src["video_id"],
                "source_url": src["url"],
                "source_title": src["title"],
                "title": yt_title,
                "description": desc,
                "tags": tags,
                "file_path": str(final_mp4),
                "duration_ms": out0.get("durationMs"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "uploaded_video_id": None,
            }

            if upload:
                token_path = Path(self.settings.youtube_token_file)
                if token_path.exists():
                    uploader = YouTubeUploader(self.settings)
                    plan = VideoPlan(
                        topic=src["title"] or yt_title,
                        format="short",
                        title=yt_title,
                        description=desc,
                        tags=tags,
                        hook=hook_cfg["pill"],
                        script=out0.get("transcript") or yt_title,
                        cta="Subscribe for daily Prashant, Shobhit & Digraj comedy & roast clips!",
                        thumbnail_text=hook_cfg["pill"][:30],
                    )
                    upload_res = uploader.upload(final_mp4, plan, thumbnail_path=None)
                    meta_record["uploaded_video_id"] = upload_res.get("video_id")
                    meta_record["uploaded_url"] = upload_res.get("url")
                else:
                    logger.warning(f"Upload skipped: authorize token first for {token_path}")

            (clip_out_dir / "metadata.json").write_text(json.dumps(meta_record, indent=2, ensure_ascii=False), encoding="utf-8")
            outputs.append(meta_record)

            if src["video_id"] not in used_ids:
                history.setdefault("processed_sources", []).append(src["video_id"])
                used_ids.add(src["video_id"])
            history.setdefault("produced_clips", []).append(meta_record)
            self._save_history(history)

        return outputs
