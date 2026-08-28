from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


class ThumbnailGenerator:
    def create(self, text: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (1280, 720), (13, 18, 27))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((65, 70, 1215, 650), radius=52, fill=(24, 32, 46), outline=(74, 222, 128), width=8)
        draw.ellipse((880, 80, 1170, 370), fill=(44, 62, 80))
        draw.ellipse((950, 135, 1120, 305), fill=(74, 222, 128))

        display = (text or "WORTH THE HYPE?").upper().strip()[:42]
        words = display.split()
        split = max(1, (len(words) + 1) // 2)
        lines = [" ".join(words[:split]), " ".join(words[split:])]
        lines = [line for line in lines if line]
        font = self._font(94)
        y = 215 if len(lines) == 2 else 270
        for line in lines:
            draw.text((105, y), line, font=font, fill=(248, 250, 252), stroke_width=3, stroke_fill=(0, 0, 0))
            y += 118
        image.save(output_path, quality=94)
        return output_path

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
