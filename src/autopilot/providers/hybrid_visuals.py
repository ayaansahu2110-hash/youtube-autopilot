from __future__ import annotations

import re
import shutil
import textwrap
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

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

            if asset is None and self.facts_mode:
                asset = self._fetch_authoritative_image(
                    scene,
                    sorted(allowed),
                    output_dir / f"scene-{scene_index:02d}-source.jpg",
                    scene_index=scene_index,
                    used_urls=used_source_media,
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
        """Record a richer public UI sequence, then fall back to a framed screenshot."""
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
                page.screenshot(path=str(raw), full_page=False)

                # 1) Start with the actual product page.
                page.wait_for_timeout(700)

                # 2) Show a relevant feature/examples/how-it-works section instead
                # of repeating only the hero landing page.
                if not self._show_relevant_section(page, scene):
                    page.evaluate(
                        "window.scrollBy({top: Math.min(window.innerHeight * 0.65, 850), behavior: 'smooth'})"
                    )
                    page.wait_for_timeout(1200)

                # 3) When a public no-login input exists, demonstrate a harmless
                # generic prompt. This creates real typing footage for tools like
                # slide generators without using private information.
                demo_started = self._try_public_demo(page, scene)
                if demo_started:
                    page.wait_for_timeout(4500)
                    self._show_result_area(page)
                    page.wait_for_timeout(1800)
                else:
                    # 4) If no interactive demo is available, deliberately show
                    # examples/templates/results rather than another hero shot.
                    self._show_examples_or_results(page)
                    page.wait_for_timeout(1600)

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
    def _show_result_area(page) -> None:
        for hint in ("Result", "Preview", "Generated", "Presentation", "Slides", "Output"):
            try:
                target = page.get_by_text(re.compile(hint, re.I)).first
                if target.count() and target.is_visible():
                    target.scroll_into_view_if_needed(timeout=1000)
                    return
            except Exception:
                continue

    @staticmethod
    def _show_examples_or_results(page) -> None:
        for hint in ("Examples", "Templates", "Gallery", "Showcase", "Results", "Preview"):
            try:
                target = page.get_by_text(re.compile(hint, re.I)).first
                if target.count() and target.is_visible():
                    target.scroll_into_view_if_needed(timeout=1100)
                    return
            except Exception:
                continue
        try:
            page.evaluate("window.scrollBy({top: Math.min(window.innerHeight * 0.75, 950), behavior: 'smooth'})")
        except Exception:
            pass

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
        """Create a graphic mini-demo, not a black text poster."""
        width, height = (1080, 1920) if vertical else (1920, 1080)
        image = Image.new("RGB", (width, height), (10, 15, 28))
        draw = ImageDraw.Draw(image)
        margin = int(width * 0.065)

        if self.facts_mode:
            self._make_fact_explainer(image, draw, scene, output, vertical=vertical, scene_index=scene_index)
            return

        # Decorative depth so the fallback still feels like a designed tech short.
        draw.ellipse((-180, 50, 520, 750), fill=(20, 55, 70))
        draw.ellipse((width - 430, height - 720, width + 180, height - 100), fill=(34, 28, 70))
        draw.rounded_rectangle(
            (margin, int(height * 0.10), width - margin, int(height * 0.84)),
            radius=40,
            fill=(18, 25, 42),
            outline=(57, 74, 100),
            width=3,
        )

        brand_font = self._font(27 if vertical else 30, bold=True)
        kicker_font = self._font(24 if vertical else 24, bold=True)
        headline_font = self._font(48 if vertical else 48, bold=True)
        small_font = self._font(25 if vertical else 24)
        ui_font = self._font(27 if vertical else 26, bold=True)

        draw.text((margin + 40, int(height * 0.13)), self.brand_name.upper(), font=brand_font, fill=(119, 255, 166))
        purpose = self._clean(scene.purpose).upper()[:24] or "HOW IT WORKS"
        draw.text((margin + 40, int(height * 0.18)), purpose, font=kicker_font, fill=(137, 151, 177))

        headline = self._clean(scene.on_screen_text) or self._headline_from_narration(scene.narration)
        y = int(height * 0.23)
        for line in self._wrap(headline, 24 if vertical else 34, max_lines=2):
            draw.text((margin + 40, y), line, font=headline_font, fill=(247, 249, 252))
            y += int(headline_font.size * 1.15)

        # Mini product-workflow mockup: INPUT -> PROCESS -> OUTPUT.
        box_left = margin + 42
        box_right = width - margin - 42
        box_w = box_right - box_left
        top = int(height * 0.39)
        input_h = int(height * 0.12)
        output_h = int(height * 0.17)

        draw.rounded_rectangle((box_left, top, box_right, top + input_h), radius=24, fill=(27, 35, 56))
        draw.text((box_left + 24, top + 18), "INPUT", font=kicker_font, fill=(119, 255, 166))
        prompt = self._input_label(scene)
        for idx, line in enumerate(self._wrap(prompt, 42 if vertical else 64, max_lines=2)):
            draw.text((box_left + 24, top + 58 + idx * 34), line, font=small_font, fill=(222, 228, 238))

        mid_y = top + input_h + 52
        draw.line((box_left + 30, mid_y, box_right - 30, mid_y), fill=(65, 82, 110), width=4)
        cx = box_left + box_w // 2
        draw.polygon([(cx, mid_y + 20), (cx - 16, mid_y - 6), (cx + 16, mid_y - 6)], fill=(119, 255, 166))

        out_top = mid_y + 46
        draw.rounded_rectangle((box_left, out_top, box_right, out_top + output_h), radius=24, fill=(24, 31, 48))
        draw.text((box_left + 24, out_top + 18), "OUTPUT", font=kicker_font, fill=(119, 255, 166))

        # Draw three compact result cards to imply generated slides/results.
        card_gap = 16
        card_w = (box_w - card_gap * 2 - 48) // 3
        card_y = out_top + 66
        for i in range(3):
            x1 = box_left + 18 + i * (card_w + card_gap)
            x2 = x1 + card_w
            draw.rounded_rectangle((x1, card_y, x2, card_y + int(output_h * 0.48)), radius=16, fill=(38, 48, 70))
            draw.rectangle((x1 + 12, card_y + 12, x2 - 12, card_y + 30), fill=(119, 255, 166))
            draw.rectangle((x1 + 12, card_y + 43, x2 - 24, card_y + 53), fill=(105, 118, 144))
            draw.rectangle((x1 + 12, card_y + 63, x2 - 38, card_y + 73), fill=(79, 92, 118))

        footer = self._clean(scene.narration)
        footer_y = int(height * 0.76)
        for idx, line in enumerate(self._wrap(footer, 48 if vertical else 76, max_lines=2)):
            draw.text((margin + 40, footer_y + idx * 34), line, font=small_font, fill=(180, 190, 208))

        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, quality=95)

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
