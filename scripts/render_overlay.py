"""Render a transparent RGBA PNG overlay for ClipForge vertical Shorts.

Supports crisp text mixed with full-color Windows 11 Fluent emojis (via seguiemj.ttf
with embedded_color=True), top/bottom meme banners, center aesthetic hook captions,
and subtle creator @handle watermarks.
"""

import json
import re
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_EMOJI = r"C:\Windows\Fonts\seguiemj.ttf"
FONT_IMPACT = r"C:\Windows\Fonts\impact.ttf"
FONT_SERIF = r"C:\Windows\Fonts\georgiab.ttf"
FONT_SANS_BOLD = r"C:\Windows\Fonts\arialbd.ttf"
FONT_SCRIPT = r"C:\Windows\Fonts\segoeprb.ttf"

# Strip variation selectors (U+FE0F) & ZWJ noise that create extra spacing in Pillow
EMOJI_RE = re.compile(
    "(["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\u2764\u2665\u2661\u26A1\u2728\u2B50\u2757\u2753"
    "]+)",
    flags=re.UNICODE,
)


FONT_LINUX_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_LINUX_LIBERATION = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_LINUX_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        path,
        FONT_SANS_BOLD,
        r"C:\Windows\Fonts\segoeui.ttf",
        FONT_LINUX_BOLD,
        FONT_LINUX_LIBERATION,
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ]
    if "seguiemj" in path.lower() or "emoji" in path.lower():
        candidates.insert(1, FONT_LINUX_EMOJI)
    for candidate in candidates:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                # NotoColorEmoji bitmap tables on Linux often only open at 109px
                if "NotoColorEmoji" in candidate:
                    try:
                        return ImageFont.truetype(candidate, 109)
                    except Exception:
                        pass
    return ImageFont.load_default()


def _clean_emoji_chunk(txt: str) -> str:
    return re.sub(r"[\ufe0f\ufe0e\u200d\U0001F3FB-\U0001F3FF]", "", txt)


def _split_runs(line: str) -> list[tuple[bool, str]]:
    runs = []
    pos = 0
    for m in EMOJI_RE.finditer(line):
        if m.start() > pos:
            runs.append((False, line[pos : m.start()]))
        em = _clean_emoji_chunk(m.group(0))
        if em:
            runs.append((True, em))
        pos = m.end()
    if pos < len(line):
        runs.append((False, line[pos:]))
    return runs


def _measure_line(draw: ImageDraw.ImageDraw, line: str, font_txt, font_em) -> tuple[int, int]:
    total_w = 0
    max_h = font_txt.size
    for is_em, chunk in _split_runs(line):
        f = font_em if is_em else font_txt
        bbox = draw.textbbox((0, 0), chunk, font=f)
        total_w += max(0, bbox[2] - bbox[0])
        max_h = max(max_h, bbox[3] - bbox[1])
    return total_w, max_h


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font_txt, font_em, max_width: int) -> list[str]:
    lines: list[str] = []
    for raw_para in str(text).splitlines():
        words = raw_para.strip().split()
        if not words:
            continue
        cur = words[0]
        for w in words[1:]:
            trial = f"{cur} {w}"
            tw, _ = _measure_line(draw, trial, font_txt, font_em)
            if tw <= max_width:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def _draw_mixed_centered_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    center_y: int,
    width: int,
    font_path: str,
    font_size: int,
    fill: tuple[int, int, int, int],
    stroke_fill: tuple[int, int, int, int] | None = (0, 0, 0, 230),
    stroke_width: int = 3,
    max_width_ratio: float = 0.88,
    line_gap: int = 12,
):
    if not text or not str(text).strip():
        return
    font_txt = _load_font(font_path, font_size)
    font_em = _load_font(FONT_EMOJI, font_size)
    lines = _wrap_text(draw, text, font_txt, font_em, int(width * max_width_ratio))
    if not lines:
        return

    line_metrics = [_measure_line(draw, ln, font_txt, font_em) for ln in lines]
    total_h = sum(h for _, h in line_metrics) + line_gap * (len(lines) - 1)
    cur_y = center_y - total_h // 2

    for ln, (lw, lh) in zip(lines, line_metrics, strict=True):
        cur_x = (width - lw) // 2
        for is_em, chunk in _split_runs(ln):
            f = font_em if is_em else font_txt
            if is_em:
                draw.text((cur_x, cur_y), chunk, font=f, embedded_color=True)
            else:
                if stroke_fill and stroke_width > 0:
                    draw.text(
                        (cur_x, cur_y),
                        chunk,
                        font=f,
                        fill=fill,
                        stroke_width=stroke_width,
                        stroke_fill=stroke_fill,
                    )
                else:
                    draw.text((cur_x, cur_y), chunk, font=f, fill=fill)
            bbox = draw.textbbox((0, 0), chunk, font=f)
            cur_x += max(0, bbox[2] - bbox[0])
        cur_y += lh + line_gap


