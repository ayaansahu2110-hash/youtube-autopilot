from pathlib import Path

import httpx

from autopilot.models import VisualAsset


class PexelsVideoProvider:
    API_URL = "https://api.pexels.com/v1/videos/search"

    def __init__(self, api_key: str | None):
        self.api_key = api_key

    def fetch_assets(
        self,
        queries: list[str],
        output_dir: Path,
        *,
        vertical: bool,
        limit: int,
    ) -> list[VisualAsset]:
        if not self.api_key:
            return []
        output_dir.mkdir(parents=True, exist_ok=True)
        assets: list[VisualAsset] = []
        used_ids: set[int] = set()
        for query in queries:
            if len(assets) >= limit:
                break
            video = self._search_best(query, vertical=vertical, used_ids=used_ids)
            if not video:
                continue
            used_ids.add(int(video["id"]))
            download_url = self._best_file(video, vertical=vertical)
            if not download_url:
                continue
            path = output_dir / f"pexels-{video['id']}.mp4"
            try:
                with httpx.stream("GET", download_url, timeout=60, follow_redirects=True) as response:
                    response.raise_for_status()
                    with path.open("wb") as handle:
                        for chunk in response.iter_bytes():
                            handle.write(chunk)
            except Exception:
                path.unlink(missing_ok=True)
                continue
            user = video.get("user") or {}
            assets.append(
                VisualAsset(
                    local_path=path,
                    source_page_url=video.get("url"),
                    creator=user.get("name"),
                    query=query,
                )
            )
        return assets

    def _search_best(self, query: str, *, vertical: bool, used_ids: set[int]) -> dict | None:
        try:
            response = httpx.get(
                self.API_URL,
                headers={"Authorization": self.api_key or ""},
                params={
                    "query": query,
                    "orientation": "portrait" if vertical else "landscape",
                    "size": "large",
                    "per_page": 20,
                },
                timeout=20,
            )
            response.raise_for_status()
        except Exception:
            return None

        videos = [
            video for video in response.json().get("videos", [])
            if int(video.get("id", 0)) not in used_ids
        ]
        if not videos:
            return None

        # Prefer clips that are long enough to trim cleanly, high resolution,
        # and actually match the requested orientation.
        def score(video: dict) -> tuple[int, int, int]:
            duration = int(video.get("duration") or 0)
            files = video.get("video_files") or []
            best_pixels = 0
            orientation_ok = False
            for item in files:
                width = int(item.get("width") or 0)
                height = int(item.get("height") or 0)
                if width and height:
                    best_pixels = max(best_pixels, width * height)
                    if (height >= width) == vertical:
                        orientation_ok = True
            duration_score = 1 if 4 <= duration <= 30 else 0
            return (1 if orientation_ok else 0, duration_score, best_pixels)

        videos.sort(key=score, reverse=True)
        return videos[0]

    @staticmethod
    def _best_file(video: dict, *, vertical: bool) -> str | None:
        files = [item for item in video.get("video_files", []) if item.get("link")]
        if not files:
            return None

        def score(item: dict) -> tuple[int, int, int]:
            width = int(item.get("width") or 0)
            height = int(item.get("height") or 0)
            orientation_ok = height >= width if vertical else width >= height
            pixels = width * height
            oversize_penalty = abs(max(width, height) - 2160)
            return (1 if orientation_ok else 0, pixels, -oversize_penalty)

        files.sort(key=score, reverse=True)
        return str(files[0]["link"])

    @staticmethod
    def attribution_lines(assets: list[VisualAsset]) -> list[str]:
        lines = []
        seen: set[str] = set()
        for asset in assets:
            if not asset.source_page_url or asset.source_page_url in seen:
                continue
            seen.add(asset.source_page_url)
            creator = asset.creator or "Pexels contributor"
            lines.append(f"Video by {creator} on Pexels: {asset.source_page_url}")
        return lines
