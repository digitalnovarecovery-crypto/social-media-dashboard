"""Agent 3: Creative Director — Generates professional branded visuals using Pillow.

Schedule: Daily at 7am
Reads: today's draft posts from DB
Produces: image_url on each post (locally generated branded images served via /static/)

Design philosophy: Bold, large text that fills 50-70% of the image. Every image
should look like it was designed by a social media manager in Canva — big headlines,
prominent phone numbers, strong brand presence.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

from agents.base_agent import BaseAgent
from config import BRANDS, PROJECT_ROOT
from db.models import Post, get_db

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLATFORM_SIZES = {
    "facebook": (1200, 630),
    "instagram": (1080, 1080),
    "tiktok": (1080, 1920),
    "linkedin": (1200, 627),
    "youtube": (1280, 720),
}

POST_TYPES = ("quote", "bold_headline", "cta", "service_list", "motivational")

IMAGES_DIR = PROJECT_ROOT / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Bundled font paths (guaranteed to exist in the repo)
_BUNDLED_BOLD = str(PROJECT_ROOT / "static" / "fonts" / "DejaVuSans-Bold.ttf")
_BUNDLED_REGULAR = str(PROJECT_ROOT / "static" / "fonts" / "DejaVuSans.ttf")

# Font paths in preference order — bundled fonts FIRST for reliability
_BOLD_FONT_PATHS = [
    _BUNDLED_BOLD,
    "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
    "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

_REGULAR_FONT_PATHS = [
    _BUNDLED_REGULAR,
    "/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf",
    "/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf",
    "/usr/share/fonts/truetype/lato/Lato-Semibold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

_MEDIUM_FONT_PATHS = [
    _BUNDLED_BOLD,  # Use bold as medium fallback
    "/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf",
    "/usr/share/fonts/truetype/lato/Lato-Semibold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

# Cache resolved font path so we don't stat every time
_font_cache: dict[str, str | None] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_font_path(candidates: list[str]) -> str | None:
    key = "|".join(candidates)
    if key not in _font_cache:
        for fp in candidates:
            if os.path.exists(fp):
                _font_cache[key] = fp
                break
        else:
            _font_cache[key] = None
    return _font_cache[key]


def get_font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    """Return a font at the requested size. weight: 'bold', 'medium', 'regular'."""
    if weight == "bold":
        path = _resolve_font_path(_BOLD_FONT_PATHS)
    elif weight == "medium":
        path = _resolve_font_path(_MEDIUM_FONT_PATHS)
    else:
        path = _resolve_font_path(_REGULAR_FONT_PATHS)

    if path:
        return ImageFont.truetype(path, size)
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def luminance(rgb: Tuple[int, int, int]) -> float:
    """Perceived luminance 0-1."""
    return (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255.0


def darken(rgb: Tuple[int, ...], factor: float = 0.6) -> Tuple[int, int, int]:
    return (max(0, int(rgb[0] * factor)),
            max(0, int(rgb[1] * factor)),
            max(0, int(rgb[2] * factor)))


def lighten(rgb: Tuple[int, ...], factor: float = 0.3) -> Tuple[int, int, int]:
    return (min(255, int(rgb[0] + (255 - rgb[0]) * factor)),
            min(255, int(rgb[1] + (255 - rgb[1]) * factor)),
            min(255, int(rgb[2] + (255 - rgb[2]) * factor)))


def contrast_color(bg: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Return white or near-black depending on background luminance."""
    if luminance(bg) > 0.55:
        return (20, 20, 20)
    return (255, 255, 255)


