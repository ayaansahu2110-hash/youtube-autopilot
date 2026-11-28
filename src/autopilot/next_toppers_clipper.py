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
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
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

# High-performing comedy & roasting Shorts + compilation channels found via YouTube research
COMEDY_CLIP_CHANNELS: list[dict[str, str]] = [
    {"id": "UCcRv4COoX94JIlBd8xuGbjA", "name": "NextTopper Harsh", "tab": "shorts"},
    {"id": "UCsxA17djxwN1lWVEawbX56g", "name": "Nexttoppers Hub Shorts", "tab": "shorts"},
    {"id": "UCsxA17djxwN1lWVEawbX56g", "name": "Nexttoppers Hub", "tab": "videos"},
    {"id": "UCcsbHSRLQNcugDQwaUup-pA", "name": "Shobby ki Olivia Shorts", "tab": "shorts"},
    {"id": "UCEB1A2-aK7ITZxu1ibq8v4Q", "name": "Next topper op Shorts", "tab": "shorts"},
    {"id": "UCe226-9kFQO3QkNGb_hBkow", "name": "Next toppers addict Shorts", "tab": "shorts"},
]

ROAST_SEARCH_QUERIES: list[str] = [
    "PK Bhaiya Roasting Day By Day shorts",
    "When Class Gets Dark prashant kirad shorts",
    "next toppers dark comedy roasting shorts",
    "prashant kirad shobhit nirwan roasting shorts",
    "digraj sir dark comedy funny shorts",
]

EXCLUDED_LECTURE_KEYWORDS: tuple[str, ...] = (
    "one shot",
    "complete chapter",
    "full revision",
    "sample paper solution",
    "ncert exercise",
    "most important questions marathon",
)

MIN_PREFERRED_VIEWS = 50_000

PILL_HOOKS: list[dict[str, str]] = [
    {"pill": "PK Bhaiya Roasting Day By Day 📈⚡", "title": "PK Bhaiya Roasting Day By Day 📈⚡ #nexttoppers #prashantkirad #funny #relatable #studentlife #2026"},
    {"pill": "When Class Gets Dark 😜🌚", "title": "When Class Gets Dark 😜🌚 #nexttoppers #prashantkirad #dark #funny #memes #students #2026"},
    {"pill": "Wait For Bhaiya's Savage Reply 💀😂", "title": "PK Bhaiya Roasting Day By Day 📈⚡ #prashantkirad #nexttoppers #funny #roasting #studentlife #2026"},
    {"pill": "Shobhit & PK Bhaiya Hesitate Pls 😭💀", "title": "When Class Gets Dark 😜🌚 #nexttoppers #shobhitnirwan #prashantkirad #funny #relatable #2026"},
    {"pill": "Digraj Sir Comedy Mode On 🤣👑", "title": "Digraj Sir Unexpected Comedy 🤣🔥 #nexttoppers #digrajsinghrajput #funny #studentlife #2026"},
]

TILE_REACTIONS: list[tuple[str, str]] = [
    ("Bhaiya roasting day by day 🫣", "🤣"),
    ("Chhod do bhaiya hmm smjh gaye 💀", "💀"),
    ("Bhaiya thoda control karo 😅", "🤣"),
    ("No hesitation mode on 🔥", "😭"),
    ("Sir ne toh roast kar diya 😭", "💀"),
    ("Class dark ho gayi bhai 🌚", "🤣"),
]


ZOOM_CONFERENCE_IDS: set[str] = {"MGH5bp-bESQ", "LWo0qmF41l0", "Ziz-2Hh3eVU"}


def _yt_dlp_bin() -> str:
    venv_bin = Path(r"E:\youtube-autopilot\.venv\Scripts\yt-dlp.exe")
    if os.name == "nt" and venv_bin.exists():
        return str(venv_bin)
    return shutil.which("yt-dlp") or "yt-dlp"


def _resolve_render_overlay_script() -> Path:
    candidates = [
        Path(__file__).resolve().parents[2] / "scripts" / "render_overlay.py",
        Path(os.environ.get("CLIPFORGE_HOME", r"E:\ClipForge")) / "scripts" / "render_overlay.py",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError("Missing scripts/render_overlay.py in repository or CLIPFORGE_HOME")


def _avg_face_width_frac(video_path: Path, start_ms: int = 0, end_ms: int | None = None, sample_count: int = 5) -> float:
    """Measure average largest face bounding width relative to frame width (rejects tiny Zoom webcams)."""
    if not video_path.exists():
        return 0.0
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(str(cascade_path))
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 0.0
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_ms = (int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps) * 1000.0 if fps > 0 else 0.0
        s_ms = max(0.0, float(start_ms))
        e_ms = min(total_ms, float(end_ms)) if end_ms and total_ms > 0 else total_ms
        if e_ms <= s_ms:
            e_ms = total_ms
        widths: list[float] = []
        for i in range(max(3, sample_count)):
            cap.set(cv2.CAP_PROP_POS_MSEC, s_ms + ((e_ms - s_ms) * (i + 0.5) / max(3, sample_count)))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            w = frame.shape[1] or 1280
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=4, minSize=(42, 42))
            if len(faces) > 0:
                _, _, fw, _ = max(faces, key=lambda b: b[2] * b[3])
                widths.append(fw / max(1, w))
        return sum(widths) / len(widths) if widths else 0.0
    finally:
        cap.release()


