from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


class ThumbnailGenerator:
    def create(
        self,
        text: str,
        output_path: Path,
        *,
        title: str = "",
        brief: str = "",
        brand_name: str = "ByteVexa",
        facts_mode: bool = False,
        feature_image: Path | None = None,
    ) -> Path:
        """Create a high-contrast, channel-aware thumbnail with a real visual story."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if facts_mode:
            return self._create_fact_thumbnail(
                text,
                output_path,
                title=title,
                brand_name=brand_name,
                feature_image=feature_image,
            )
        width, height = 1280, 720
        primary, secondary = self._bytevexa_theme(f"{title} {brief} {text}")

        image = Image.new("RGB", (width, height), (8, 11, 20))
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((790, -120, 1390, 500), fill=(*primary, 105))
        glow_draw.ellipse((-230, 330, 430, 980), fill=(*secondary, 82))
        glow = glow.filter(ImageFilter.GaussianBlur(90))
        image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")
        draw = ImageDraw.Draw(image)

        # Small brand tag: recognizable, but never competes with the hook.
        brand_font = self._font(25)
        draw.rounded_rectangle((64, 50, 250, 96), radius=18, fill=(20, 30, 43))
        draw.text((84, 61), brand_name.upper()[:16], font=brand_font, fill=primary)

        display = (text or "WORTH TRYING?").upper().strip()[:34]
        lines = self._split_display(display)
        headline_size = 92 if len(lines) <= 2 else 76
        headline_font = self._font(headline_size)
        y = 180 if len(lines) <= 2 else 145
        for line in lines:
            draw.text(
                (68, y),
                line,
                font=headline_font,
                fill=(250, 252, 255),
                stroke_width=4,
                stroke_fill=(2, 4, 9),
            )
            y += headline_size + 16

        # Topic-aware right-side visual: a large premium mock AI/product window.
        panel = (790, 130, 1218, 600)
        draw.rounded_rectangle(panel, radius=34, fill=(18, 24, 38), outline=primary, width=3)
        draw.rounded_rectangle((818, 163, 1190, 209), radius=15, fill=(31, 39, 57))
        for cx, colour in ((842, (255, 96, 94)), (870, (255, 190, 55)), (898, (64, 218, 126))):
            draw.ellipse((cx - 7, 179, cx + 7, 193), fill=colour)

        topic = f"{title} {brief} {display}".lower()
        if any(word in topic for word in ("slide", "presentation", "deck")):
            self._draw_slides_mock(draw)
        elif any(word in topic for word in ("image", "video", "generate", "design")):
            self._draw_generation_mock(draw)
        elif any(word in topic for word in ("code", "developer", "coding", "agent")):
            self._draw_code_mock(draw)
        else:
            self._draw_ai_mock(draw)

        # Curiosity cue and separation line make the composition read instantly on mobile.
        draw.rounded_rectangle((742, 306, 797, 366), radius=20, fill=primary)
        arrow_font = self._font(38)
        draw.text((753, 310), "→", font=arrow_font, fill=(8, 13, 22))

        image.save(output_path, quality=96, optimize=True)
        return output_path

    @staticmethod
    def _bytevexa_theme(topic: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        """Give each thumbnail a topic-relevant accent instead of one generic look."""
        subject = topic.lower()
        if any(word in subject for word in ("security", "privacy", "scam", "risk", "hack")):
            return (255, 177, 63), (255, 88, 104)
        if any(word in subject for word in ("video", "image", "design", "creative", "animation")):
            return (250, 112, 187), (255, 190, 79)
        if any(word in subject for word in ("code", "developer", "coding", "agent", "mcp")):
            return (171, 124, 255), (105, 245, 191)
        return (116, 255, 165), (94, 181, 255)

    def _create_fact_thumbnail(
        self,
        text: str,
        output_path: Path,
        *,
        title: str,
        brand_name: str,
        feature_image: Path | None,
    ) -> Path:
        """Use the actual opening documentary visual, never a reused AI-app mockup."""
        width, height = 1280, 720
        image = self._cover_feature_image(feature_image, width, height)
        image = image.filter(ImageFilter.GaussianBlur(1.2))
        overlay = Image.new("RGBA", (width, height), (4, 8, 18, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        for x in range(width):
            alpha = int(220 * max(0, 1 - x / 920))
            overlay_draw.line((x, 0, x, height), fill=(3, 8, 18, alpha))
        overlay_draw.rectangle((0, 0, width, height), outline=(221, 184, 89, 90), width=4)
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(image)

        brand_font = self._font(24)
        draw.rounded_rectangle((58, 48, 330, 94), radius=16, fill=(7, 15, 28))
        draw.text((78, 59), brand_name.upper()[:16], font=brand_font, fill=(255, 218, 114))
        draw.rounded_rectangle((58, 112, 224, 147), radius=13, fill=(21, 45, 65))
        draw.text((75, 120), "VERIFIED FACT", font=self._font(18), fill=(221, 242, 255))

        display = (text or title or "THE REAL REASON").upper().strip()[:34]
        lines = self._split_display(display)
        headline_size = 90 if len(lines) <= 2 else 72
        y = 214 if len(lines) <= 2 else 188
        headline_font = self._font(headline_size)
        for line in lines:
            draw.text(
                (58, y), line, font=headline_font, fill=(255, 251, 239),
                stroke_width=5, stroke_fill=(2, 5, 11),
            )
            y += headline_size + 14

        # The gold cue is intentionally small: the factual visual remains the hook.
        draw.rounded_rectangle((58, 610, 410, 654), radius=16, fill=(255, 218, 114))
        draw.text((78, 619), "ONE QUESTION. REAL ANSWER.", font=self._font(18), fill=(8, 14, 24))
        image.save(output_path, quality=96, optimize=True)
        return output_path

    @staticmethod
    def _cover_feature_image(feature_image: Path | None, width: int, height: int) -> Image.Image:
        if feature_image:
            try:
                with Image.open(feature_image) as source:
                    source = source.convert("RGB")
                    scale = max(width / source.width, height / source.height)
                    resized = source.resize(
                        (round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS
                    )
                    left = max(0, (resized.width - width) // 2)
                    top = max(0, (resized.height - height) // 2)
                    return resized.crop((left, top, left + width, top + height))
            except (OSError, ValueError):
                pass
        image = Image.new("RGB", (width, height), (7, 15, 29))
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((690, -220, 1430, 520), fill=(37, 116, 178, 175))
        glow_draw.ellipse((830, 260, 1320, 800), fill=(229, 160, 56, 115))
        return Image.alpha_composite(image.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(100))).convert("RGB")

    def _draw_slides_mock(self, draw: ImageDraw.ImageDraw) -> None:
        draw.rounded_rectangle((830, 240, 1178, 500), radius=22, fill=(246, 248, 252))
        draw.rectangle((856, 270, 965, 470), fill=(92, 108, 255))
        draw.rectangle((990, 278, 1144, 304), fill=(24, 31, 45))
        draw.rectangle((990, 324, 1128, 340), fill=(130, 139, 158))
        draw.rectangle((990, 356, 1152, 372), fill=(177, 184, 197))
        draw.rounded_rectangle((1010, 405, 1146, 462), radius=16, fill=(116, 255, 165))

    def _draw_generation_mock(self, draw: ImageDraw.ImageDraw) -> None:
        draw.rounded_rectangle((830, 240, 1178, 486), radius=24, fill=(32, 40, 59))
        draw.ellipse((875, 282, 1070, 477), fill=(79, 102, 255))
        draw.ellipse((978, 320, 1132, 474), fill=(116, 255, 165))
        draw.rounded_rectangle((846, 515, 1165, 555), radius=16, fill=(44, 53, 74))

    def _draw_code_mock(self, draw: ImageDraw.ImageDraw) -> None:
        mono = self._font(25)
        rows = [
            ("agent.run(task)", (116, 255, 165)),
            ("→ research()", (226, 232, 243)),
            ("→ build()", (226, 232, 243)),
            ("✓ result", (117, 173, 255)),
        ]
        y = 260
        for row, colour in rows:
            draw.text((842, y), row, font=mono, fill=colour)
            y += 62

    def _draw_ai_mock(self, draw: ImageDraw.ImageDraw) -> None:
        draw.rounded_rectangle((835, 248, 1170, 314), radius=22, fill=(43, 53, 74))
        draw.rounded_rectangle((835, 340, 1128, 404), radius=22, fill=(49, 61, 86))
        draw.rounded_rectangle((885, 436, 1170, 502), radius=22, fill=(116, 255, 165))
        bolt = self._font(38)
        draw.text((1040, 448), "AI", font=bolt, fill=(8, 14, 22))

    @staticmethod
    def _split_display(display: str) -> list[str]:
        words = display.split()
        if len(words) <= 2:
            return [display]
        if len(words) <= 5:
            split = (len(words) + 1) // 2
            return [" ".join(words[:split]), " ".join(words[split:])]
        first = max(1, len(words) // 3)
        second = max(first + 1, (2 * len(words)) // 3)
        return [" ".join(words[:first]), " ".join(words[first:second]), " ".join(words[second:])]

    @staticmethod
    def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return ImageFont.truetype(str(candidate), size=size)
        return ImageFont.load_default()
