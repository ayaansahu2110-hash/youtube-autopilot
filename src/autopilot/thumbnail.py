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
    ) -> Path:
        """Create a high-contrast ByteVexa thumbnail with a visual story, not a text card."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        width, height = 1280, 720

        image = Image.new("RGB", (width, height), (8, 11, 20))
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((790, -120, 1390, 500), fill=(76, 235, 148, 95))
        glow_draw.ellipse((-230, 330, 430, 980), fill=(72, 92, 255, 72))
        glow = glow.filter(ImageFilter.GaussianBlur(90))
        image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")
        draw = ImageDraw.Draw(image)

        # Small brand tag: recognizable, but never competes with the hook.
        brand_font = self._font(25)
        draw.rounded_rectangle((64, 50, 250, 96), radius=18, fill=(20, 30, 43))
        draw.text((84, 61), "BYTEVEXA", font=brand_font, fill=(116, 255, 165))

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
        draw.rounded_rectangle(panel, radius=34, fill=(18, 24, 38), outline=(90, 108, 140), width=3)
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
        draw.rounded_rectangle((742, 306, 797, 366), radius=20, fill=(116, 255, 165))
        arrow_font = self._font(38)
        draw.text((753, 310), "→", font=arrow_font, fill=(8, 13, 22))

        image.save(output_path, quality=96, optimize=True)
        return output_path

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