def _face_focus_box(
    video_path: Path, start_ms: int = 0, end_ms: int | None = None, sample_count: int = 6
) -> tuple[float, float, float]:
    """Return (avg_cx, avg_cy, avg_w_frac) of the largest detected face for tight square/portrait framing."""
    if not video_path.exists():
        return 0.5, 0.42, 0.0
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(str(cascade_path))
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 0.5, 0.42, 0.0
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_ms = (int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps) * 1000.0 if fps > 0 else 0.0
        s_ms = max(0.0, float(start_ms))
        e_ms = min(total_ms, float(end_ms)) if end_ms and total_ms > 0 else total_ms
        if e_ms <= s_ms:
            e_ms = total_ms
        xs, ys, ws = [], [], []
        steps = max(3, sample_count)
        for i in range(steps):
            cap.set(cv2.CAP_PROP_POS_MSEC, s_ms + ((e_ms - s_ms) * (i + 0.5) / steps))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            h, w = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=4, minSize=(42, 42))
            if len(faces) > 0:
                fx, fy, fw, fh = max(faces, key=lambda b: b[2] * b[3])
                xs.append((fx + fw / 2.0) / max(1, w))
                ys.append((fy + fh * 0.65) / max(1, h))
                ws.append(fw / max(1, w))
        cx = max(0.16, min(0.84, sum(xs) / len(xs))) if xs else 0.5
        cy = max(0.25, min(0.68, sum(ys) / len(ys))) if ys else 0.42
        wf = sum(ws) / len(ws) if ws else 0.0
        return cx, cy, wf
    finally:
        cap.release()


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


