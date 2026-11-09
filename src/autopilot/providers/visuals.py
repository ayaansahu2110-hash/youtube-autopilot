from pathlib import Path

import httpx

from autopilot.models import VisualAsset


class PexelsVideoProvider:
    API_URL = "https://api.pexels.com/v1/videos/search"

    def __init__(self, api_key: str | None):
        self.api_key = api_key
        self._used_ids: set[int] = set()

    def fetch_assets(
        self,
        queries: list[str],
        output_dir: Path,
        *,
        vertical: bool,
        limit: int,
        negative_keywords: list[str] | None = None,
        positive_keywords: list[str] | None = None,
    ) -> list[VisualAsset]:
        if not self.api_key:
            return []
        output_dir.mkdir(parents=True, exist_ok=True)
        assets: list[VisualAsset] = []
        used_ids = self._used_ids
        for scene_index, query in enumerate(queries[:limit]):
            video = self._search_best(
                query,
                vertical=vertical,
                used_ids=used_ids,
                negative_keywords=negative_keywords,
                positive_keywords=positive_keywords,
            )
            if not video:
                continue
            used_ids.add(int(video["id"]))
            download_url = self._best_file(video, vertical=vertical)
            if not download_url:
                continue
            path = output_dir / f"scene-{scene_index:02d}-pexels-{video['id']}.mp4"
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
                    scene_index=scene_index,
                )
            )
        return assets

    def _search_best(
        self,
        query: str,
        *,
        vertical: bool,
        used_ids: set[int],
        negative_keywords: list[str] | None = None,
        positive_keywords: list[str] | None = None,
    ) -> dict | None:
        try:
            response = httpx.get(
                self.API_URL,
                headers={"Authorization": self.api_key or ""},
                params={
                    "query": query,
                    "orientation": "portrait" if vertical else "landscape",
                    "size": "large",
                    "per_page": 30,
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

        negs = [n.lower().strip() for n in (negative_keywords or []) if n.strip()]
        filtered = []
        for v in videos:
            url_slug = str(v.get("url") or "").lower()
            if any(neg in url_slug for neg in negs):
                continue
            filtered.append(v)

        candidates = filtered if filtered else videos
        pos = [p.lower().strip() for p in (positive_keywords or []) if p.strip()]

        def score(item: tuple[int, dict]) -> tuple[int, int, int, int, int]:
            rank, video = item
            url_slug = str(video.get("url") or "").lower()
            pos_matches = sum(2 for p in pos if p in url_slug)
            duration = int(video.get("duration") or 0)
            files = video.get("video_files") or []
            best_pixels = 0
            orientation_ok = False
            for f in files:
                width = int(f.get("width") or 0)
                height = int(f.get("height") or 0)
                if width and height:
                    best_pixels = max(best_pixels, width * height)
                    if (height >= width) == vertical:
                        orientation_ok = True
            duration_score = 1 if 3 <= duration <= 25 else 0
            rank_score = max(0, 30 - rank)
            return (1 if orientation_ok else 0, pos_matches, rank_score, duration_score, best_pixels)

        ranked = list(enumerate(candidates))
        ranked.sort(key=score, reverse=True)
        return ranked[0][1]

    @staticmethod
    def _best_file(video: dict, *, vertical: bool) -> str | None:
        files = [item for item in video.get("video_files", []) if item.get("link")]
        if not files:
            return None

        def score(item: dict) -> tuple[int, int, int]:
            width = int(item.get("width") or 0)
            height = int(item.get("height") or 0)
            orientation_ok = height >= width if vertical else width >= height
            max_dim = max(width, height)
            # Perfect match for YouTube Full HD is max dimension 1920 (1080x1920 or 1920x1080)
            # Avoid downloading bloated 4K/UHD (3840x2160) files that take minutes to download
            distance_from_1080p = abs(max_dim - 1920)
            return (1 if orientation_ok else 0, -distance_from_1080p, width * height)

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
