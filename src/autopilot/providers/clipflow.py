from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

import httpx

from autopilot.models import SceneBeat, VisualAsset

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