def render_overlay(spec: dict, out_path: Path):
    w = int(spec.get("width", 1080))
    h = int(spec.get("height", 1920))
    layout = spec.get("layoutMode", "crop")

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    top_text = spec.get("topText") or ""
    bottom_text = spec.get("bottomText") or ""
    center_text = spec.get("centerText") or ""
    watermark = spec.get("watermarkText") or ""
    top_pill = bool(spec.get("topPill", False))

    is_white_bg = layout == "letterbox-meme"
    scale = w / 1080.0

    # Top Hook Banner
    if top_text:
        if top_pill:
            font_txt = _load_font(FONT_SANS_BOLD, max(22, int(46 * scale)))
            font_em = _load_font(FONT_EMOJI, max(22, int(46 * scale)))
            lines = _wrap_text(draw, top_text, font_txt, font_em, int(w * 0.84))
            if lines:
                line_metrics = [_measure_line(draw, ln, font_txt, font_em) for ln in lines]
                max_lw = max(lw for lw, _ in line_metrics)
                line_gap = int(10 * scale)
                total_h = sum(h for _, h in line_metrics) + line_gap * (len(lines) - 1)
                pad_x = int(38 * scale)
                pad_y = int(20 * scale)
                pill_w = min(int(w * 0.94), max_lw + pad_x * 2)
                pill_h = total_h + pad_y * 2
                cy = int(275 * scale)
                x0 = (w - pill_w) // 2
                y0 = cy - pill_h // 2
                draw.rounded_rectangle(
                    [x0, y0, x0 + pill_w, y0 + pill_h],
                    radius=int(26 * scale),
                    fill=(255, 255, 255, 248),
                    outline=(220, 220, 220, 255),
                    width=max(1, int(2 * scale)),
                )
                cur_y = y0 + pad_y - int(4 * scale)
                for ln, (lw, lh) in zip(lines, line_metrics, strict=True):
                    cur_x = (w - lw) // 2
                    for is_em, chunk in _split_runs(ln):
                        f = font_em if is_em else font_txt
                        if is_em:
                            draw.text((cur_x, cur_y), chunk, font=f, embedded_color=True)
                        else:
                            draw.text((cur_x, cur_y), chunk, font=f, fill=(18, 18, 22, 255))
                        bbox = draw.textbbox((0, 0), chunk, font=f)
                        cur_x += max(0, bbox[2] - bbox[0])
                    cur_y += lh + line_gap
        elif is_white_bg:
            _draw_mixed_centered_block(
                draw,
                top_text,
                center_y=int(240 * scale),
                width=w,
                font_path=FONT_IMPACT,
                font_size=max(26, int(68 * scale)),
                fill=(228, 178, 52, 255),
                stroke_fill=(35, 25, 0, 220),
                stroke_width=max(1, int(3 * scale)),
            )
        else:
            _draw_mixed_centered_block(
                draw,
                top_text,
                center_y=int(390 * scale),
                width=w,
                font_path=FONT_SANS_BOLD,
                font_size=max(24, int(52 * scale)),
                fill=(255, 230, 64, 255),
                stroke_fill=(0, 0, 0, 245),
                stroke_width=max(2, int(5 * scale)),
            )

    # Center / Lower-Middle Aesthetic Caption (e.g., "He doesn't look good!! 🗣️")
    if center_text:
        _draw_mixed_centered_block(
            draw,
            center_text,
            center_y=int(h * 0.62),
            width=w,
            font_path=FONT_SERIF,
            font_size=max(22, int(46 * scale)),
            fill=(255, 255, 255, 255),
            stroke_fill=(0, 0, 0, 235),
            stroke_width=max(2, int(4 * scale)),
            max_width_ratio=0.84,
        )

    # Bottom Hook / Punchline Banner
    if bottom_text:
        if is_white_bg:
            _draw_mixed_centered_block(
                draw,
                bottom_text,
                center_y=int(1560 * scale),
                width=w,
                font_path=FONT_IMPACT,
                font_size=max(26, int(64 * scale)),
                fill=(228, 178, 52, 255),
                stroke_fill=(35, 25, 0, 220),
                stroke_width=max(1, int(3 * scale)),
            )
        else:
            _draw_mixed_centered_block(
                draw,
                bottom_text,
                center_y=int(1560 * scale),
                width=w,
                font_path=FONT_SANS_BOLD,
                font_size=max(22, int(48 * scale)),
                fill=(255, 255, 255, 255),
                stroke_fill=(0, 0, 0, 245),
                stroke_width=max(2, int(4 * scale)),
            )

    # Subtle Watermark (@handle)
    if watermark:
        wm_font = _load_font(FONT_SCRIPT, max(16, int(28 * scale)))
        wm_em = _load_font(FONT_EMOJI, max(16, int(28 * scale)))
        wm_w, wm_h = _measure_line(draw, watermark, wm_font, wm_em)
        wm_x = max(int(24 * scale), int(w * 0.60))
        if wm_x + wm_w > w - int(24 * scale):
            wm_x = w - wm_w - int(24 * scale)
        wm_y = int(h * 0.64) if is_white_bg else int(h * 0.65)
        cur_x = wm_x
        for is_em, chunk in _split_runs(watermark):
            f = wm_em if is_em else wm_font
            if is_em:
                draw.text((cur_x, wm_y), chunk, font=f, embedded_color=True)
            else:
                draw.text(
                    (cur_x, wm_y),
                    chunk,
                    font=f,
                    fill=(255, 255, 255, 215),
                    stroke_width=max(1, int(2 * scale)),
                    stroke_fill=(0, 0, 0, 200),
                )
            bbox = draw.textbbox((0, 0), chunk, font=f)
            cur_x += max(0, bbox[2] - bbox[0])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: render_overlay.py <spec.json> <out.png>", file=sys.stderr)
        sys.exit(1)
    spec_path = Path(sys.argv[1])
    out_png = Path(sys.argv[2])
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    render_overlay(data, out_png)
