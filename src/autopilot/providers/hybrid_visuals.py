from __future__ import annotations

import re
import textwrap
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont

from autopilot.models import SceneBeat, VisualAsset
from autopilot.providers.visuals import PexelsVideoProvider


class HybridVisualDirector:
    """Build one intentionally matched visual per narration scene.

    Priority is real public UI -> branded explanatory motion card -> stock B-roll.
    Browser capture is intentionally read-only: no login, typing, form submission or
    account interaction is attempted.
    """

    def __init__(self, pexels: PexelsVideoProvider):
        self.pexels = pexels

    def build_assets(
        self,
        scenes: list[SceneBeat],
        output_dir: Path,
        *,
        vertical: bool,
        allowed_source_urls: list[str],
        limit: int,
    ) -> list[VisualAsset]:
        output_dir.mkdir(parents=True, exist_ok=True)
        allowed = {url for url in allowed_source_urls if url.startswith(("http://", "https://"))}
        assets: list[VisualAsset] = []

        for scene_index, scene in enumerate(scenes[:limit]):
            asset: VisualAsset | None = None

            if scene.visual_mode == "ui":
                source_url = scene.source_url if scene.source_url in allowed else ""
                if source_url:
                    asset = self._capture_public_ui(
                        source_url,
                        output_dir / f"scene-{scene_index:02d}-ui.png",
                        scene_index=scene_index,
                        vertical=vertical,
                    )

            if asset is None and scene.visual_mode == "stock":
                stock = self.pexels.fetch_assets(
                    [scene.visual_query],
                    output_dir / "stock",
                    vertical=vertical,
                    limit=1,
                )
                if stock:
                    asset = stock[0].model_copy(
                        update={
                            "scene_index": scene_index,
                            "visual_mode": "stock",
                            "asset_kind": "video",
                        }
                    )

            if asset is None:
                # Motion graphics are the safe default. A purposeful explainer card
                # is better than unrelated stock footage when exact UI is unavailable.
                card = output_dir / f"scene-{scene_index:02d}-motion.png"
                self._make_motion_card(scene, card, vertical=vertical, scene_index=scene_index)
                asset = VisualAsset(
                    local_path=card,
                    query=scene.visual_query,
                    scene_index=scene_index,
                    asset_kind="image",
                    visual_mode="motion",
                )

            assets.append(asset)

        return assets

    def _capture_public_ui(
        self,
        url: str,
        output: Path,
        *,
        scene_index: int,
        vertical: bool,
    ) -> VisualAsset | None:
        raw = output.with_name(output.stem + "-raw.png")
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(1800)
                page.screenshot(path=str(raw), full_page=False)
                browser.close()

            self._frame_browser_capture(raw, output, url=url, vertical=vertical)
            raw.unlink(missing_ok=True)
            return VisualAsset(
                local_path=output,
                source_page_url=url,
                creator=urlparse(url).netloc,
                query="public product interface",
                scene_index=scene_index,
                asset_kind="image",
                visual_mode="ui",
            )
        except Exception:
            raw.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            return None

    def _frame_browser_capture(self, raw: Path, output: Path, *, url: str, vertical: bool) -> None:
        width, height = (1080, 1920) if vertical else (1920, 1080)
        canvas = Image.new("RGB", (width, height), (8, 12, 24))
        draw = ImageDraw.Draw(canvas)
        capture = Image.open(raw).convert("RGB")

        margin = int(width * 0.055)
        top = int(height * (0.18 if vertical else 0.12))
        available_w = width - margin * 2
        available_h = int(height * (0.60 if vertical else 0.72))
        capture.thumbnail((available_w, available_h), Image.Resampling.LANCZOS)
        left = (width - capture.width) // 2
        y = top + (available_h - capture.height) // 2

        # Browser-style frame and soft border.
        pad = 12
        draw.rounded_rectangle(
            (left - pad, y - 56, left + capture.width + pad, y + capture.height + pad),
            radius=24,
            fill=(22, 28, 43),
            outline=(70, 82, 105),
            width=2,
        )
        for offset, color in ((0, (255, 99, 95)), (22, (255, 190, 46)), (44, (38, 201, 88))):
            draw.ellipse((left + offset, y - 38, left + offset + 12, y - 26), fill=color)
        canvas.paste(capture, (left, y))

        brand_font = self._font(28 if vertical else 30, bold=True)
        domain_font = self._font(24 if vertical else 22)
        draw.text((margin, 55), "BYTEVEXA", font=brand_font, fill=(119, 255, 166))
        domain = urlparse(url).netloc.removeprefix("www.")[:45]
        draw.text((margin, 108), domain, font=domain_font, fill=(206, 213, 226))
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output, quality=94)

    def _make_motion_card(
        self,
        scene: SceneBeat,
        output: Path,
        *,
        vertical: bool,
        scene_index: int,
    ) -> None:
        width, height = (1080, 1920) if vertical else (1920, 1080)
        image = Image.new("RGB", (width, height), (8, 12, 24))
        draw = ImageDraw.Draw(image)

        margin = int(width * 0.075)
        draw.rounded_rectangle(
            (margin, int(height * 0.19), width - margin, int(height * 0.78)),
            radius=42,
            fill=(17, 24, 39),
            outline=(52, 66, 88),
            width=3,
        )

        brand_font = self._font(29 if vertical else 32, bold=True)
        kicker_font = self._font(27 if vertical else 25, bold=True)
        headline_font = self._font(58 if vertical else 52, bold=True)
        body_font = self._font(35 if vertical else 30)
        number_font = self._font(30 if vertical else 28, bold=True)

        draw.text((margin, 65), "BYTEVEXA", font=brand_font, fill=(119, 255, 166))
        draw.text((width - margin - 70, 65), f"{scene_index + 1:02d}", font=number_font, fill=(130, 142, 164))

        purpose = self._clean(scene.purpose).upper()[:28] or "EXPLAINED"
        draw.text((margin + 48, int(height * 0.25)), purpose, font=kicker_font, fill=(119, 255, 166))

        headline = self._clean(scene.on_screen_text) or self._headline_from_narration(scene.narration)
        y = int(height * 0.33)
        for line in self._wrap(headline, 22 if vertical else 34, max_lines=3):
            draw.text((margin + 48, y), line, font=headline_font, fill=(246, 248, 252))
            y += int(headline_font.size * 1.18)

        body = self._clean(scene.narration)
        y += 34
        for line in self._wrap(body, 41 if vertical else 65, max_lines=4):
            draw.text((margin + 48, y), line, font=body_font, fill=(190, 199, 216))
            y += int(body_font.size * 1.35)

        # Simple visual motif that animates well with a slow zoom in FFmpeg.
        motif_y = int(height * 0.70)
        start_x = margin + 52
        end_x = width - margin - 52
        draw.line((start_x, motif_y, end_x, motif_y), fill=(55, 70, 94), width=4)
        progress = start_x + int((end_x - start_x) * min(0.92, 0.25 + scene_index * 0.075))
        draw.line((start_x, motif_y, progress, motif_y), fill=(119, 255, 166), width=7)
        draw.ellipse((progress - 10, motif_y - 10, progress + 10, motif_y + 10), fill=(119, 255, 166))

        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, quality=95)

    @staticmethod
    def _headline_from_narration(text: str) -> str:
        clean = HybridVisualDirector._clean(text)
        words = clean.split()
        return " ".join(words[:8]).rstrip(".,:;!?")

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _wrap(text: str, width: int, *, max_lines: int) -> list[str]:
        lines = textwrap.wrap(text, width=max(8, width), break_long_words=False, break_on_hyphens=False)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip(" .") + "…"
        return lines or [""]

    @staticmethod
    def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        )
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
        return ImageFont.load_default()