def _fetch_heatmap_peaks(url: str, max_peaks: int = 3) -> list[tuple[float, float]]:
    """Query YouTube Most-Replayed heatmap peaks for a video so we jump straight to viral comedy moments."""
    yt_dlp = _yt_dlp_bin()
    proc = subprocess.run(
        [
            yt_dlp,
            "--dump-single-json",
            "--no-playlist",
            "--js-runtimes", "node",
            "--remote-components", "ejs:github",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    hm = data.get("heatmap") or []
    if not hm:
        return []
    ranked = sorted(hm, key=lambda x: float(x.get("value") or 0.0), reverse=True)
    selected: list[tuple[float, float]] = []
    for seg in ranked:
        st = float(seg.get("start_time") or 0.0)
        et = float(seg.get("end_time") or st + 15.0)
        # Skip 0-2s intro replay spike on Shorts
        if st < 3.0 and (et - st) < 5.0:
            continue
        if all(abs(st - prev_s) > 20.0 for prev_s, _ in selected):
            selected.append((st, et))
        if len(selected) >= max_peaks:
            break
    return selected


def find_best_face_window(
    video_path: Path,
    target_sec: float = 24.0,
    scan_step_sec: float = 20.0,
    preferred_peaks: list[tuple[float, float]] | None = None,
) -> tuple[int, int, float, float]:
    """Pick the funniest/most-replayed window where teacher's face is clearly visible on screen."""
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

    # First check YouTube Most-Replayed viewer peaks (these pinpoint the actual joke/roast)
    for pk_start, _ in (preferred_peaks or []):
        start_s = max(0.0, min(dur_sec - target_sec - 1.0, pk_start - 3.0))
        s_ms = int(start_s * 1000)
        e_ms = int((start_s + target_sec) * 1000)
        ratio, cx = verify_face_presence_and_center(video_path, s_ms, e_ms, sample_count=6)
        if ratio > best[2]:
            best = (s_ms, e_ms, ratio, cx)
        if ratio >= 0.65:
            return s_ms, e_ms, ratio, cx

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
    limit_per_source: int = 8,
    include_live_search: bool = True,
) -> list[dict]:
    """Discover high-view funny/roasting videos from curated channels, official roasts, and YouTube search."""
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
        # Keep official horizontal videos only as secondary sources for 2x2 collages
        for ch in OFFICIAL_LIVE_CHANNELS[:3]:
            urls_to_fetch.append((f"https://www.youtube.com/channel/{ch['id']}/videos", ch["name"]))

    if include_live_search:
        for q in ROAST_SEARCH_QUERIES:
            urls_to_fetch.append((f"ytsearch12:{q}", f"search:{q}"))

    seen_ids: set[str] = set()
    results: list[dict] = []
    funny_keywords = (
        "roast", "funny", "comedy", "meme", "react", "hesitate",
        "dark", "exposed", "prank", "reply", "angry", "abused", "laugh",
        "dhokebaaz", "challenge", "practical", "scaring", "olivia", "masti",
    )

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
            is_comedy_title = any(k in low for k in funny_keywords)
            # Only allow verified comedy/roast/exposed/funny titles (skip unrelated vlogs/hair/money/lectures)
            if not is_comedy_title:
                continue
            if any(bad in low for bad in EXCLUDED_LECTURE_KEYWORDS):
                continue
            is_short_remix = "/shorts" in url or (12 <= dur <= 70)
            # Strongly prioritize already-trending viral Shorts (high views + dark/roast comedy)
            viral_boost = 1.6 if ("roast" in low or "dark" in low or "exposed" in low or "prank" in low) else 1.2
            shorts_bonus = 600_000 if (is_short_remix and views >= MIN_PREFERRED_VIEWS) else 0
            priority_score = int(views * viral_boost) + shorts_bonus + (50_000 if is_comedy_title else 0)
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

    # Prefer genuinely viral videos (>= MIN_PREFERRED_VIEWS) first before lower-view fallback
    viral = [r for r in results if r["views"] >= MIN_PREFERRED_VIEWS]
    rest = [r for r in results if r["views"] < MIN_PREFERRED_VIEWS]
    viral.sort(key=lambda x: x["priority_score"], reverse=True)
    rest.sort(key=lambda x: x["priority_score"], reverse=True)
    return viral + rest


COLLAGE_HOOKS: list[dict[str, str]] = [
    {"pill": "PK Bhaiya Roasting Day By Day 📈⚡", "title": "PK Bhaiya Roasting Day By Day 📈⚡ #nexttoppers #prashantkirad #funny #relatable #studentlife #2026"},
    {"pill": "When Class Gets Dark 😜🌚", "title": "When Class Gets Dark 😜🌚 #nexttoppers #prashantkirad #dark #funny #memes #students #2026"},
    {"pill": "PK Bhaiya Roasting Day By Day 📈⚡", "title": "PK Bhaiya Roasting Day By Day 📈⚡ #prashantkirad #nexttoppers #funny #roasting #studentlife #2026"},
]


def build_roast_collage_short(
    segments: list[dict],
    *,
    hook_pill: str,
    watermark: str,
    out_mp4: Path,
    bgm_path: Path | None = None,
) -> Path:
    """Club 4 funny/roast teacher clips into a viral ~55s 2x2 vertical Short with B&W emoji freezes.

    Each item in `segments`: {"path": Path, "start_s": float, "dur_s": float, "face_cx": float}
    (optional "face_cy": float, "caption": str, "emoji": str, "crop_box": (wf, hf, xf, yf)).
    """
    if len(segments) < 4:
        raise ValueError("build_roast_collage_short requires 4 segments")
    segs = segments[:4]
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    tile = 534
    gap = 8
    grid_x = (1080 - (tile * 2 + gap)) // 2  # 2px
    grid_y = 360
    coords = [
        (grid_x, grid_y),
        (grid_x + tile + gap, grid_y),
        (grid_x, grid_y + tile + gap),
        (grid_x + tile + gap, grid_y + tile + gap),
    ]

    render_overlay_py = _resolve_render_overlay_script()

    with tempfile.TemporaryDirectory(prefix="trio_collage_") as td_str:
        td = Path(td_str)
        tile_mp4s: list[Path] = []
        idle_pngs: list[Path] = []
        done_pngs: list[Path] = []
        durs: list[float] = []

        # Step 1: Extract each tight face-zoomed 534x534 tile with yellow caption + permanent B&W emoji freeze
        for idx, s in enumerate(segs):
            src = Path(s["path"])
            start_s = max(0.0, float(s.get("start_s", 0.0)))
            dur_s = max(5.0, min(14.5, float(s.get("dur_s", 13.8))))
            face_cx = max(0.16, min(0.84, float(s.get("face_cx", 0.5))))
            face_cy = max(0.25, min(0.68, float(s.get("face_cy", 0.44))))
            freeze_at = max(2.0, dur_s - 1.2)
            durs.append(dur_s)

            default_cap, default_em = TILE_REACTIONS[idx % len(TILE_REACTIONS)]
            tile_cap = str(s.get("caption") or default_cap)
            freeze_em = str(s.get("emoji") or default_em)

            live_ov = td / f"tile_live_{idx}.png"
            freeze_ov = td / f"tile_freeze_{idx}.png"
            for ov_out, em_val in ((live_ov, ""), (freeze_ov, freeze_em)):
                spec_p = td / f"spec_{idx}_{'frz' if em_val else 'live'}.json"
                spec_p.write_text(
                    json.dumps({
                        "width": tile,
                        "height": tile,
                        "tileMode": True,
                        "tileCaption": tile_cap,
                        "freezeEmoji": em_val,
                    }, ensure_ascii=False),
                    encoding="utf-8",
                )
                subprocess.run([sys.executable, str(render_overlay_py), str(spec_p), str(ov_out)], check=True)

            t_mp4 = td / f"tile_{idx}.mp4"
            idle_jpg = td / f"idle_{idx}.jpg"
            done_jpg = td / f"done_{idx}.jpg"
            crop_box = s.get("crop_box")
            if crop_box:
                wf, hf, xf, yf = crop_box
                crop_expr = (
                    f"crop=iw*{wf:.3f}:ih*{hf:.3f}:iw*{xf:.3f}:ih*{yf:.3f},"
                    f"scale={tile}:{tile}:force_original_aspect_ratio=increase,"
                    f"crop={tile}:{tile}"
                )
            else:
                # Zoom slightly tighter (~0.80 of height) around the teacher's face so whiteboards stay cropped out
                crop_expr = (
                    f"scale=-2:720,"
                    f"crop='min(iw,ih*0.80)':'min(iw,ih*0.80)':"
                    f"'max(0,min(iw-min(iw,ih*0.80),iw*{face_cx:.3f}-min(iw,ih*0.80)/2))':"
                    f"'max(0,min(ih-min(iw,ih*0.80),ih*{face_cy:.3f}-min(iw,ih*0.80)/2))',"
                    f"scale={tile}:{tile}"
                )

            fc_tile = (
                f"[0:v]{crop_expr},fps=30,format=yuv420p,"
                f"eq=contrast=1.08:saturation=1.18,"
                f"hue=s='if(gte(t,{freeze_at:.2f}),0,1)',"
                f"eq=contrast='if(gte(t,{freeze_at:.2f}),1.28,1.0)':enable='gte(t,{freeze_at:.2f})'[base];"
                f"[base][1:v]overlay=0:0:enable='lt(t,{freeze_at:.2f})'[v1];"
                f"[v1][2:v]overlay=0:0:enable='gte(t,{freeze_at:.2f})'[vout]"
            )
            af = "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,loudnorm=I=-15:TP=-1.5:LRA=9"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", f"{start_s:.2f}", "-t", f"{dur_s:.2f}",
                    "-i", str(src), "-i", str(live_ov), "-i", str(freeze_ov),
                    "-filter_complex", fc_tile,
                    "-map", "[vout]", "-map", "0:a",
                    "-af", af,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k", str(t_mp4), "-loglevel", "error",
                ],
                check=True,
            )
            # Waiting tiles (j > turn) show dimmed color; completed tiles (j < turn) stay B&W + giant emoji!
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", f"{min(1.0, freeze_at * 0.4):.2f}", "-i", str(t_mp4),
                    "-frames:v", "1", "-vf", "eq=brightness=-0.18:saturation=0.58", str(idle_jpg), "-loglevel", "error",
                ],
                check=True,
            )
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", f"{max(0.2, dur_s - 0.15):.2f}", "-i", str(t_mp4),
                    "-frames:v", "1", str(done_jpg), "-loglevel", "error",
                ],
                check=True,
            )
            tile_mp4s.append(t_mp4)
            idle_pngs.append(idle_jpg)
            done_pngs.append(done_jpg)

        # Step 2: Compose 4 sequential turns (done tiles stay B&W+emoji, active plays, future tiles stay dimmed)
        seg_mp4s: list[Path] = []
        for turn in range(4):
            seg_out = td / f"turn_{turn}.mp4"
            dur_s = durs[turn]
            inputs = []
            for j in range(4):
                if j == turn:
                    inputs += ["-i", str(tile_mp4s[j])]
                elif j < turn:
                    inputs += ["-loop", "1", "-t", f"{dur_s:.2f}", "-i", str(done_pngs[j])]
                else:
                    inputs += ["-loop", "1", "-t", f"{dur_s:.2f}", "-i", str(idle_pngs[j])]

            fc_parts = [
                f"[{turn}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:2,eq=brightness=-0.20[bg]"
            ]
            prev = "[bg]"
            for j, (ox, oy) in enumerate(coords):
                nxt = f"[v{j}]"
                fc_parts.append(f"{prev}[{j}:v]overlay={ox}:{oy}:shortest=1{nxt}")
                prev = nxt

            fc = ";".join(fc_parts)
            subprocess.run(
                [
                    "ffmpeg", "-y", *inputs,
                    "-filter_complex", fc,
                    "-map", prev, "-map", f"{turn}:a",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(seg_out), "-loglevel", "error",
                ],
                check=True,
            )
            seg_mp4s.append(seg_out)

        # Step 3: Concat all 4 turns, blend subtle BGM with normalize=0 (loud punch), and overlay full white top banner
        concat_txt = td / "concat.txt"
        concat_txt.write_text("\n".join(f"file '{p.as_posix()}'" for p in seg_mp4s), encoding="utf-8")
        joined = td / "joined.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c", "copy", str(joined), "-loglevel", "error"],
            check=True,
        )

        ov_spec = td / "overlay.json"
        ov_png = td / "overlay.png"
        ov_spec.write_text(
            json.dumps({
                "width": 1080,
                "height": 1920,
                "topText": hook_pill,
                "topPill": True,
                "fullBanner": True,
                "watermarkText": watermark,
                "whiteBg": False,
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        subprocess.run([sys.executable, str(render_overlay_py), str(ov_spec), str(ov_png)], check=True)

        if bgm_path and Path(bgm_path).exists():
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(joined),
                    "-i", str(ov_png),
                    "-stream_loop", "-1", "-i", str(bgm_path),
                    "-filter_complex",
                    "[0:v][1:v]overlay=0:0[vout];[2:a]volume=0.14[bgm];"
                    "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                    "loudnorm=I=-15:TP=-1.5:LRA=9[aout]",
                    "-map", "[vout]", "-map", "[aout]",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "19",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_mp4), "-loglevel", "error",
                ],
                check=True,
            )
        else:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(joined), "-i", str(ov_png),
                    "-filter_complex", "[0:v][1:v]overlay=0:0[vout]",
                    "-map", "[vout]", "-map", "0:a",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "19", "-c:a", "copy", str(out_mp4), "-loglevel", "error",
                ],
                check=True,
            )
    return out_mp4


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
            channel_display_name="NextToppers Roast",
            expected_youtube_channel_id="UCrqB8xuwv8CCrS3n_WHIe7Q",
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
        cache_root = Path(os.environ.get("CLIPFORGE_DATA_DIR") or (r"E:\ClipForgeData" if os.name == "nt" else tempfile.gettempdir()))
        cache_dir = cache_root / "url_cache"
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
                "--remote-components", "ejs:github",
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

    def _standalone_render_short(
        self,
        *,
        local_src: Path,
        start_ms: int,
        end_ms: int,
        face_cx: float,
        is_vertical: bool,
        hook_pill: str | None,
        bgm_path: Path | None,
        out_mp4: Path,
        speed_factor: float = 1.0,
    ) -> dict | None:
        """Render a clean 1080x1920 Short using FFmpeg + Pillow directly (used offline/GitHub Actions or viral remix)."""
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        render_overlay_py = _resolve_render_overlay_script()
        start_s = max(0.0, start_ms / 1000.0)
        dur_s = max(8.0, min(59.0, (end_ms - start_ms) / 1000.0))

        with tempfile.TemporaryDirectory(prefix="standalone_short_") as td_str:
            td = Path(td_str)
            ov_spec = td / "ov.json"
            ov_png = td / "ov.png"
            ov_spec.write_text(
                json.dumps({
                    "width": 1080,
                    "height": 1920,
                    "topText": hook_pill or "",
                    "topPill": bool(hook_pill),
                    "fullBanner": bool(hook_pill),
                    "watermarkText": self.watermark,
                    "whiteBg": False,
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(render_overlay_py), str(ov_spec), str(ov_png)], check=True)

            if is_vertical:
                base_vf = (
                    "split[fg0][bg0];"
                    "[bg0]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:2,eq=brightness=-0.18[bg];"
                    "[fg0]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2"
                )
            else:
                cx = max(0.16, min(0.84, face_cx))
                base_vf = (
                    f"split[fg0][bg0];"
                    f"[bg0]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:2,eq=brightness=-0.18[bg];"
                    f"[fg0]crop='min(iw,ih*0.86)':ih:'max(0,min(iw-min(iw,ih*0.86),iw*{cx:.3f}-min(iw,ih*0.86)/2))':0,scale=1080:-2[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
                )

            spd_vf = f",setpts={1.0 / speed_factor:.4f}*PTS" if abs(speed_factor - 1.0) > 0.002 else ""
            spd_af = f",atempo={speed_factor:.4f}" if abs(speed_factor - 1.0) > 0.002 else ""
            vf = f"{base_vf}{spd_vf},fps=30,format=yuv420p,eq=contrast=1.06:saturation=1.12[vbase];[vbase][1:v]overlay=0:0[vout]"
            if bgm_path and bgm_path.exists():
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", f"{start_s:.2f}", "-t", f"{dur_s:.2f}", "-i", str(local_src),
                    "-i", str(ov_png),
                    "-stream_loop", "-1", "-i", str(bgm_path),
                    "-filter_complex",
                    f"{vf};[2:a]volume=0.11[bgm];[0:a]loudnorm=I=-15:TP=-1.5:LRA=9{spd_af}[va];"
                    "[va][bgm]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                    "loudnorm=I=-15:TP=-1.5:LRA=9[aout]",
                    "-map", "[vout]", "-map", "[aout]",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_mp4), "-loglevel", "error",
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", f"{start_s:.2f}", "-t", f"{dur_s:.2f}", "-i", str(local_src),
                    "-i", str(ov_png),
                    "-filter_complex", vf,
                    "-af", f"loudnorm=I=-15:TP=-1.5:LRA=9{spd_af}",
                    "-map", "[vout]", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_mp4), "-loglevel", "error",
                ]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0 or not out_mp4.exists():
                logger.warning("Standalone FFmpeg render failed: %s", r.stderr[-200:])
                return None
        return {"filePath": str(out_mp4), "durationMs": int((dur_s / speed_factor) * 1000), "transcript": hook_pill or ""}

    def cleanup_storage(self, *, keep_short_days: int = 5) -> int:
        """Delete heavy downloaded raw videos immediately and prune old compiled/expired MP4s."""
        removed = 0
        # 1. Always delete raw yt-dlp source downloads once clip extraction finishes
        for cache_root in (
            Path(os.environ.get("CLIPFORGE_DATA_DIR", r"E:\ClipForgeData")) / "url_cache",
            Path(r"D:\ClipForgeData\renders\url_cache"),
        ):
            if cache_root.exists():
                for f in cache_root.glob("yt_*.mp4*"):
                    try:
                        f.unlink()
                        removed += 1
                    except OSError:
                        pass

        # 2. Remove temporary collage scratch folders
        tmp_dir = self.artifacts_dir / "_tmp_collage"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # 3. Clean stale ClipForge render/export scratch files older than 1 day on E:\ClipForgeData
        cutoff_render = datetime.now(timezone.utc) - timedelta(days=1)
        data_root = Path(os.environ.get("CLIPFORGE_DATA_DIR", r"E:\ClipForgeData"))
        for sub in ("renders", "exports", "cache"):
            sub_dir = data_root / sub
            if sub_dir.exists():
                for f in sub_dir.rglob("*"):
                    if f.is_file():
                        try:
                            if datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc) < cutoff_render:
                                f.unlink()
                                removed += 1
                        except OSError:
                            pass

        # 4. Prune Short MP4 files that were already compiled into a Long video or older than keep_short_days
        cutoff_short = datetime.now(timezone.utc) - timedelta(days=keep_short_days)
        history = self._load_history()
        for rec in history.get("produced_clips", []):
            fp = Path(rec.get("file_path") or "")
            if not fp.exists() or fp.suffix.lower() != ".mp4":
                continue
            compiled = bool(rec.get("compiled_in_long"))
            created_str = rec.get("created_at") or ""
            is_old = False
            try:
                if created_str:
                    is_old = datetime.fromisoformat(created_str.replace("Z", "+00:00")) < cutoff_short
            except Exception:
                pass
            if compiled or is_old:
                try:
                    fp.unlink()
                    rec["file_deleted"] = True
                    removed += 1
                except OSError:
                    pass
        self._save_history(history)
        return removed

    @staticmethod
    def _is_vertical_video(video_path: Path) -> bool:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return False
        w = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280
        h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720
        cap.release()
        return (w / max(1.0, h)) < 0.78

    def _produce_collage_item(
        self,
        candidates: list[dict],
        start_cursor: int,
        bgm: Path | None,
        batch_index: int,
        produced_count: int,
    ) -> tuple[dict, str, dict, float, dict, int] | None:
        """Pick 4 horizontal face-verified roast punchlines and club them into a 2x2 collage Short."""
        segs: list[dict] = []
        used_sources: list[dict] = []
        cursor = start_cursor
        checked = 0
        while cursor < len(candidates) and len(segs) < 4 and checked < 14:
            c = candidates[cursor]
            cursor += 1
            if c.get("is_short_remix") or c.get("video_id") in ZOOM_CONFERENCE_IDS:
                continue
            checked += 1
            local_p = self._download_to_cache(c["url"], c["video_id"])
            if not local_p or self._is_vertical_video(local_p):
                continue
            peaks = _fetch_heatmap_peaks(c["url"], max_peaks=2)
            seg_dur = 13.8
            s_ms, e_ms, ratio, _ = find_best_face_window(
                local_p, target_sec=seg_dur, scan_step_sec=30.0, preferred_peaks=peaks
            )
            fcx, fcy, fw_frac = _face_focus_box(local_p, s_ms, e_ms)
            if ratio < 0.55 or fw_frac < 0.09:
                continue
            cap_text, em_char = TILE_REACTIONS[(produced_count + len(segs)) % len(TILE_REACTIONS)]
            segs.append({
                "path": local_p,
                "start_s": max(0.0, s_ms / 1000.0),
                "dur_s": seg_dur,
                "face_cx": fcx,
                "face_cy": fcy,
                "caption": cap_text,
                "emoji": em_char,
            })
            used_sources.append(c)

        if len(segs) < 4:
            return None

        hook_cfg = COLLAGE_HOOKS[(produced_count + batch_index) % len(COLLAGE_HOOKS)]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        tmp_out = self.artifacts_dir / "_tmp_collage" / f"{stamp}_{batch_index}.mp4"
        build_roast_collage_short(
            segs,
            hook_pill=hook_cfg["pill"],
            watermark=self.watermark,
            out_mp4=tmp_out,
            bgm_path=bgm,
        )
        lead_src = used_sources[0]
        fake_out0 = {
            "filePath": str(tmp_out),
            "durationMs": int(sum(s["dur_s"] for s in segs) * 1000),
            "transcript": " | ".join(u["title"][:45] for u in used_sources),
        }
        return lead_src, "roast-collage", hook_cfg, 1.0, fake_out0, cursor

    def run_batch(
        self,
        *,
        count: int = 2,
        style: str = "both",  # 'both' | 'auto' | 'roast-live' | 'roast-collage' | 'roast-remix'
        video_url_override: str | None = None,
        start_sec_override: float | None = None,
        duration_sec_override: int | None = None,
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
            all_cands = fetch_comedy_candidates(self.source_channel_ids, limit_per_source=8, include_live_search=True)
            fresh = [c for c in all_cands if c["video_id"] not in used_ids]
            candidates = fresh if fresh else all_cands

        if not candidates:
            raise RuntimeError("No comedy/roasting source videos found.")
        use_clipflow = self.clipflow.is_available()

        outputs: list[dict] = []
        bgm = _pick_comedy_bgm(self.bgm_dir)
        cand_cursor = 0
        collage_cursor = 0

        for i in range(count):
            chosen_output = None
            want_collage = (
                style == "roast-collage"
                or (style == "both" and ((len(history.get("produced_clips", [])) + i) % 2 == 0))
            ) and video_url_override is None
            if want_collage:
                res = self._produce_collage_item(
                    candidates, collage_cursor, bgm, i, len(history.get("produced_clips", []))
                )
                if res is not None:
                    *chosen_list, collage_cursor = res
                    chosen_output = tuple(chosen_list)

            attempts = 0
            while chosen_output is None and cand_cursor < len(candidates) and attempts < 16:
                src = candidates[cand_cursor]
                cand_cursor += 1
                if src["video_id"] in ZOOM_CONFERENCE_IDS and video_url_override is None:
                    logger.info(f"Skipping multi-box Zoom grid {src['video_id']} for single-face roast")
                    continue

                is_remix = (style == "roast-remix") or (style in ("auto", "both") and bool(src.get("is_short_remix")))
                if style in ("auto", "both") and video_url_override is None and not is_remix:
                    continue

                attempts += 1
                local_src = self._download_to_cache(src["url"], src["video_id"])
                if not local_src:
                    continue

                is_vert = self._is_vertical_video(local_src)
                layout = "crop" if is_vert else "face-zoom"
                target_len = float(duration_sec_override or 26)

                if start_sec_override is not None:
                    s_ms = int(start_sec_override * 1000)
                    e_ms = int((start_sec_override + target_len) * 1000)
                    face_ratio, face_cx = verify_face_presence_and_center(local_src, s_ms, e_ms, sample_count=8)
                    if face_ratio < 0.50:
                        logger.info(f"Skipping {src['video_id']} manual slice (face_ratio={face_ratio:.2f})")
                        continue
                elif is_remix:
                    face_ratio, face_cx = verify_face_presence_and_center(local_src, 0, None, sample_count=8)
                    if face_ratio < 0.60:
                        logger.info(f"Skipping {src['video_id']} (face_ratio={face_ratio:.2f} < 0.60)")
                        continue
                    s_ms, e_ms = None, None
                else:
                    peaks = _fetch_heatmap_peaks(src["url"], max_peaks=3)
                    s_ms, e_ms, face_ratio, face_cx = find_best_face_window(
                        local_src, target_sec=target_len, scan_step_sec=25.0, preferred_peaks=peaks
                    )
                    if face_ratio < 0.60 or _avg_face_width_frac(local_src, s_ms, e_ms) < 0.09:
                        logger.info(f"Skipping {src['video_id']} (low face clarity: ratio={face_ratio:.2f})")
                        continue

                hook_cfg = PILL_HOOKS[(len(history.get("produced_clips", [])) + i) % len(PILL_HOOKS)]
                chosen_style = "roast-remix" if is_remix else "roast-live"

                if not use_clipflow:
                    tmp_s_mp4 = self.artifacts_dir / "_tmp_collage" / f"standalone_{src['video_id']}_{i}.mp4"
                    s_start = 0 if s_ms is None else s_ms
                    s_end = int(min(58.0, self._probe_duration_sec(local_src)) * 1000) if e_ms is None else e_ms
                    out0 = self._standalone_render_short(
                        local_src=local_src,
                        start_ms=s_start,
                        end_ms=s_end,
                        face_cx=face_cx,
                        is_vertical=is_vert,
                        hook_pill=None if is_remix else hook_cfg["pill"],
                        bgm_path=None if is_remix else bgm,
                        out_mp4=tmp_s_mp4,
                        speed_factor=1.015 if is_remix else 1.0,
                    )
                    if out0:
                        chosen_output = (src, chosen_style, hook_cfg, face_ratio, out0)
                        break
                    continue

                if is_remix and s_ms is None:
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
                        layout_mode=layout,
                        color_grade="viral-warm",
                        crop_offset_x=face_cx,
                        bgm_path=None,
                        bgm_volume=0.0,
                        mute_original=False,
                        speed_factor=1.015,
                        top_text=None,
                        top_pill=False,
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
                        clip_duration_sec=int(round(target_len)),
                        caption_preset="trio-hinglish",
                        resolution="1080p",
                        provider="gemini",
                        llm_provider="nvidia",
                        prompt=(
                            "Cut the funniest comedy joke, student roast, or savage comeback spoken by "
                            "Prashant Kirad, Shobhit Nirwan, or Digraj Sir. Keep their dialogue crisp."
                        ),
                        language="hinglish",
                        layout_mode=layout,
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

            raw_src_title = " ".join(str(src.get("title") or "").split())
            if chosen_style == "roast-remix" and raw_src_title and raw_src_title != "Manual Comedy Source":
                yt_title = raw_src_title[:100]
            else:
                yt_title = hook_cfg["title"][:100]
            desc = (
                f"{yt_title}\n\n"
                f"Credits: @ExpHub @ShobhitNirwan17 @DigrajSinghRajput214 @NextToppers23\n"
                f"#nexttoppers #prashantkirad #funny #relatable #studentlife #2026"
            )
            tags = [
                "next toppers",
                "prashant kirad",
                "shobhit nirwan",
                "digraj sir",
                "student life",
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
                    upload_settings = self.settings.model_copy(
                        update={
                            "enable_uploads": True,
                            "upload_privacy_status": "public",
                            "allow_public_uploads": True,
                        }
                    )
                    uploader = YouTubeUploader(upload_settings)
                    plan = VideoPlan(
                        topic=src["title"] or yt_title,
                        angle="Next Toppers Trio viral comedy and roasting highlight",
                        format="short",
                        title=yt_title,
                        description=desc,
                        tags=tags,
                        hook=hook_cfg["pill"],
                        script=out0.get("transcript") or yt_title,
                        thumbnail_brief="Bold teacher reaction close-up with white rounded hook pill",
                        thumbnail_text=hook_cfg["pill"][:30],
                    )
                    video_id = uploader.upload(final_mp4, plan, thumbnail_path=None)
                    meta_record["uploaded_video_id"] = video_id
                    if video_id and video_id != "UPLOAD_LIMIT_EXCEEDED":
                        meta_record["uploaded_url"] = f"https://youtube.com/shorts/{video_id}"
                else:
                    logger.warning(f"Upload skipped: authorize token first for {token_path}")

            (clip_out_dir / "metadata.json").write_text(json.dumps(meta_record, indent=2, ensure_ascii=False), encoding="utf-8")
            outputs.append(meta_record)

            if src["video_id"] not in used_ids:
                history.setdefault("processed_sources", []).append(src["video_id"])
                used_ids.add(src["video_id"])
            history.setdefault("produced_clips", []).append(meta_record)
            self._save_history(history)

        self.cleanup_storage()
        return outputs

    @staticmethod
    def _probe_duration_sec(video_path: Path) -> float:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True,
        )
        try:
            return float((p.stdout or "").strip() or 0.0)
        except ValueError:
            return 0.0

    def build_long_compilation(
        self,
        *,
        min_sec: float = 240.0,
        max_sec: float = 300.0,
        upload: bool = False,
    ) -> dict | None:
        """Club recent uploaded/produced roasting Shorts into a 4-5 minute 16:9 Long YouTube video."""
        history = self._load_history()
        produced = history.get("produced_clips", [])
        candidates_recs = [
            r for r in produced
            if not r.get("compiled_in_long")
            and not r.get("file_deleted")
            and r.get("file_path")
            and Path(r["file_path"]).exists()
        ]

        # If fewer than ~min_sec of uncompiled Shorts exist, produce extra Shorts (without double-uploading)
        total_sec = sum(self._probe_duration_sec(Path(r["file_path"])) for r in candidates_recs)
        if total_sec < min_sec:
            needed_clips = max(1, min(6, int((min_sec - total_sec) // 26) + 1))
            extra = self.run_batch(count=needed_clips, style="both", upload=False)
            candidates_recs.extend(extra)

        chosen_recs: list[dict] = []
        acc_sec = 0.0
        for rec in candidates_recs:
            fp = Path(rec["file_path"])
            if not fp.exists():
                continue
            dur = self._probe_duration_sec(fp)
            if dur <= 3.0:
                continue
            if acc_sec + dur > max_sec and acc_sec >= min_sec:
                break
            chosen_recs.append(rec)
            acc_sec += dur
            if acc_sec >= min_sec and len(chosen_recs) >= 6:
                break

        if not chosen_recs:
            return None

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        long_dir = self.artifacts_dir / f"{stamp}_long_compilation"
        long_dir.mkdir(parents=True, exist_ok=True)
        long_mp4 = long_dir / "nexttoppers_roast_compilation.mp4"

        with tempfile.TemporaryDirectory(prefix="trio_long_") as td_str:
            td = Path(td_str)
            norm_parts: list[Path] = []
            for idx, rec in enumerate(chosen_recs):
                src_fp = Path(rec["file_path"])
                part_fp = td / f"part_{idx:02d}.mp4"
                # Frame vertical Short crisply inside 1920x1080 16:9 widescreen with blurred sidebars
                vf = (
                    "split[fg0][bg0];"
                    "[bg0]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=28:2,eq=brightness=-0.22[bg];"
                    "[fg0]scale=-2:1080[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=30,format=yuv420p"
                )
                af = "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,loudnorm=I=-15:TP=-1.5:LRA=9"
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-i", str(src_fp),
                        "-vf", vf, "-af", af,
                        "-c:v", "libx264", "-preset", "fast", "-crf", "21",
                        "-c:a", "aac", "-b:a", "192k", str(part_fp), "-loglevel", "error",
                    ],
                    check=True,
                )
                norm_parts.append(part_fp)

            concat_file = td / "concat.txt"
            concat_file.write_text("\n".join(f"file '{p.as_posix()}'" for p in norm_parts), encoding="utf-8")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(long_mp4), "-loglevel", "error"],
                check=True,
            )

        final_dur = self._probe_duration_sec(long_mp4)
        yt_title = "NextToppers Roast Compilation 🔥 Non-Stop Prashant, Shobhit & Digraj Funny Moments! 😂"[:100]
        source_links = "\n".join(f"- {r.get('source_url')}" for r in chosen_recs[:10] if r.get("source_url"))
        desc = (
            f"{yt_title}\n\n"
            f"Best Next Toppers Trio (Prashant Kirad, Shobhit Nirwan, Digraj Singh Rajput) roasting & dark comedy moments clubbed together!\n\n"
            f"Credits & Official Channels:\n"
            f"@ExpHub @ShobhitNirwan17 @DigrajSinghRajput214 @NextToppers23 @PrashantKiradvlogs\n\n"
            f"Featured Clips:\n{source_links}\n\n"
            f"#nexttoppers #prashantkirad #shobhitnirwan #digrajsinghrajput #roasting #comedy #compilation #nexttoppersroast"
        )
        tags = [
            "next toppers", "next toppers roast", "prashant kirad roasting",
            "shobhit nirwan funny", "digraj sir comedy", "next toppers funny compilation",
            "next toppers dark comedy", "class 10 funny moments",
        ]
        long_record = {
            "style": "long-compilation",
            "clip_count": len(chosen_recs),
            "duration_sec": round(final_dur, 1),
            "title": yt_title,
            "description": desc,
            "tags": tags,
            "file_path": str(long_mp4),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_video_id": None,
        }

        if upload:
            token_path = Path(self.settings.youtube_token_file)
            if token_path.exists():
                upload_settings = self.settings.model_copy(
                    update={
                        "enable_uploads": True,
                        "upload_privacy_status": "public",
                        "allow_public_uploads": True,
                    }
                )
                uploader = YouTubeUploader(upload_settings)
                plan = VideoPlan(
                    topic="Next Toppers Trio Roasting Compilation",
                    angle="4-5 minute clubbed compilation of viral Next Toppers Trio roasting Shorts",
                    format="long",
                    title=yt_title,
                    description=desc,
                    tags=tags,
                    hook="Non-Stop NextToppers Roasting Compilation!",
                    script=desc,
                    thumbnail_brief="All three Next Toppers teachers laughing and roasting in bold gaming style",
                    thumbnail_text="NEXTTOPPERS ROAST",
                )
                video_id = uploader.upload(long_mp4, plan, thumbnail_path=None)
                long_record["uploaded_video_id"] = video_id
                if video_id and video_id != "UPLOAD_LIMIT_EXCEEDED":
                    long_record["uploaded_url"] = f"https://www.youtube.com/watch?v={video_id}"
                    compile_id = video_id
                    for rec in chosen_recs:
                        rec["compiled_in_long"] = compile_id
                    try:
                        long_mp4.unlink()
                        long_record["file_deleted"] = True
                    except OSError:
                        pass
            else:
                logger.warning(f"Long compilation upload skipped: authorize {token_path}")

        (long_dir / "metadata.json").write_text(json.dumps(long_record, indent=2, ensure_ascii=False), encoding="utf-8")
        history = self._load_history()
        compiled_paths = {r.get("file_path") for r in chosen_recs}
        for rec in history.get("produced_clips", []):
            if rec.get("file_path") in compiled_paths and long_record.get("uploaded_video_id"):
                rec["compiled_in_long"] = long_record["uploaded_video_id"]
        history.setdefault("long_compilations", []).append(long_record)
        history["last_long_compiled_at"] = datetime.now(timezone.utc).isoformat()
        self._save_history(history)
        self.cleanup_storage()
        return long_record

    def run_long_compilation_if_due(self, *, every_days: int = 4, upload: bool = True) -> dict | None:
        """Upload a 4-5 min clubbed Long compilation if at least `every_days` have passed since the last one."""
        history = self._load_history()
        last_str = history.get("last_long_compiled_at")
        if last_str:
            try:
                last_dt = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - last_dt < timedelta(days=every_days):
                    return None
            except Exception:
                pass
        else:
            # Wait until we have accumulated enough uncompiled Shorts (~4 days / >=8 Shorts) unless invoked manually
            avail = [
                r for r in history.get("produced_clips", [])
                if not r.get("compiled_in_long") and r.get("file_path") and Path(r["file_path"]).exists()
            ]
            if len(avail) < 8:
                return None
        return self.build_long_compilation(upload=upload)