def shadow_color(text_rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Shadow colour opposite to text."""
    if luminance(text_rgb) > 0.5:
        return (0, 0, 0)
    return (60, 60, 60)


def draw_text_with_shadow(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: Tuple[int, int, int],
    shadow_offset: int = 3,
    shadow_fill: Tuple[int, int, int] | None = None,
):
    """Draw text with a drop shadow for readability."""
    sx, sy = xy
    sf = shadow_fill or shadow_color(fill)
    # Draw shadow twice for thickness
    draw.text((sx + shadow_offset, sy + shadow_offset), text, fill=sf, font=font)
    draw.text((sx + shadow_offset - 1, sy + shadow_offset - 1), text, fill=sf, font=font)
    draw.text((sx, sy), text, fill=fill, font=font)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines: list[str] = []
    current_line = ""
    for word in words:
        test = f"{current_line} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines or [text]


def text_block_height(lines: list[str], font: ImageFont.FreeTypeFont, line_spacing: int) -> int:
    total = 0
    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        total += bbox[3] - bbox[1]
        if i < len(lines) - 1:
            total += line_spacing
    return total


def draw_centered_text_block(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    y_start: int,
    canvas_width: int,
    fill: Tuple[int, int, int],
    line_spacing: int = 10,
    shadow_offset: int = 3,
    align: str = "center",
    x_left: int = 0,
) -> int:
    """Draw multiple lines of text. Returns y position after last line."""
    y = y_start
    for line in lines:
        bbox = font.getbbox(line)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        if align == "center":
            x = (canvas_width - tw) // 2
        else:
            x = x_left
        draw_text_with_shadow(draw, (x, y), line, font, fill, shadow_offset)
        y += th + line_spacing
    return y


def draw_rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill):
    """Draw a rounded rectangle (compatible with older Pillow versions)."""
    x0, y0, x1, y1 = xy
    # Use built-in rounded_rectangle if available (Pillow >= 8.2)
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)
    else:
        # Fallback: rectangle + circles at corners
        draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
        draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
        draw.pieslice([x0, y0, x0 + 2 * radius, y0 + 2 * radius], 180, 270, fill=fill)
        draw.pieslice([x1 - 2 * radius, y0, x1, y0 + 2 * radius], 270, 360, fill=fill)
        draw.pieslice([x0, y1 - 2 * radius, x0 + 2 * radius, y1], 90, 180, fill=fill)
        draw.pieslice([x1 - 2 * radius, y1 - 2 * radius, x1, y1], 0, 90, fill=fill)


# ---------------------------------------------------------------------------
# Background renderers
# ---------------------------------------------------------------------------

def fill_solid(img: Image.Image, color: Tuple[int, int, int]):
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), img.size], fill=color)


def fill_gradient_vertical(img: Image.Image, top: Tuple[int, int, int], bottom: Tuple[int, int, int]):
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def fill_diagonal_split(img: Image.Image, color_a: Tuple[int, int, int], color_b: Tuple[int, int, int]):
    """Fill with a diagonal split — top-left is color_a, bottom-right is color_b."""
    draw = ImageDraw.Draw(img)
    w, h = img.size
    draw.rectangle([(0, 0), (w, h)], fill=color_a)
    draw.polygon([(w, 0), (w, h), (0, h)], fill=color_b)


def draw_decorative_dots(draw: ImageDraw.ImageDraw, w: int, h: int, color: Tuple[int, int, int], count: int = 12):
    """Scatter decorative circles for visual interest."""
    rng = random.Random(w * h)  # deterministic per image size
    for _ in range(count):
        r = rng.randint(int(min(w, h) * 0.02), int(min(w, h) * 0.06))
        x = rng.randint(-r, w)
        y = rng.randint(-r, h)
        # Very subtle — use faded color
        faded = (color[0], color[1], color[2])
        draw.ellipse([x - r, y - r, x + r, y + r], fill=None, outline=faded, width=2)


def draw_corner_accent(draw: ImageDraw.ImageDraw, w: int, h: int, color: Tuple[int, int, int]):
    """Draw a bold accent shape in the top-right corner."""
    size = int(min(w, h) * 0.25)
    draw.ellipse([w - size, -size // 2, w + size // 2, size], fill=None, outline=color, width=4)
    # Small circle bottom-left
    sr = int(min(w, h) * 0.10)
    draw.ellipse([-sr // 2, h - sr - 10, sr + sr // 2, h + sr // 2], fill=None, outline=color, width=3)


# ---------------------------------------------------------------------------
# Layout renderers — one per post_type
# ---------------------------------------------------------------------------

def render_quote(
    img: Image.Image,
    headline: str,
    subtext: str,
    phone: str,
    brand_name: str,
    primary: Tuple[int, int, int],
    accent: Tuple[int, int, int],
):
    """Quote card: large quote with attribution, decorative quote marks."""
    w, h = img.size
    draw = ImageDraw.Draw(img)

    # Background: accent color (bright, eye-catching)
    fill_solid(img, accent)
    draw = ImageDraw.Draw(img)

    text_fill = contrast_color(accent)
    margin_x = int(w * 0.10)
    usable_w = w - 2 * margin_x

    # Giant decorative open-quote mark
    quote_font_size = int(w * 0.25)
    quote_font = get_font(quote_font_size, "bold")
    draw_text_with_shadow(
        draw, (margin_x - int(w * 0.02), int(h * 0.04)),
        "\u201C", quote_font, darken(accent, 0.75), shadow_offset=0,
    )

    # Headline text — large and filling
    headline_size = max(60, int(w / 6.5))
    headline_font = get_font(headline_size, "bold")
    lines = wrap_text(headline.upper(), headline_font, usable_w)

    # If too many lines, reduce size
    while len(lines) > 5 and headline_size > 50:
        headline_size -= 8
        headline_font = get_font(headline_size, "bold")
        lines = wrap_text(headline.upper(), headline_font, usable_w)

    block_h = text_block_height(lines, headline_font, int(headline_size * 0.2))
    y_start = int(h * 0.18)

    y = draw_centered_text_block(
        draw, lines, headline_font, y_start, w, text_fill,
        line_spacing=int(headline_size * 0.2), shadow_offset=2,
    )

    # Closing quote mark
    draw_text_with_shadow(
        draw, (w - margin_x - int(w * 0.10), y - int(headline_size * 0.3)),
        "\u201D", quote_font, darken(accent, 0.75), shadow_offset=0,
    )

    # Attribution / subtext
    sub_size = max(28, int(headline_size * 0.35))
    sub_font = get_font(sub_size, "medium")
    sub_lines = wrap_text(f"-- {subtext}", sub_font, usable_w)
    y += int(h * 0.03)
    y = draw_centered_text_block(
        draw, sub_lines, sub_font, y, w, darken(text_fill, 0.7),
        line_spacing=8, shadow_offset=1,
    )

    # Bottom brand bar
    _draw_brand_bar(draw, w, h, brand_name, phone, primary, accent, text_fill)


def render_bold_headline(
    img: Image.Image,
    headline: str,
    subtext: str,
    phone: str,
    brand_name: str,
    primary: Tuple[int, int, int],
    accent: Tuple[int, int, int],
):
    """Bold headline: text fills the frame with engagement question."""
    w, h = img.size

    # Background: primary brand color
    fill_solid(img, primary)
    draw = ImageDraw.Draw(img)
    draw_decorative_dots(draw, w, h, accent, count=15)
    draw_corner_accent(draw, w, h, accent)

    text_fill = contrast_color(primary)
    margin_x = int(w * 0.08)
    usable_w = w - 2 * margin_x

    # HUGE headline
    headline_size = max(70, int(w / 5.5))
    headline_font = get_font(headline_size, "bold")
    lines = wrap_text(headline.upper(), headline_font, usable_w)

    while len(lines) > 5 and headline_size > 55:
        headline_size -= 8
        headline_font = get_font(headline_size, "bold")
        lines = wrap_text(headline.upper(), headline_font, usable_w)

    block_h = text_block_height(lines, headline_font, int(headline_size * 0.25))
    # Center vertically in upper 65% of image
    available_h = int(h * 0.60)
    y_start = max(int(h * 0.06), (available_h - block_h) // 2)

    y = draw_centered_text_block(
        draw, lines, headline_font, y_start, w, text_fill,
        line_spacing=int(headline_size * 0.25), shadow_offset=3,
    )

    # Accent divider bar
    bar_w = int(w * 0.25)
    bar_h = max(5, int(h * 0.008))
    draw.rectangle(
        [(w // 2 - bar_w // 2, y + 10), (w // 2 + bar_w // 2, y + 10 + bar_h)],
        fill=accent,
    )
    y += 10 + bar_h + 15

    # Subtext / engagement question
    sub_size = max(32, int(headline_size * 0.38))
    sub_font = get_font(sub_size, "medium")
    sub_lines = wrap_text(subtext, sub_font, usable_w)
    y = draw_centered_text_block(
        draw, sub_lines, sub_font, y, w, accent,
        line_spacing=8, shadow_offset=2,
    )

    _draw_brand_bar(draw, w, h, brand_name, phone, primary, accent, text_fill)


def render_cta(
    img: Image.Image,
    headline: str,
    subtext: str,
    phone: str,
    brand_name: str,
    primary: Tuple[int, int, int],
    accent: Tuple[int, int, int],
):
    """CTA layout: 'Don't wait for crisis. Call (XXX) XXX-XXXX' filling the frame."""
    w, h = img.size

    # Background: gradient from primary to slightly lighter
    fill_gradient_vertical(img, primary, lighten(primary, 0.15))
    draw = ImageDraw.Draw(img)

    text_fill = contrast_color(primary)
    margin_x = int(w * 0.08)
    usable_w = w - 2 * margin_x

    # Top accent bar
    draw.rectangle([(0, 0), (w, max(8, int(h * 0.012)))], fill=accent)

    # Headline — large
    headline_size = max(65, int(w / 6))
    headline_font = get_font(headline_size, "bold")
    lines = wrap_text(headline.upper(), headline_font, usable_w)

    while len(lines) > 4 and headline_size > 50:
        headline_size -= 8
        headline_font = get_font(headline_size, "bold")
        lines = wrap_text(headline.upper(), headline_font, usable_w)

    y_start = int(h * 0.10)
    y = draw_centered_text_block(
        draw, lines, headline_font, y_start, w, text_fill,
        line_spacing=int(headline_size * 0.22), shadow_offset=3,
    )

    y += int(h * 0.04)

    # Phone number — HUGE, in accent color, inside a rounded pill
    if phone:
        phone_size = max(55, int(w / 8))
        phone_font = get_font(phone_size, "bold")
        phone_bbox = phone_font.getbbox(phone)
        phone_tw = phone_bbox[2] - phone_bbox[0]
        phone_th = phone_bbox[3] - phone_bbox[1]

        pill_pad_x = int(w * 0.06)
        pill_pad_y = int(phone_th * 0.4)
        pill_w = phone_tw + pill_pad_x * 2
        pill_h = phone_th + pill_pad_y * 2
        pill_x = (w - pill_w) // 2
        pill_y = y

        draw_rounded_rect(draw, (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h),
                          radius=pill_h // 2, fill=accent)
        phone_fill = contrast_color(accent)
        phone_x = (w - phone_tw) // 2
        phone_y = pill_y + pill_pad_y
        draw.text((phone_x, phone_y), phone, fill=phone_fill, font=phone_font)
        y = pill_y + pill_h + int(h * 0.03)
    else:
        y += int(h * 0.02)

    # Subtext below phone
    sub_size = max(28, int(headline_size * 0.35))
    sub_font = get_font(sub_size, "medium")
    sub_lines = wrap_text(subtext, sub_font, usable_w)
    y = draw_centered_text_block(
        draw, sub_lines, sub_font, y, w, lighten(text_fill, 0.15),
        line_spacing=8, shadow_offset=2,
    )

    # Brand at very bottom
    _draw_brand_bar(draw, w, h, brand_name, "", primary, accent, text_fill)


def render_service_list(
    img: Image.Image,
    headline: str,
    subtext: str,
    phone: str,
    brand_name: str,
    primary: Tuple[int, int, int],
    accent: Tuple[int, int, int],
):
    """Service list: headline + bullet points."""
    w, h = img.size

    # Background: diagonal split for visual interest
    fill_diagonal_split(img, primary, darken(primary, 0.75))
    draw = ImageDraw.Draw(img)

    text_fill = contrast_color(primary)
    margin_x = int(w * 0.10)
    usable_w = w - 2 * margin_x

    # Top accent strip
    strip_h = max(10, int(h * 0.015))
    draw.rectangle([(0, 0), (w, strip_h)], fill=accent)

    # Headline
    headline_size = max(55, int(w / 7.5))
    headline_font = get_font(headline_size, "bold")
    lines = wrap_text(headline.upper(), headline_font, usable_w)

    while len(lines) > 3 and headline_size > 45:
        headline_size -= 6
        headline_font = get_font(headline_size, "bold")
        lines = wrap_text(headline.upper(), headline_font, usable_w)

    y = int(h * 0.08)
    y = draw_centered_text_block(
        draw, lines, headline_font, y, w, accent,
        line_spacing=int(headline_size * 0.2), shadow_offset=3,
    )

    # Divider
    y += int(h * 0.02)
    bar_w = int(w * 0.30)
    draw.rectangle([(w // 2 - bar_w // 2, y), (w // 2 + bar_w // 2, y + 5)], fill=accent)
    y += int(h * 0.03)

    # Service items from subtext (split on commas, semicolons, or pipes)
    items = re.split(r'[,;|]', subtext)
    items = [item.strip() for item in items if item.strip()]
    if not items:
        items = [subtext]

    bullet_size = max(30, int(w / 14))
    bullet_font = get_font(bullet_size, "medium")
    check_size = max(28, int(bullet_size * 0.9))

    for item in items[:6]:  # Max 6 items
        item_text = item.strip()
        if not item_text:
            continue
        # Checkmark bullet
        check_x = margin_x
        item_lines = wrap_text(item_text, bullet_font, usable_w - int(w * 0.08))
        for j, il in enumerate(item_lines):
            prefix = "\u2713 " if j == 0 else "   "
            draw_text_with_shadow(
                draw, (check_x, y), prefix + il, bullet_font, text_fill,
                shadow_offset=2,
            )
            y += bullet_size + int(bullet_size * 0.35)

    # Phone + brand
    _draw_brand_bar(draw, w, h, brand_name, phone, primary, accent, text_fill)


def render_motivational(
    img: Image.Image,
    headline: str,
    subtext: str,
    phone: str,
    brand_name: str,
    primary: Tuple[int, int, int],
    accent: Tuple[int, int, int],
):
    """Motivational: centered bold text on bright background, inspirational feel."""
    w, h = img.size

    # Use accent as background for a bright, uplifting look
    accent_bg = lighten(accent, 0.1)
    fill_gradient_vertical(img, accent_bg, accent)
    draw = ImageDraw.Draw(img)

    text_fill = contrast_color(accent)
    margin_x = int(w * 0.10)
    usable_w = w - 2 * margin_x

    # Decorative thin lines
    line_color = darken(accent, 0.8)
    for i in range(3):
        lw = max(2, int(w * 0.002))
        offset = int(w * 0.04) * (i + 1)
        draw.line([(offset, 0), (offset, h)], fill=line_color, width=lw)
        draw.line([(w - offset, 0), (w - offset, h)], fill=line_color, width=lw)

    # Small brand short name or icon at top center
    top_size = max(22, int(w / 25))
    top_font = get_font(top_size, "medium")
    top_bbox = top_font.getbbox(brand_name.upper())
    top_tw = top_bbox[2] - top_bbox[0]
    draw.text(((w - top_tw) // 2, int(h * 0.05)), brand_name.upper(), fill=text_fill, font=top_font)

    # HUGE motivational headline
    headline_size = max(75, int(w / 5))
    headline_font = get_font(headline_size, "bold")
    lines = wrap_text(headline.upper(), headline_font, usable_w)

    while len(lines) > 5 and headline_size > 55:
        headline_size -= 8
        headline_font = get_font(headline_size, "bold")
        lines = wrap_text(headline.upper(), headline_font, usable_w)

    block_h = text_block_height(lines, headline_font, int(headline_size * 0.25))
    available_top = int(h * 0.12)
    available_bottom = int(h * 0.75)
    y_start = max(available_top, (available_top + available_bottom - block_h) // 2)

    y = draw_centered_text_block(
        draw, lines, headline_font, y_start, w, text_fill,
        line_spacing=int(headline_size * 0.25), shadow_offset=2,
    )

    # Subtext
    y += int(h * 0.02)
    sub_size = max(28, int(headline_size * 0.32))
    sub_font = get_font(sub_size, "medium")
    sub_lines = wrap_text(subtext, sub_font, usable_w)
    y = draw_centered_text_block(
        draw, sub_lines, sub_font, y, w, darken(text_fill, 0.65),
        line_spacing=6, shadow_offset=1,
    )

    # Phone number at bottom
    _draw_brand_bar(draw, w, h, brand_name, phone, primary, accent, text_fill)


# ---------------------------------------------------------------------------
# Shared bottom brand bar
# ---------------------------------------------------------------------------

def _draw_brand_bar(
    draw: ImageDraw.ImageDraw,
    w: int,
    h: int,
    brand_name: str,
    phone: str,
    primary: Tuple[int, int, int],
    accent: Tuple[int, int, int],
    text_fill: Tuple[int, int, int],
):
    """Draw a strong brand presence bar at the bottom of the image."""
    bar_h = int(h * 0.14)
    bar_y = h - bar_h

    # Semi-opaque dark bar
    bar_color = darken(primary, 0.35)
    draw.rectangle([(0, bar_y), (w, h)], fill=bar_color)
    # Accent line on top of bar
    draw.rectangle([(0, bar_y), (w, bar_y + max(4, int(h * 0.006)))], fill=accent)

    inner_h = bar_h - max(4, int(h * 0.006))
    inner_y = bar_y + max(4, int(h * 0.006))
    margin = int(w * 0.05)

    bar_text = contrast_color(bar_color)

    # Brand name — large and bold
    brand_size = max(30, int(inner_h * 0.38))
    brand_font = get_font(brand_size, "bold")

    if phone:
        # Two-line layout: brand name on top, phone below
        brand_y = inner_y + int(inner_h * 0.10)
        draw.text((margin, brand_y), brand_name.upper(), fill=accent, font=brand_font)

        phone_size = max(26, int(inner_h * 0.32))
        phone_font = get_font(phone_size, "bold")
        phone_y = brand_y + brand_size + int(inner_h * 0.05)
        phone_bbox = phone_font.getbbox(phone)
        phone_tw = phone_bbox[2] - phone_bbox[0]
        # Phone on the right
        draw.text((w - phone_tw - margin, inner_y + (inner_h - phone_size) // 2),
                  phone, fill=bar_text, font=phone_font)
    else:
        # Just brand name centered vertically
        brand_y = inner_y + (inner_h - brand_size) // 2
        bbox = brand_font.getbbox(brand_name.upper())
        bw = bbox[2] - bbox[0]
        draw.text(((w - bw) // 2, brand_y), brand_name.upper(), fill=accent, font=brand_font)


# ---------------------------------------------------------------------------
# Layout dispatcher
# ---------------------------------------------------------------------------

# --- v2 layouts (see agents/layouts_v2.py) ---
from agents.layouts_v2 import (
    render_quote as _v2_render_quote,
    render_bold_headline as _v2_render_bold_headline,
    render_cta as _v2_render_cta,
    render_service_list as _v2_render_service_list,
    render_motivational as _v2_render_motivational,
)

LAYOUT_RENDERERS = {
    "quote": _v2_render_quote,
    "bold_headline": _v2_render_bold_headline,
    "cta": _v2_render_cta,
    "service_list": _v2_render_service_list,
    "motivational": _v2_render_motivational,
}


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class CreativeDirector(BaseAgent):
    name = "creative_director"
    display_name = "Creative Director"

    def run(self) -> dict:
        brands = [self.brand_id] if self.brand_id else list(BRANDS.keys())
        total = 0
        for brand_id in brands:
            count = self._create_visuals(brand_id)
            total += count
        return {"posts_created": total}

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------

    def _create_visuals(self, brand_id: str) -> int:
        db = get_db()
        try:
            posts = (
                db.query(Post)
                .filter_by(brand_id=brand_id, status="draft")
                .filter(Post.image_url.is_(None))
                .all()
            )

            if not posts:
                self.log(f"No posts need visuals for {brand_id}")
                return 0

            brand_info = BRANDS[brand_id]
            count = 0

            for post in posts:
                try:
                    brief = self._generate_brief(brand_info, post)
                    image_path = self._generate_image(brief, post, brand_info)
                    if image_path:
                        post.image_url = f"/static/images/{image_path.name}"
                        post.image_prompt = brief.get("headline", "")
                        count += 1
                        self.log(
                            f"Generated {brief.get('post_type', 'unknown')} visual "
                            f"for post {post.id} ({post.platform})"
                        )
                except Exception as e:
                    self.log(f"Failed to generate visual for post {post.id}: {e}")

            db.commit()
            self.log(f"Generated {count} visuals for {brand_id}")
            return count
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Brief generation via Claude
    # ------------------------------------------------------------------

    def _generate_brief(self, brand_info: dict, post: Post) -> dict:
        """Use Claude to generate a creative brief including post_type."""
        prompt = f"""You are a creative director for {brand_info['name']}.

Generate a creative brief for a social media image. Return ONLY valid JSON.

Platform: {post.platform}
Caption: {(post.caption or '')[:500]}
Brand colors: primary {brand_info['color']}, accent {brand_info['accent']}
Phone: {brand_info.get('phones', {}).get(post.platform, '')}

Return this exact JSON structure:
{{
  "post_type": "one of: quote, bold_headline, cta, service_list, motivational",
  "headline": "Short impactful headline (4-8 words max)",
  "subtext": "Supporting text (max 15 words). For service_list type, list 3-5 services separated by | characters.",
  "use_accent_bg": true or false (true = use bright accent color as background for variety)
}}

Guidelines:
- post_type "quote" for inspirational quotes or testimonial-style posts
- post_type "bold_headline" for engagement questions or bold statements
- post_type "cta" for call-to-action posts encouraging people to call
- post_type "service_list" for posts about services, programs, amenities
- post_type "motivational" for uplifting recovery messages
- headline must be SHORT and PUNCHY — it will be rendered HUGE
- For service_list subtext, separate items with | like "Medical Detox | Therapy | Aftercare"
- NO faces or people references (HIPAA)
"""
        try:
            response = self.call_claude(prompt, max_tokens=300)
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                brief = json.loads(json_match.group())
                # Validate post_type
                if brief.get("post_type") not in POST_TYPES:
                    brief["post_type"] = "bold_headline"
                return brief
        except Exception as e:
            self.log(f"Brief generation failed: {e}")

        # Fallback brief
        return {
            "post_type": "motivational",
            "headline": "Recovery Starts Here",
            "subtext": "Take the first step today",
            "use_accent_bg": False,
        }

    # ------------------------------------------------------------------
    # Image generation — dispatches to layout renderers
    # ------------------------------------------------------------------

    def _generate_image(self, brief: dict, post: Post, brand_info: dict) -> Path | None:
        """Generate a professional branded image using Pillow."""
        platform = post.platform or "instagram"
        width, height = PLATFORM_SIZES.get(platform, (1080, 1080))

        primary = hex_to_rgb(brand_info["color"])
        accent = hex_to_rgb(brand_info["accent"])

        # If brief says use accent bg, swap primary/accent roles for background variety
        use_accent_bg = brief.get("use_accent_bg", False)

        img = Image.new("RGB", (width, height))

        headline = brief.get("headline", "Recovery Starts Here")
        subtext = brief.get("subtext", "Take the first step today")
        phone = brand_info.get("phones", {}).get(platform, "")
        brand_name = brand_info["name"]
        post_type = brief.get("post_type", "bold_headline")

        renderer = LAYOUT_RENDERERS.get(post_type, render_bold_headline)

        # For variety, some layouts can swap primary/accent
        if use_accent_bg and post_type in ("bold_headline", "motivational"):
            renderer(img, headline, subtext, phone, brand_name, accent, primary)
        else:
            renderer(img, headline, subtext, phone, brand_name, primary, accent)

        # Save
        uid = hashlib.md5(
            f"{post.id}-{post.brand_id}-{post.platform}-{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:10]
        filename = f"{post.brand_id}_{platform}_{uid}.png"
        filepath = IMAGES_DIR / filename

        img.save(filepath, "PNG", quality=95)
        return filepath
