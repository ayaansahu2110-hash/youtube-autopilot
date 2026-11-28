from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

import httpx

from autopilot.models import SceneBeat

logger = logging.getLogger(__name__)


class ClipflowProvider:
    """Client for local Clipflow (ClipForge) AI video and clipping API.
    
    Provides high-definition generative AI B-roll with 64 cinematic camera motion presets.
    Designed with a strict fail-safe: if the local server is stopped, offline, times out,
    or returns an error, it immediately logs a warning and returns None, triggering a
    seamless automatic fallback to the standard Pexels/stock pipeline.
    """

    CAMERA_PRESETS = [
        "DOLLY IN",
        "360 ORBIT",
        "CRASH ZOOM IN",
        "SUPER DOLLY IN",
        "AERIAL PULLBACK",
        "ROAD RUSH",
        "FPV DRONE",
        "TILT UP",
        "PAN RIGHT",
        "WHIP PAN",
    ]

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:4820",
        api_key: str | None = None,
        enabled: bool = True,
        timeout_sec: float = 60.0,
    ):
        self.base_url = (base_url or "http://127.0.0.1:4820").rstrip("/")
        self.api_key = api_key or "cf_live_a51399c62b50fcb1d67b80539a3c3e20f1511abf57421a08"
        self.enabled = enabled
        self.timeout_sec = timeout_sec
        self._available_cache: bool | None = None
        self._last_health_check: float = 0.0

    def is_available(self) -> bool:
        """Check if local Clipflow API server is reachable and authorized.
        
        Caches health status for 30 seconds to minimize health check overhead.
        """
        if not self.enabled or not self.api_key:
            return False

        now = time.time()
        if self._available_cache is not None and (now - self._last_health_check) < 30.0:
            return self._available_cache

        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(
                    f"{self.base_url}/api/v1/health",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                self._available_cache = res.status_code == 200
        except Exception:
            self._available_cache = False

        self._last_health_check = now
        return self._available_cache

    def map_camera_preset(self, scene: SceneBeat, scene_index: int = 0) -> str:
        """Intelligently select camera vector based on scene purpose and narration keywords."""
        if scene.shot_type_camera_movement:
            upper = scene.shot_type_camera_movement.upper()
            for preset in self.CAMERA_PRESETS:
                if preset in upper:
                    return preset

        text = f"{scene.purpose} {scene.narration} {scene.visual_query}".lower()
        if any(w in text for w in ("hook", "shock", "mystery", "stop", "never", "watch")):
            return "CRASH ZOOM IN"
        if any(w in text for w in ("scale", "space", "galaxy", "stars", "universe", "web", "world")):
            return "AERIAL PULLBACK"
        if any(w in text for w in ("orbit", "surround", "structure", "temple", "chamber", "monument")):
            return "360 ORBIT"
        if any(w in text for w in ("speed", "jet", "flight", "particle", "fast", "blast", "rush")):
            return "ROAD RUSH"
        if any(w in text for w in ("mechanism", "inside", "deep", "vortex", "atom", "quantum", "singularity")):
            return "SUPER DOLLY IN"

        # Cyclical variety fallback
        fallbacks = ["DOLLY IN", "360 ORBIT", "CRASH ZOOM IN", "AERIAL PULLBACK"]
        return fallbacks[scene_index % len(fallbacks)]

    def generate_scene_video(
        self,
        prompt: str,
        out_path: Path,
        *,
        camera_preset: str = "DOLLY IN",
        duration: int = 4,
        aspect_ratio: str = "9:16",
        resolution: str = "720p",
        provider: str = "nvidia",
    ) -> Path | None:
        """Submit text-to-video / cinema generation job to Clipflow and await completion.
        
        Returns out_path on success, or None on ANY error/timeout to trigger automatic fallback.
        """
        if not self.is_available():
            logger.info("[Clipflow] Local server unavailable; skipping to standard visual provider.")
            return None

        out_path.parent.mkdir(parents=True, exist_ok=True)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "prompt": prompt,
            "mode": "t2v",
            "provider": provider,
            "cameraPreset": camera_preset,
            "duration": duration,
            "aspectRatio": aspect_ratio,
            "resolution": resolution,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                submit_res = client.post(f"{self.base_url}/api/v1/generate", json=body, headers=headers)
                if submit_res.status_code != 202:
                    logger.warning(f"[Clipflow] Submit returned HTTP {submit_res.status_code}: {submit_res.text[:200]}")
                    return None
                data = submit_res.json()
                job_id = data.get("jobId")
                if not job_id:
                    return None

            # Poll for completion
            start_time = time.time()
            job_data = None
            while (time.time() - start_time) < self.timeout_sec:
                time.sleep(2.0)
                try:
                    with httpx.Client(timeout=6.0) as client:
                        poll_res = client.get(f"{self.base_url}/api/v1/jobs/{job_id}", headers=headers)
                        if poll_res.status_code == 200:
                            job_data = poll_res.json()
                            status = job_data.get("status")
                            if status == "completed":
                                break
                            if status in ("failed", "cancelled"):
                                logger.warning(f"[Clipflow] Job {job_id} {status}: {job_data.get('error')}")
                                return None
                except Exception as poll_err:
                    logger.debug(f"[Clipflow] Poll retry ({poll_err})")

            if not job_data or job_data.get("status") != "completed":
                logger.warning(f"[Clipflow] Job {job_id} timed out after {self.timeout_sec}s.")
                return None

            outputs = job_data.get("outputs") or []
            if not outputs:
                return None

            local_rendered_file = outputs[0].get("filePath")
            if local_rendered_file and os.path.exists(local_rendered_file):
                shutil.copy2(local_rendered_file, out_path)
                logger.info(f"[Clipflow] Rendered scene video: {out_path.name}")
                return out_path

            # Fallback to streaming HTTP download
            download_url = outputs[0].get("downloadUrl")
            if download_url:
                full_dl_url = f"{self.base_url}{download_url}"
                with httpx.stream("GET", full_dl_url, headers=headers, timeout=30.0) as dl_stream:
                    if dl_stream.status_code == 200:
                        with open(out_path, "wb") as f:
                            for chunk in dl_stream.iter_bytes():
                                f.write(chunk)
                        logger.info(f"[Clipflow] Downloaded scene video: {out_path.name}")
                        return out_path

            return None

        except Exception as exc:
            logger.warning(f"[Clipflow] Generation exception ({exc}); falling back gracefully.")
            return None

    def clip_video(
        self,
        *,
        video_url: str | None = None,
        file_path: str | Path | None = None,
        title: str | None = None,
        aspect_ratio: str = "9:16",
        clip_count: int = 2,
        clip_duration_sec: int = 22,
        caption_preset: str = "trio-hinglish",
        resolution: str = "1080p",
        provider: str = "gemini",
        llm_provider: str = "nvidia",
        prompt: str | None = None,
        language: str = "hinglish",
        layout_mode: str = "fit-blur",
        color_grade: str = "viral-warm",
        crop_offset_x: float = 0.5,
        bgm_path: str | Path | None = None,
        bgm_volume: float = 0.16,
        mute_original: bool = False,
        speed_factor: float = 1.0,
        top_text: str | None = None,
        bottom_text: str | None = None,
        center_text: str | None = None,
        watermark_text: str | None = None,
        top_pill: bool = False,
        auto_emoji: bool = True,
        burn_captions: bool = True,
        export_all: bool = True,
        start_ms: int | None = None,
        end_ms: int | None = None,
        poll_timeout_sec: float = 360.0,
    ) -> dict | None:
        """Submit a long-to-short ClipForge clipping job and await completed outputs.

        Returns the completed job dict (with outputs list containing filePath, title,
        topHook, bottomHook, emoji, mood, score, transcript) or None on error.
        """
        if not self.is_available():
            logger.warning("[Clipflow] Local server unavailable for clip_video.")
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict = {
            "aspectRatio": aspect_ratio,
            "clipCount": clip_count,
            "clipDurationSec": clip_duration_sec,
            "captionPreset": caption_preset,
            "resolution": resolution,
            "provider": provider,
            "llmProvider": llm_provider,
            "language": language,
            "layoutMode": layout_mode,
            "colorGrade": color_grade,
            "cropOffsetX": crop_offset_x,
            "bgmVolume": bgm_volume,
            "muteOriginal": mute_original,
            "speedFactor": speed_factor,
            "topPill": top_pill,
            "autoEmoji": auto_emoji,
            "burnCaptions": burn_captions,
            "exportAll": export_all,
        }
        if video_url:
            body["videoUrl"] = video_url
        if file_path:
            body["filePath"] = str(file_path)
        if title:
            body["title"] = title
        if prompt:
            body["prompt"] = prompt
        if bgm_path:
            body["bgmPath"] = str(Path(bgm_path).resolve())
        if top_text is not None:
            body["topText"] = top_text
        if bottom_text is not None:
            body["bottomText"] = bottom_text
        if center_text is not None:
            body["centerText"] = center_text
        if watermark_text is not None:
            body["watermarkText"] = watermark_text
        if start_ms is not None and end_ms is not None:
            body["startMs"] = int(start_ms)
            body["endMs"] = int(end_ms)

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(f"{self.base_url}/api/v1/clip", json=body, headers=headers)
                if res.status_code != 202:
                    logger.warning(f"[Clipflow] clip submit HTTP {res.status_code}: {res.text[:250]}")
                    return None
                job_id = res.json().get("jobId")
                if not job_id:
                    return None

            deadline = time.time() + poll_timeout_sec
            while time.time() < deadline:
                time.sleep(3.0)
                try:
                    with httpx.Client(timeout=10.0) as client:
                        jr = client.get(f"{self.base_url}/api/v1/jobs/{job_id}", headers=headers)
                        if jr.status_code == 200:
                            jd = jr.json()
                            st = jd.get("status")
                            if st == "completed":
                                return jd
                            if st in ("failed", "cancelled"):
                                logger.warning(f"[Clipflow] clip job {job_id} {st}: {jd.get('error')}")
                                return None
                except Exception as pe:
                    logger.debug(f"[Clipflow] clip poll retry ({pe})")
            logger.warning(f"[Clipflow] clip job {job_id} timed out after {poll_timeout_sec}s.")
            return None
        except Exception as exc:
            logger.warning(f"[Clipflow] clip_video exception ({exc})")
            return None
