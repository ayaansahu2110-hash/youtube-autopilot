import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BRANDING_DIR = Path("branding")
BRANDING_DIR.mkdir(parents=True, exist_ok=True)

def create_radial_gradient(size: int, inner_color, outer_color):
    base = Image.new("RGBA", (size, size), outer_color)
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    center = size // 2
    radius = int(size * 0.45)
    draw.ellipse((center - radius, center - radius, center + radius, center + radius), fill=inner_color)
    glow = glow.filter(ImageFilter.GaussianBlur(size // 6))
    return Image.alpha_composite(base, glow)

def get_font(name: str, size: int):
    candidates = [
        f"C:/Windows/Fonts/{name}.ttf",
        f"C:/Windows/Fonts/{name.lower()}.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    return ImageFont.load_default()

def draw_centered_text(draw, text, font, center_x, center_y, fill=(255, 255, 255), stroke_fill=None, stroke_width=0):
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text(
        (center_x - w / 2 - bbox[0], center_y - h / 2 - bbox[1]),
        text,
        font=font,
        fill=fill,
        stroke_fill=stroke_fill,
        stroke_width=stroke_width,
    )

def generate_astrapulse():
    """AstraPulse: Cosmic Zodiac, mystical violet-gold nebula, constellation stars, celestial glyphs."""
    size = 1024
    img = create_radial_gradient(size, (98, 42, 178, 220), (10, 8, 24, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2 - 40

    # Draw celestial rings
    for r, width, color in [
        (380, 4, (245, 195, 75, 120)),
        (330, 2, (180, 140, 255, 80)),
        (260, 6, (255, 215, 90, 200)),
        (180, 2, (200, 160, 255, 90)),
    ]:
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=width)

    # 12 zodiac constellation markers around the ring
    zodiac_symbols = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"]
    z_font = get_font("segoeui", 38)
    for i in range(12):
        angle = (i * 30 - 90) * (math.pi / 180)
        x = cx + int(330 * math.cos(angle))
        y = cy + int(330 * math.sin(angle))
        draw.ellipse((x - 22, y - 22, x + 22, y + 22), fill=(25, 15, 48, 220), outline=(245, 195, 75, 180), width=2)
        draw_centered_text(draw, zodiac_symbols[i], z_font, x, y, (255, 230, 130))

    # Center Emblem: Majestic Sun/Moon Star
    star_font = get_font("segoeui", 140)
    draw_centered_text(draw, "✦", star_font, cx, cy, (255, 225, 95), stroke_fill=(120, 60, 220), stroke_width=6)

    # Brand Title
    title_font = get_font("georgiab", 68)
    sub_font = get_font("segoeuib", 32)
    draw_centered_text(draw, "ASTRA PULSE", title_font, size // 2, 870, (255, 245, 210), stroke_fill=(8, 5, 18), stroke_width=4)
    draw_centered_text(draw, "DAILY ZODIAC & HOROSCOPE", sub_font, size // 2, 940, (235, 185, 75))

    out = BRANDING_DIR / "astrapulse" / "avatar.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)
    return out

def generate_wondertales():
    """WonderTales Kids: Playful vibrant turquoise-purple gradient, friendly animated stars & storybook."""
    size = 1024
    img = create_radial_gradient(size, (255, 135, 180, 220), (32, 22, 75, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2 - 40

    # Rainbow playful rings
    draw.ellipse((cx - 360, cy - 360, cx + 360, cy + 360), outline=(255, 220, 70, 220), width=10)
    draw.ellipse((cx - 330, cy - 330, cx + 330, cy + 330), outline=(90, 230, 255, 180), width=6)

    # Center playful animal/storybook symbol
    center_font = get_font("segoeui", 180)
    draw_centered_text(draw, "🦊", center_font, cx, cy - 10)

    # Sparkling stars around
    star_font = get_font("segoeuib", 50)
    for sx, sy in [(cx - 240, cy - 200), (cx + 240, cy - 180), (cx - 220, cy + 180), (cx + 220, cy + 190)]:
        draw_centered_text(draw, "⭐", star_font, sx, sy, (255, 235, 80))

    title_font = get_font("segoeuib", 72)
    sub_font = get_font("segoeuib", 34)
    draw_centered_text(draw, "WONDERTALES", title_font, size // 2, 860, (255, 245, 180), stroke_fill=(35, 15, 65), stroke_width=6)
    draw_centered_text(draw, "KIDS ANIMATION & POEMS", sub_font, size // 2, 935, (120, 240, 255))

    out = BRANDING_DIR / "wondertales" / "avatar.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)
    return out

def generate_mokshavani():
    """MokshaVani: Sacred saffron & cosmic blue luminescence with glowing Om ॐ."""
    size = 1024
    img = create_radial_gradient(size, (255, 130, 30, 220), (12, 14, 38, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2 - 40

    # Sacred lotus circles
    draw.ellipse((cx - 370, cy - 370, cx + 370, cy + 370), outline=(255, 205, 75, 220), width=8)
    draw.ellipse((cx - 340, cy - 340, cx + 340, cy + 340), outline=(255, 160, 50, 140), width=3)
    draw.ellipse((cx - 270, cy - 270, cx + 270, cy + 270), outline=(255, 225, 110, 190), width=5)

    # Radiant sacred Om symbol
    om_font = get_font("segoeui", 220)
    draw_centered_text(draw, "ॐ", om_font, cx, cy - 10, (255, 240, 190), stroke_fill=(180, 50, 10), stroke_width=8)

    title_font = get_font("georgiab", 72)
    sub_font = get_font("segoeuib", 34)
    draw_centered_text(draw, "MOKSHAVANI", title_font, size // 2, 865, (255, 235, 175), stroke_fill=(20, 10, 5), stroke_width=5)
    draw_centered_text(draw, "SACRED VEDIC MANTRAS & BHAJANS", sub_font, size // 2, 935, (255, 175, 70))

    out = BRANDING_DIR / "mokshavani" / "avatar.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)
    return out

def generate_apexstoic():
    """ApexStoic: Obsidian marble, Roman pillar/laurel wreath, gold chisel precision."""
    size = 1024
    img = create_radial_gradient(size, (65, 75, 85, 180), (12, 14, 18, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2 - 40

    # Chiseled Greek border
    draw.ellipse((cx - 370, cy - 370, cx + 370, cy + 370), outline=(215, 175, 75, 220), width=6)
    draw.ellipse((cx - 340, cy - 340, cx + 340, cy + 340), outline=(130, 140, 150, 120), width=2)

    # Stoic Laurel Wreath + Roman Monogram
    icon_font = get_font("segoeui", 170)
    draw_centered_text(draw, "🏛️", icon_font, cx, cy - 15)

    title_font = get_font("georgiab", 76)
    sub_font = get_font("segoeuib", 32)
    draw_centered_text(draw, "APEX STOIC", title_font, size // 2, 865, (245, 240, 230), stroke_fill=(10, 10, 12), stroke_width=4)
    draw_centered_text(draw, "DISCIPLINE • MINDSET • RESILIENCE", sub_font, size // 2, 935, (215, 175, 75))

    out = BRANDING_DIR / "apexstoic" / "avatar.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)
    return out

def generate_chronosenigma():
    """ChronosEnigma: Lost ancient civilization, obsidian runes & mystical golden hourglass."""
    size = 1024
    img = create_radial_gradient(size, (40, 95, 120, 200), (8, 12, 20, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2 - 40

    # Ancient celestial rune circles
    draw.ellipse((cx - 370, cy - 370, cx + 370, cy + 370), outline=(225, 180, 80, 220), width=6)
    draw.ellipse((cx - 330, cy - 330, cx + 330, cy + 330), outline=(80, 200, 220, 140), width=3)

    # Ancient Hourglass / Mystery Monogram
    icon_font = get_font("segoeui", 170)
    draw_centered_text(draw, "⏳", icon_font, cx, cy - 15)

    title_font = get_font("georgiab", 68)
    sub_font = get_font("segoeuib", 32)
    draw_centered_text(draw, "CHRONOS ENIGMA", title_font, size // 2, 865, (245, 235, 210), stroke_fill=(5, 10, 15), stroke_width=5)
    draw_centered_text(draw, "UNSOLVED HISTORICAL MYSTERIES", sub_font, size // 2, 935, (90, 215, 230))

    out = BRANDING_DIR / "chronosenigma" / "avatar.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)
    return out

def generate_empirepulse():
    """EmpirePulse: Trillion-dollar financial empire, sovereign luxury gold & skyscraper lines."""
    size = 1024
    img = create_radial_gradient(size, (25, 70, 55, 200), (8, 14, 18, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2 - 40

    # Luxury emerald & gold rings
    draw.ellipse((cx - 370, cy - 370, cx + 370, cy + 370), outline=(230, 190, 75, 230), width=6)
    draw.ellipse((cx - 340, cy - 340, cx + 340, cy + 340), outline=(60, 180, 130, 140), width=3)

    # Skyscraper / Global Empire Icon
    icon_font = get_font("segoeui", 170)
    draw_centered_text(draw, "🌐", icon_font, cx, cy - 15)

    title_font = get_font("georgiab", 72)
    sub_font = get_font("segoeuib", 32)
    draw_centered_text(draw, "EMPIRE PULSE", title_font, size // 2, 865, (250, 245, 220), stroke_fill=(5, 12, 10), stroke_width=5)
    draw_centered_text(draw, "GEOPOLITICS • WEALTH • MEGA-DYNASTIES", sub_font, size // 2, 935, (230, 190, 75))

    out = BRANDING_DIR / "empirepulse" / "avatar.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)
    return out

def generate_bytevexa():
    """ByteVexa: Neon cybernetic AI core, futuristic cyan & indigo hexagonal mesh."""
    size = 1024
    img = create_radial_gradient(size, (20, 120, 180, 210), (8, 12, 24, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2 - 40

    draw.ellipse((cx - 370, cy - 370, cx + 370, cy + 370), outline=(60, 230, 255, 220), width=6)
    draw.ellipse((cx - 340, cy - 340, cx + 340, cy + 340), outline=(130, 90, 255, 150), width=3)

    icon_font = get_font("segoeui", 170)
    draw_centered_text(draw, "⚡", icon_font, cx, cy - 15, (255, 245, 120), stroke_fill=(20, 100, 200), stroke_width=6)

    title_font = get_font("segoeuib", 78)
    sub_font = get_font("segoeuib", 34)
    draw_centered_text(draw, "BYTEVEXA", title_font, size // 2, 865, (240, 255, 255), stroke_fill=(5, 15, 30), stroke_width=5)
    draw_centered_text(draw, "AI TOOLS • FUTURE TECH • AUTOMATION", sub_font, size // 2, 935, (60, 230, 255))

    out = BRANDING_DIR / "bytevexa" / "avatar.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)
    return out

def generate_curioaxiom():
    """CurioAxiom: Scientific discovery astrolabe & deep cosmos atom emblem."""
    size = 1024
    img = create_radial_gradient(size, (210, 140, 25, 210), (10, 14, 28, 255))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2 - 40

    draw.ellipse((cx - 370, cy - 370, cx + 370, cy + 370), outline=(245, 200, 65, 220), width=6)
    draw.ellipse((cx - 340, cy - 340, cx + 340, cy + 340), outline=(60, 140, 240, 140), width=3)

    icon_font = get_font("segoeui", 170)
    draw_centered_text(draw, "🔬", icon_font, cx, cy - 15)

    title_font = get_font("georgiab", 72)
    sub_font = get_font("segoeuib", 34)
    draw_centered_text(draw, "CURIOAXIOM", title_font, size // 2, 865, (255, 245, 220), stroke_fill=(5, 10, 20), stroke_width=5)
    draw_centered_text(draw, "VERIFIED SCIENCE & CINEMATIC FACTS", sub_font, size // 2, 935, (245, 200, 65))

    out = BRANDING_DIR / "curioaxiom" / "avatar.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)
    return out

if __name__ == "__main__":
    print("Generating 8 professional channel profile avatars...")
    print("1. AstraPulse:", generate_astrapulse())
    print("2. WonderTales Kids:", generate_wondertales())
    print("3. MokshaVani:", generate_mokshavani())
    print("4. ApexStoic:", generate_apexstoic())
    print("5. ChronosEnigma:", generate_chronosenigma())
    print("6. EmpirePulse:", generate_empirepulse())
    print("7. ByteVexa:", generate_bytevexa())
    print("8. CurioAxiom:", generate_curioaxiom())
    print("\nAll 8 channel avatars successfully generated in /branding directory!")
