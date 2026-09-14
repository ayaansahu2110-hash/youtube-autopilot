from __future__ import annotations

import re
import shutil
import textwrap
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from autopilot.models import SceneBeat, VisualAsset
from autopilot.providers.visuals import PexelsVideoProvider


class HybridVisualDirector:
    """Build one intentionally matched visual per narration scene.

    Priority: real public product demo -> branded visual explainer -> stock B-roll.
    Public demo interaction is deliberately conservative: never logs in, enters
    personal data, accepts payments or changes account settings.
    """

    DEMO_PROMPT = "Create a 5-slide presentation about renewable energy for students"

    def __init__(
        self,
        pexels: PexelsVideoProvider,
        *,
        brand_name: str = "ByteVexa",
        facts_mode: bool = False,
    ):
        self.pexels = pexels
        self.brand_name = brand_name
        self.facts_mode = facts_mode

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
        used_source_media: set[str] = set()

        for scene_index, scene in enumerate(scenes[:limit]):
            asset: VisualAsset | None = None

            if scene.visual_mode == "ui":
                source_url = scene.source_url if scene.source_url in allowed else ""
                if source_url:
                    asset = self._capture_public_ui(
                        source_url,
                        output_dir / f"scene-{scene_index:02d}-ui",
                        scene=scene,
                        scene_index=scene_index,
                        vertical=vertical,
                    )

            if asset is None and scene.visual_mode == "stock":
                stock = []
                for query in self._stock_queries(scene):
                    stock = self.pexels.fetch_assets(
                        [query],
                        output_dir / "stock",
                        vertical=vertical,
                        limit=1,
                    )
                    if stock:
                        break
                if stock:
                    asset = stock[0].model_copy(
                        update={
                            "scene_index": scene_index,
                            "visual_mode": "stock",
                            "asset_kind": "video",
                        }
                    )

            # Fact Shorts should move. Primary-source stills are excellent proof,
            # but using one for every beat produces a slideshow. Prefer a tightly
            # matched real clip for action beats and keep authority media as the
            # evidence/fallback layer.
            if asset is None and self.facts_mode:
                asset = self._fetch_authoritative_image(
                    scene,
                    sorted(allowed),
                    output_dir / f"scene-{scene_index:02d}-source.jpg",
                    scene_index=scene_index,
                    used_urls=used_source_media,
                )

            if asset is None:
                card = output_dir / f"scene-{scene_index:02d}-motion.png"
                self._make_visual_explainer(scene, card, vertical=vertical, scene_index=scene_index)
                asset = VisualAsset(
                    local_path=card,
                    query=scene.visual_query,
                    scene_index=scene_index,
                    asset_kind="image",
                    visual_mode="motion",
                )

            assets.append(asset)

        return assets

    def _fetch_authoritative_image(
        self,
        scene: SceneBeat,
        source_pages: list[str],
        output: Path,
        *,
        scene_index: int,
        used_urls: set[str],
    ) -> VisualAsset | None:
        """Use real media embedded by an approved primary source."""
        requested_domain = urlparse(scene.source_url).netloc.lower().removeprefix("www.")
        ordered = sorted(
            source_pages,
            key=lambda url: requested_domain not in urlparse(url).netloc.lower(),
        )
        terms = {
            token
            for token in re.findall(
                r"[a-z0-9]+", f"{scene.visual_query} {scene.narration}".lower()
            )
            if len(token) >= 4
            and token not in {"with", "from", "this", "that", "into", "footage", "cinematic"}
        }

        for page_url in ordered:
            try:
                response = httpx.get(
                    page_url,
                    timeout=20,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
            except Exception:
                continue

            candidates: list[tuple[int, str]] = []
            og = soup.find("meta", attrs={"property": "og:image"})
            if og and og.get("content"):
                candidates.append((1, urljoin(page_url, str(og["content"]))))
            for node in soup.find_all("img"):
                raw = node.get("src") or node.get("data-src") or node.get("data-lazy-src")
                if not raw:
                    continue
                media_url = urljoin(page_url, str(raw))
                label = " ".join(
                    str(node.get(name) or "") for name in ("alt", "title", "src")
                ).lower()
                candidates.append((sum(term in label for term in terms), media_url))

            for _, media_url in sorted(candidates, key=lambda item: item[0], reverse=True):
                if media_url in used_urls or media_url.lower().endswith((".svg", ".gif")):
                    continue
                try:
                    media = httpx.get(
                        media_url,
                        timeout=30,
                        follow_redirects=True,
                        headers={"User-Agent": "Mozilla/5.0"},
                    )
                    media.raise_for_status()
                    if not media.headers.get("content-type", "").startswith("image/"):
                        continue
                    output.write_bytes(media.content)
                    with Image.open(output) as image:
                        width, height = image.size
                        if width < 640 or height < 360:
                            output.unlink(missing_ok=True)
                            continue
                        image.convert("RGB").save(output, "JPEG", quality=94)
                    used_urls.add(media_url)
                    return VisualAsset(
                        local_path=output,
                        source_page_url=page_url,
                        creator=urlparse(page_url).netloc,
                        query=scene.visual_query,
                        scene_index=scene_index,
                        asset_kind="image",
                        visual_mode="ui",
                    )
                except Exception:
                    output.unlink(missing_ok=True)
                    continue
        return None

    def _capture_public_ui(
        self,
        url: str,
        output_stem: Path,
        *,
        scene: SceneBeat,
        scene_index: int,
        vertical: bool,
    ) -> VisualAsset | None:
        """Record a specific public product surface, never an authenticated session.

        Each tool-review stage is captured separately.  This produces a real
        guided walkthrough rather than replaying the hero section as a generic
        slide background.
        """
        video_output = output_stem.with_suffix(".webm")
        screenshot_output = output_stem.with_suffix(".png")
        raw = output_stem.with_name(output_stem.name + "-raw.png")
        video_dir = output_stem.parent / "browser-recordings"
        video_dir.mkdir(parents=True, exist_ok=True)

        try:
            from playwright.sync_api import sync_playwright

            width, height = (1080, 1920) if vertical else (1920, 1080)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    record_video_dir=str(video_dir),
                    record_video_size={"width": width, "height": height},
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1200)
                self._dismiss_cookie_banner(page)
                capture_stage = self._capture_stage(scene)
                captured_stage = self._capture_stage_surface(page, scene, capture_stage)
                page.screenshot(path=str(raw), full_page=False)

                recorded_path = page.video.path() if page.video else None
                context.close()
                browser.close()

            if recorded_path and Path(recorded_path).exists():
                shutil.copyfile(recorded_path, video_output)
                raw.unlink(missing_ok=True)
                return VisualAsset(
                    local_path=video_output,
                    source_page_url=url,
                    creator=urlparse(url).netloc,
                    query="public product feature demo recording",
                    scene_index=scene_index,
                    asset_kind="video",
                    visual_mode="ui",
                    capture_stage=captured_stage,
                )

            if raw.exists():
                self._frame_browser_capture(raw, screenshot_output, url=url, vertical=vertical)
                raw.unlink(missing_ok=True)
                return VisualAsset(
                    local_path=screenshot_output,
                    source_page_url=url,
                    creator=urlparse(url).netloc,
                    query="public product interface",
                    scene_index=scene_index,
                    asset_kind="image",
                    visual_mode="ui",
                    capture_stage=captured_stage,
                )
        except Exception:
            pass

        raw.unlink(missing_ok=True)
        video_output.unlink(missing_ok=True)
        screenshot_output.unlink(missing_ok=True)
        return None

    @staticmethod
    def _dismiss_cookie_banner(page) -> None:
        labels = ["Accept", "Accept all", "Allow all", "Got it", "OK"]
        for label in labels:
            try:
                locator = page.get_by_role("button", name=re.compile(rf"^{re.escape(label)}$", re.I))
                if locator.count() and locator.first.is_visible():
                    locator.first.click(timeout=900)
                    page.wait_for_timeout(250)
                    return
            except Exception:
                continue

    @staticmethod
    def _capture_stage(scene: SceneBeat) -> str:
        text = f"{scene.purpose} {scene.on_screen_text} {scene.visual_query}".lower()
        stages = (
            ("signup", ("signup", "sign up", "get started", "access")),
            ("pricing", ("pricing", "price", "free", "trial", "plan", "availability")),
            ("output", ("output", "result", "generated", "preview")),
            ("workflow", ("workflow", "demo", "flow", "input", "action")),
            ("main", ("main", "dashboard", "workspace", "editor", "product")),
            ("feature", ("feature", "how it works", "capability")),
        )
        return next((stage for stage, terms in stages if any(term in text for term in terms)), "feature")

    def _capture_stage_surface(self, page, scene: SceneBeat, stage: str) -> str:
        """Focus one public stage and return it only when the stage is visible."""
        if stage == "signup":
            return "signup" if self._show_public_surface(
                page, ("Sign up", "Get started", "Start free", "Try for free"), navigate=False
            ) else ""
        if stage == "pricing":
            return "pricing" if self._show_public_surface(
                page, ("Pricing", "Plans", "Free", "Trial"), navigate=True
            ) else ""
        if stage == "main":
            return "main" if self._show_public_surface(
                page, ("Dashboard", "Workspace", "Editor", "Product", "App"), navigate=False
            ) else ""
        if stage == "feature":
            return "feature" if self._show_relevant_section(page, scene) else ""
        if stage == "workflow":
            self._show_relevant_section(page, scene)
            if self._try_public_demo(page, scene):
                page.wait_for_timeout(4500)
                return "workflow"
            return ""
        if stage == "output":
            self._show_relevant_section(page, scene)
            if self._try_public_demo(page, scene):
                page.wait_for_timeout(4500)
                return "output" if self._show_result_area(page) else ""
            # A template gallery is useful supporting footage, but it is not a
            # live output.  Keep the tool-review gate honest by refusing to
            # count it as one.
            self._show_examples_or_results(page)
            return ""
        return ""

    def _show_public_surface(self, page, hints: tuple[str, ...], *, navigate: bool) -> bool:
        """Focus public navigation/section text without ever signing in or buying."""
        for hint in hints:
            for role in ("link", "button"):
                try:
                    target = page.get_by_role(role, name=re.compile(rf"{re.escape(hint)}", re.I)).first
                    if not target.count() or not target.is_visible():
                        continue
                    target.scroll_into_view_if_needed(timeout=1200)
                    if navigate and role == "link":
                        href = target.get_attribute("href") or ""
                        if href and not any(term in hint.lower() for term in ("sign", "start", "free")):
                            target.click(timeout=1500)
                            page.wait_for_timeout(1100)
                    page.wait_for_timeout(800)
                    return True
                except Exception:
                    continue
        return False

    def _show_relevant_section(self, page, scene: SceneBeat) -> bool:
        hints = []
        joined = f"{scene.purpose} {scene.on_screen_text} {scene.visual_query} {scene.narration}".lower()
        if any(word in joined for word in ("result", "output", "example", "template")):
            hints += ["Examples", "Templates", "Results", "Gallery", "Showcase"]
        if any(word in joined for word in ("feature", "work", "how", "create", "generate")):
            hints += ["How it works", "Features", "Create", "Generate", "Demo"]
        hints += ["Features", "How it works", "Examples", "Templates"]

        for hint in dict.fromkeys(hints):
            try:
                target = page.get_by_text(re.compile(re.escape(hint), re.I)).first
                if target.count() and target.is_visible():
                    target.scroll_into_view_if_needed(timeout=1200)
                    page.wait_for_timeout(850)
                    return True
            except Exception:
                continue
        return False

    def _try_public_demo(self, page, scene: SceneBeat) -> bool:
        """Type into a clearly public generation field and click a safe create button.

        Abort if the page appears to require login/payment or if the only visible
        form field is sensitive.
        """
        try:
            body = page.locator("body").inner_text(timeout=1200).lower()
        except Exception:
            body = ""
        if any(term in body for term in ("sign in to continue", "log in to continue", "payment required")):
            return False

        candidates = [
            "textarea",
            "input[placeholder*='prompt' i]",
            "input[placeholder*='describe' i]",
            "input[placeholder*='topic' i]",
            "input[placeholder*='presentation' i]",
            "input[placeholder*='slide' i]",
            "[contenteditable='true']",
        ]
        field = None
        for selector in candidates:
            try:
                locator = page.locator(selector)
                for index in range(min(locator.count(), 4)):
                    item = locator.nth(index)
                    if not item.is_visible():
                        continue
                    input_type = (item.get_attribute("type") or "").lower()
                    if input_type in {"password", "email", "tel", "number"}:
                        continue
                    field = item
                    break
            except Exception:
                continue
            if field is not None:
                break
        if field is None:
            return False

        try:
            field.scroll_into_view_if_needed(timeout=1200)
            page.wait_for_timeout(500)
            field.click(timeout=1200)
            # Use a generic non-personal demo prompt suited to presentation tools.
            prompt = self.DEMO_PROMPT
            if "code" in scene.narration.lower():
                prompt = "Explain a simple Python loop with one example"
            elif "image" in scene.narration.lower():
                prompt = "A clean futuristic workspace with a laptop"
            field.fill("")
            field.type(prompt, delay=28)
            page.wait_for_timeout(850)
        except Exception:
            return False

        # Click only an obvious generation/creation button, never login/buy/save.
        button_patterns = [
            r"^generate$", r"^create$", r"generate slides", r"create presentation",
            r"make slides", r"generate presentation", r"^go$", r"^submit$",
        ]
        for pattern in button_patterns:
            try:
                button = page.get_by_role("button", name=re.compile(pattern, re.I)).first
                if button.count() and button.is_visible() and button.is_enabled():
                    label = (button.inner_text() or "").lower()
                    if any(bad in label for bad in ("sign in", "login", "upgrade", "buy", "subscribe")):
                        continue
                    button.click(timeout=1500)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _show_result_area(page) -> bool:
        for hint in ("Result", "Preview", "Generated", "Presentation", "Slides", "Output"):
            try:
                target = page.get_by_text(re.compile(hint, re.I)).first
                if target.count() and target.is_visible():
                    target.scroll_into_view_if_needed(timeout=1000)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    def _show_examples_or_results(page) -> bool:
        for hint in ("Examples", "Templates", "Gallery", "Showcase", "Results", "Preview"):
            try:
                target = page.get_by_text(re.compile(hint, re.I)).first
                if target.count() and target.is_visible():
                    target.scroll_into_view_if_needed(timeout=1100)
                    return True
            except Exception:
                continue
        try:
            page.evaluate("window.scrollBy({top: Math.min(window.innerHeight * 0.75, 950), behavior: 'smooth'})")
        except Exception:
            return False
        return False

    def _frame_browser_capture(self, raw: Path, output: Path, *, url: str, vertical: bool) -> None:
        width, height = (1080, 1920) if vertical else (1920, 1080)
        canvas = Image.new("RGB", (width, height), (8, 12, 24))
        draw = ImageDraw.Draw(canvas)
        capture = Image.open(raw).convert("RGB")

        margin = int(width * 0.055)
        top = int(height * (0.13 if vertical else 0.10))
        available_w = width - margin * 2
        available_h = int(height * (0.70 if vertical else 0.76))
        capture.thumbnail((available_w, available_h), Image.Resampling.LANCZOS)
        left = (width - capture.width) // 2
        y = top + (available_h - capture.height) // 2

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

        brand_font = self._font(26 if vertical else 28, bold=True)
        domain_font = self._font(22 if vertical else 21)
        draw.text((margin, 45), "BYTEVEXA", font=brand_font, fill=(119, 255, 166))
        domain = urlparse(url).netloc.removeprefix("www.")[:45]
        draw.text((margin, 92), domain, font=domain_font, fill=(206, 213, 226))
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output, quality=94)

    def _make_visual_explainer(
        self,
        scene: SceneBeat,
        output: Path,
        *,
        vertical: bool,
        scene_index: int,
    ) -> None:
        """Create a varied, high-contrast mini-demo rather than a text-heavy card.

        The presenter captions already carry the narration.  These frames reserve
        text for one short emphasis and use the rest of the canvas for visual proof,
        comparisons and product-like interaction cues.
        """
        width, height = (1080, 1920) if vertical else (1920, 1080)
        image = Image.new("RGB", (width, height), (10, 15, 28))
        draw = ImageDraw.Draw(image)
        margin = int(width * 0.065)

        if self.facts_mode:
            self._make_fact_explainer(image, draw, scene, output, vertical=vertical, scene_index=scene_index)
            return

        role, theme = self._bytevexa_theme(scene, scene_index)
        base, surface, accent, secondary, muted = theme

        # A different palette is selected for each story beat.  It deliberately
        # avoids the old repeated blue information banner.
        for y in range(0, height, 8):
            mix = y / max(1, height)
            colour = tuple(round(base[channel] * (1 - mix) + surface[channel] * mix) for channel in range(3))
            draw.rectangle((0, y, width, min(height, y + 8)), fill=colour)
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((-width // 3, int(height * 0.12), int(width * 0.62), int(height * 0.72)), fill=(*accent, 72))
        glow_draw.ellipse((int(width * 0.46), int(height * 0.48), width + width // 3, height + height // 5), fill=(*secondary, 62))
        image = Image.alpha_composite(image.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(85))).convert("RGB")
        draw = ImageDraw.Draw(image)

        brand_font = self._font(24 if vertical else 27, bold=True)
        small_font = self._font(21 if vertical else 23, bold=True)
        label_font = self._font(48 if vertical else 54, bold=True)
        chrome = (241, 245, 250)
        panel = tuple(min(255, value + 12) for value in surface)
        dim_panel = tuple(max(0, value - 8) for value in surface)

        draw.text((margin, int(height * 0.075)), self.brand_name.upper(), font=brand_font, fill=chrome)
        draw.rounded_rectangle(
            (width - margin - 122, int(height * 0.072), width - margin, int(height * 0.112)),
            radius=18,
            fill=(*accent, 232),
        )
        draw.text((width - margin - 92, int(height * 0.079)), f"{scene_index + 1:02d}", font=small_font, fill=base)

        # One compact, single-line emphasis: never a transcript or a persistent
        # multi-line banner.  Spoken captions are rendered separately at the bottom.
        label = self._visual_label(scene).upper()
        label_box_top = int(height * 0.155)
        label_box_bottom = label_box_top + int(height * 0.078)
        draw.rounded_rectangle(
            (margin, label_box_top, width - margin, label_box_bottom),
            radius=30,
            fill=(7, 10, 18),
            outline=(*accent, 205),
            width=3,
        )
        bbox = draw.textbbox((0, 0), label, font=label_font)
        label_width = bbox[2] - bbox[0]
        while label_width > width - margin * 2 - 52 and label_font.size > 30:
            label_font = self._font(label_font.size - 2, bold=True)
            bbox = draw.textbbox((0, 0), label, font=label_font)
            label_width = bbox[2] - bbox[0]
        label_y = label_box_top + (label_box_bottom - label_box_top - (bbox[3] - bbox[1])) // 2 - bbox[1]
        draw.text(((width - label_width) // 2, label_y), label, font=label_font, fill=chrome)

        canvas_top = int(height * 0.29)
        canvas_bottom = int(height * 0.77)
        canvas_left = margin
        canvas_right = width - margin
        if role == "comparison":
            self._draw_comparison_canvas(
                draw, canvas_left, canvas_top, canvas_right, canvas_bottom,
                accent=accent, secondary=secondary, panel=panel, dim_panel=dim_panel, text=chrome,
            )
        elif role == "limitation":
            self._draw_caution_canvas(
                draw, canvas_left, canvas_top, canvas_right, canvas_bottom,
                accent=accent, secondary=secondary, panel=panel, text=chrome,
            )
        elif role == "result":
            self._draw_result_canvas(
                draw, canvas_left, canvas_top, canvas_right, canvas_bottom,
                accent=accent, secondary=secondary, panel=panel, dim_panel=dim_panel, text=chrome,
            )
        else:
            self._draw_workflow_canvas(
                draw, canvas_left, canvas_top, canvas_right, canvas_bottom,
                accent=accent, secondary=secondary, panel=panel, dim_panel=dim_panel, text=chrome,
                scene_index=scene_index,
            )

        # Tiny progress markers make the sequence feel tactile without turning
        # every scene into a branded lower-third.
        dot_y = int(height * 0.84)
        for index in range(5):
            x = width // 2 - 72 + index * 36
            colour = accent if index == scene_index % 5 else muted
            draw.ellipse((x - 7, dot_y - 7, x + 7, dot_y + 7), fill=colour)

        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, quality=96)

    def _bytevexa_theme(
        self,
        scene: SceneBeat,
        scene_index: int,
    ) -> tuple[str, tuple[tuple[int, int, int], ...]]:
        """Return a purposeful visual role and a non-repeating colour theme."""
        purpose = self._clean(scene.purpose).lower()
        if any(word in purpose for word in ("comparison", "versus", "decision", "alternative", "pros", "cons")):
            role = "comparison"
        elif any(word in purpose for word in ("limit", "catch", "risk", "warning", "caveat")):
            role = "limitation"
        elif any(word in purpose for word in ("proof", "result", "output", "evidence", "reveal")):
            role = "result"
        else:
            role = "workflow"

        themes = {
            "workflow": ((12, 15, 22), (31, 25, 48), (148, 255, 107), (255, 151, 71), (118, 124, 145)),
            "comparison": ((18, 13, 30), (39, 25, 54), (213, 123, 255), (99, 255, 195), (140, 126, 158)),
            "limitation": ((29, 16, 12), (58, 29, 22), (255, 181, 61), (255, 93, 93), (161, 130, 111)),
            "result": ((13, 22, 20), (22, 46, 40), (70, 243, 188), (255, 211, 92), (119, 153, 143)),
        }
        # Rotate accent variants so adjacent general workflow beats do not look cloned.
        if role == "workflow" and scene_index % 3 == 2:
            themes["workflow"] = ((18, 16, 29), (42, 28, 54), (247, 118, 193), (117, 226, 255), (142, 133, 159))
        return role, themes[role]

    def _draw_workflow_canvas(
        self,
        draw: ImageDraw.ImageDraw,
        left: int,
        top: int,
        right: int,
        bottom: int,
        *,
        accent: tuple[int, int, int],
        secondary: tuple[int, int, int],
        panel: tuple[int, int, int],
        dim_panel: tuple[int, int, int],
        text: tuple[int, int, int],
        scene_index: int,
    ) -> None:
        """Draw a product-like action canvas with changing controls and outcomes."""
        draw.rounded_rectangle((left, top, right, bottom), radius=46, fill=panel, outline=accent, width=4)
        header_bottom = top + int((bottom - top) * 0.16)
        draw.rounded_rectangle((left + 28, top + 28, right - 28, header_bottom), radius=24, fill=dim_panel)
        for offset, colour in ((0, accent), (28, secondary), (56, text)):
            draw.ellipse((left + 52 + offset, top + 53, left + 68 + offset, top + 69), fill=colour)
        draw.rounded_rectangle((left + 52, header_bottom + 44, right - 52, header_bottom + 134), radius=24, fill=(9, 12, 19))
        for index, ratio in enumerate((0.76, 0.48, 0.64)):
            y = header_bottom + 68 + index * 20
            draw.rounded_rectangle((left + 82, y, left + 82 + int((right - left - 180) * ratio), y + 8), radius=4, fill=(104, 116, 139))

        card_top = header_bottom + 180
        card_gap = 22
        card_width = (right - left - 104 - card_gap * 2) // 3
        for index in range(3):
            x = left + 52 + index * (card_width + card_gap)
            tint = accent if index == scene_index % 3 else secondary
            draw.rounded_rectangle((x, card_top, x + card_width, card_top + int((bottom - card_top) * 0.52)), radius=25, fill=dim_panel)
            draw.rounded_rectangle((x + 20, card_top + 20, x + card_width - 20, card_top + 34), radius=7, fill=tint)
            draw.ellipse((x + 28, card_top + 65, x + 72, card_top + 109), fill=(*tint,))
            for row, ratio in enumerate((0.72, 0.50, 0.63)):
                y = card_top + 132 + row * 18
                draw.rounded_rectangle((x + 24, y, x + 24 + int((card_width - 48) * ratio), y + 7), radius=4, fill=(125, 135, 153))

        button_width = min(260, int((right - left) * 0.34))
        button_left = (left + right - button_width) // 2
        button_top = bottom - 115
        draw.rounded_rectangle((button_left, button_top, button_left + button_width, button_top + 58), radius=25, fill=accent)
        play_x = button_left + button_width // 2
        draw.polygon([(play_x - 8, button_top + 17), (play_x - 8, button_top + 41), (play_x + 14, button_top + 29)], fill=(10, 12, 18))

    def _draw_comparison_canvas(
        self,
        draw: ImageDraw.ImageDraw,
        left: int,
        top: int,
        right: int,
        bottom: int,
        *,
        accent: tuple[int, int, int],
        secondary: tuple[int, int, int],
        panel: tuple[int, int, int],
        dim_panel: tuple[int, int, int],
        text: tuple[int, int, int],
    ) -> None:
        gap = 26
        card_width = (right - left - gap) // 2
        for index, colour in enumerate((secondary, accent)):
            x = left + index * (card_width + gap)
            draw.rounded_rectangle((x, top, x + card_width, bottom), radius=42, fill=panel, outline=colour, width=5)
            draw.rounded_rectangle((x + 30, top + 34, x + card_width - 30, top + 55), radius=10, fill=colour)
            heading = "PROS" if index == 0 else "CONS"
            heading_font = self._font(34, bold=True)
            heading_box = draw.textbbox((0, 0), heading, font=heading_font)
            heading_width = heading_box[2] - heading_box[0]
            draw.text(
                (x + (card_width - heading_width) // 2, top + 78),
                heading,
                font=heading_font,
                fill=text,
            )
            circle_y = top + int((bottom - top) * 0.33)
            draw.ellipse((x + card_width // 2 - 74, circle_y - 74, x + card_width // 2 + 74, circle_y + 74), fill=dim_panel, outline=colour, width=5)
            if index == 0:
                draw.line((x + card_width // 2 - 35, circle_y, x + card_width // 2 + 35, circle_y), fill=colour, width=10)
            else:
                draw.polygon(
                    [(x + card_width // 2 - 24, circle_y - 36), (x + card_width // 2 + 42, circle_y), (x + card_width // 2 - 24, circle_y + 36)],
                    fill=colour,
                )
            for row, ratio in enumerate((0.70, 0.44, 0.60)):
                y = top + int((bottom - top) * 0.66) + row * 28
                draw.rounded_rectangle((x + 44, y, x + 44 + int((card_width - 88) * ratio), y + 10), radius=5, fill=text if row == 0 else (132, 139, 157))

    def _draw_caution_canvas(
        self,
        draw: ImageDraw.ImageDraw,
        left: int,
        top: int,
        right: int,
        bottom: int,
        *,
        accent: tuple[int, int, int],
        secondary: tuple[int, int, int],
        panel: tuple[int, int, int],
        text: tuple[int, int, int],
    ) -> None:
        draw.rounded_rectangle((left, top, right, bottom), radius=46, fill=panel, outline=secondary, width=5)
        cx = (left + right) // 2
        cy = top + int((bottom - top) * 0.37)
        triangle = [(cx, cy - 148), (cx - 152, cy + 122), (cx + 152, cy + 122)]
        draw.polygon(triangle, fill=accent)
        draw.rounded_rectangle((cx - 13, cy - 66, cx + 13, cy + 35), radius=8, fill=(27, 19, 14))
        draw.ellipse((cx - 13, cy + 64, cx + 13, cy + 90), fill=(27, 19, 14))
        for row, ratio in enumerate((0.76, 0.55, 0.68)):
            y = top + int((bottom - top) * 0.70) + row * 30
            x2 = left + int((right - left) * (0.12 + ratio * 0.76))
            draw.rounded_rectangle((left + int((right - left) * 0.12), y, x2, y + 11), radius=5, fill=text if row == 0 else (170, 145, 126))
        draw.ellipse((right - 102, top + 62, right - 62, top + 102), outline=secondary, width=5)
        draw.line((right - 82, top + 73, right - 82, top + 91), fill=secondary, width=5)

    def _draw_result_canvas(
        self,
        draw: ImageDraw.ImageDraw,
        left: int,
        top: int,
        right: int,
        bottom: int,
        *,
        accent: tuple[int, int, int],
        secondary: tuple[int, int, int],
        panel: tuple[int, int, int],
        dim_panel: tuple[int, int, int],
        text: tuple[int, int, int],
    ) -> None:
        draw.rounded_rectangle((left, top, right, bottom), radius=46, fill=panel, outline=accent, width=5)
        cx = (left + right) // 2
        cy = top + int((bottom - top) * 0.30)
        draw.ellipse((cx - 122, cy - 122, cx + 122, cy + 122), fill=dim_panel, outline=accent, width=8)
        draw.line((cx - 55, cy + 2, cx - 12, cy + 47), fill=accent, width=18)
        draw.line((cx - 12, cy + 47, cx + 72, cy - 55), fill=accent, width=18)
        bar_left = left + 66
        bar_right = right - 66
        for index, ratio in enumerate((0.88, 0.62, 0.76)):
            y = top + int((bottom - top) * 0.59) + index * 58
            draw.rounded_rectangle((bar_left, y, bar_right, y + 22), radius=11, fill=(16, 20, 28))
            draw.rounded_rectangle((bar_left, y, bar_left + int((bar_right - bar_left) * ratio), y + 22), radius=11, fill=accent if index != 1 else secondary)
        for index in range(3):
            x = left + 78 + index * int((right - left - 156) / 2)
            draw.ellipse((x - 10, bottom - 86, x + 10, bottom - 66), fill=text if index == 0 else (123, 142, 143))

    @staticmethod
    def _visual_label(scene: SceneBeat) -> str:
        """Keep overlay copy short enough to be a visual emphasis, not a banner."""
        raw = HybridVisualDirector._clean(scene.on_screen_text) or HybridVisualDirector._headline_from_narration(scene.narration)
        words = raw.replace("\n", " ").split()[:4]
        label = " ".join(words).strip(" .,:;!?")
        return label[:32] or "SEE THE MOVE"

    def _make_fact_explainer(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        scene: SceneBeat,
        output: Path,
        *,
        vertical: bool,
        scene_index: int,
    ) -> None:
        """Draw a cinematic scientific schematic, never a software-style slide."""
        width, height = image.size
        margin = int(width * 0.07)
        text = f"{scene.narration} {scene.visual_query}".lower()

        # Atmospheric depth and a bright physical focal point.
        draw.ellipse((-width // 2, height // 3, width + width // 2, height + height // 2), fill=(8, 35, 62))
        draw.arc((-width // 3, height // 4, width + width // 3, height + height // 3), 195, 345, fill=(40, 132, 190), width=10)
        center_x, center_y = width // 2, int(height * 0.53)

        if any(term in text for term in ("heat", "reentry", "plasma", "shockwave", "compression")):
            # Blunt capsule plus detached bow shock and incoming air particles.
            capsule = [
                (center_x - 150, center_y - 130),
                (center_x + 150, center_y - 130),
                (center_x + 205, center_y + 75),
                (center_x, center_y + 155),
                (center_x - 205, center_y + 75),
            ]
            draw.polygon(capsule, fill=(203, 211, 218), outline=(255, 247, 220))
            draw.arc((center_x - 320, center_y - 310, center_x + 320, center_y + 340), 195, 345, fill=(255, 112, 35), width=30)
            draw.arc((center_x - 365, center_y - 350, center_x + 365, center_y + 385), 195, 345, fill=(255, 205, 74), width=8)
            for row in range(5):
                y = center_y - 240 + row * 95
                draw.line((margin, y, center_x - 300, y), fill=(93, 180, 222), width=5)
                draw.polygon([(center_x - 300, y), (center_x - 330, y - 12), (center_x - 330, y + 12)], fill=(93, 180, 222))
        else:
            radius = int(width * 0.20)
            draw.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius), fill=(36, 104, 143), outline=(125, 220, 245), width=8)
            for offset in (-210, -105, 105, 210):
                draw.arc((center_x - radius - abs(offset), center_y - radius // 2 + offset, center_x + radius + abs(offset), center_y + radius // 2 + offset), 200, 340, fill=(67, 159, 196), width=5)

        brand_font = self._font(27 if vertical else 30, bold=True)
        kicker_font = self._font(24 if vertical else 25, bold=True)
        headline_font = self._font(48 if vertical else 52, bold=True)
        draw.text((margin, int(height * 0.07)), self.brand_name.upper(), font=brand_font, fill=(111, 224, 245))
        draw.text((margin, int(height * 0.12)), self._clean(scene.purpose).upper()[:24], font=kicker_font, fill=(255, 166, 69))
        headline = self._clean(scene.on_screen_text) or self._headline_from_narration(scene.narration)
        y = int(height * 0.17)
        for line in self._wrap(headline, 24 if vertical else 38, max_lines=2):
            draw.text((margin, y), line, font=headline_font, fill=(247, 250, 252))
            y += int(headline_font.size * 1.15)

        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, quality=95)

    def _input_label(self, scene: SceneBeat) -> str:
        text = f"{scene.narration} {scene.visual_query}".lower()
        if "slide" in text or "presentation" in text:
            return self.DEMO_PROMPT
        if "image" in text:
            return "Describe the image you want to create"
        if "code" in text:
            return "Explain a simple Python loop"
        if "summar" in text or "pdf" in text:
            return "Upload document → ask for concise summary"
        return "Describe the task in one clear prompt"

    def _stock_queries(self, scene: SceneBeat) -> list[str]:
        primary = self._clean(scene.visual_query)
        if not self.facts_mode:
            return [primary]
        text = f"{scene.narration} {primary}".lower()
        fallbacks: list[str] = []
        keyword_queries = (
            (("reentry", "spacecraft", "capsule"), "space capsule spacecraft"),
            (("heat", "fire", "plasma"), "extreme heat flames"),
            (("rocket", "space"), "rocket in space"),
            (("parachute", "landing"), "parachute landing sky"),
            (("race", "formula", "car"), "race car track"),
            (("engine", "automobile"), "car engine close up"),
            (("ocean", "river"), "aerial ocean landscape"),
            (("ancient", "history"), "ancient ruins archaeology"),
        )
        for terms, query in keyword_queries:
            if any(term in text for term in terms):
                fallbacks.append(query)
        return list(dict.fromkeys([primary, *fallbacks]))

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
        lines = textwrap.wrap(
            text,
            width=max(8, width),
            break_long_words=False,
            break_on_hyphens=False,
        )
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
