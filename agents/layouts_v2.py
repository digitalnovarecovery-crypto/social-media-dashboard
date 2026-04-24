"""
layouts_v2 — professional social post layouts for the Creative Director agent.

This module is a drop-in replacement for the layout renderers currently defined
inline inside agents/creative_director.py. To switch over, change the
LAYOUT_RENDERERS dict in creative_director.py to point here:

    from agents.layouts_v2 import (
        render_quote, render_bold_headline, render_cta,
        render_service_list, render_motivational,
    )
    LAYOUT_RENDERERS = {
        "quote":          render_quote,
        "bold_headline":  render_bold_headline,
        "cta":            render_cta,
        "service_list":   render_service_list,
        "motivational":   render_motivational,
    }

Design system (applied uniformly):
  * Background: warm off-white (#F8F5F0). Never flat brand color, never gradient.
  * Typography: Poppins (bundled) — Bold, SemiBold, Medium, Regular.
  * Headlines in sentence case, NEVER .upper().
  * ONE accent element per composition (a short rule under the eyebrow).
  * No drop shadows. No decorative dots. No corner arcs. No diagonal splits.
  * Consistent grid: 7.5% outer margin, content aligned left.
  * Hierarchy: eyebrow  →  headline  →  supporting copy  →  optional CTA  →  micro-text.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

_FONT_PREFS = {
    "bold":     ["Poppins-Bold.ttf", "Lato-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "semibold": ["Poppins-SemiBold.ttf", "Poppins-Bold.ttf", "Lato-Bold.ttf"],
    "medium":   ["Poppins-Medium.ttf", "Lato-Medium.ttf", "DejaVuSans.ttf"],
    "regular":  ["Poppins-Regular.ttf", "Lato-Regular.ttf", "DejaVuSans.ttf"],
}

# Search order: bundled in the repo first, then Debian system fonts.
_FONT_DIRS = [
    Path(__file__).parent.parent / "static" / "fonts",
    Path(__file__).parent / "fonts",
    Path("/usr/share/fonts/truetype/google-fonts"),
    Path("/usr/share/fonts/truetype/lato"),
    Path("/usr/share/fonts/truetype/dejavu"),
]

_font_cache: dict[str, str] = {}


def _find_font(weight: str) -> str:
    if weight in _font_cache:
        return _font_cache[weight]
    for filename in _FONT_PREFS.get(weight, []):
        for d in _FONT_DIRS:
            candidate = d / filename
            if candidate.exists():
                _font_cache[weight] = str(candidate)
                return str(candidate)
    _font_cache[weight] = ""
    return ""


def get_font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    path = _find_font(weight)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Palette + color helpers
# ---------------------------------------------------------------------------

RGB = Tuple[int, int, int]


def hex_to_rgb(hex_color: str) -> RGB:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def darken(c: RGB, amount: float = 0.75) -> RGB:
    return (int(c[0] * amount), int(c[1] * amount), int(c[2] * amount))


def mix(a: RGB, b: RGB, t: float) -> RGB:
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def tint_bg_for_brand(primary: RGB) -> RGB:
    """A *very slightly* tinted off-white, biased toward the brand color.
    Keeps the warm premium feel while still feeling brand-adjacent."""
    return mix((248, 245, 240), primary, 0.03)


# ---------------------------------------------------------------------------
# Shared palette (single source of truth)
# ---------------------------------------------------------------------------

BG_WARM = (248, 245, 240)        # #F8F5F0
INK = (22, 26, 34)               # near-black, slightly warm
MUTED = (92, 98, 112)            # supporting copy
HAIRLINE = (210, 203, 192)       # dividers / fine rules
WHITE = (255, 255, 255)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def measure(text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        w, _ = measure(trial, font)
        if w <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def fit_text(
    text: str,
    max_width: int,
    max_lines: int,
    start_size: int,
    min_size: int,
    weight: str = "bold",
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Find the largest font size that fits text in at most max_lines lines."""
    size = start_size
    while size >= min_size:
        font = get_font(size, weight)
        lines = wrap_lines(text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
        size -= 4
    font = get_font(min_size, weight)
    return font, wrap_lines(text, font, max_width)


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    x: int,
    y: int,
    color: RGB,
    line_height_ratio: float = 1.15,
    align: str = "left",
    canvas_width: int | None = None,
) -> int:
    _, line_h = measure("Ay", font)
    step = int(line_h * line_height_ratio)
    for line in lines:
        if align == "center" and canvas_width is not None:
            tw, _ = measure(line, font)
            cx = (canvas_width - tw) // 2
            draw.text((cx, y), line, fill=color, font=font)
        else:
            draw.text((x, y), line, fill=color, font=font)
        y += step
    return y


def draw_rounded_rect(draw: ImageDraw.ImageDraw, bbox, radius: int, fill: RGB):
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(bbox, radius=radius, fill=fill)
        return
    x0, y0, x1, y1 = bbox
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.pieslice([x0, y0, x0 + 2 * radius, y0 + 2 * radius], 180, 270, fill=fill)
    draw.pieslice([x1 - 2 * radius, y0, x1, y0 + 2 * radius], 270, 360, fill=fill)
    draw.pieslice([x0, y1 - 2 * radius, x0 + 2 * radius, y1], 90, 180, fill=fill)
    draw.pieslice([x1 - 2 * radius, y1 - 2 * radius, x1, y1], 0, 90, fill=fill)


# ---------------------------------------------------------------------------
# Common elements: eyebrow + accent rule, bottom signature
# ---------------------------------------------------------------------------

def _tracked(text: str) -> str:
    """Simulate letter-spacing by doubling spaces between words."""
    return "  ".join(text.split())


def _draw_eyebrow(
    draw: ImageDraw.ImageDraw,
    brand_name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    primary: RGB,
) -> int:
    """Eyebrow label + small accent rule. Returns y position after rule."""
    size = max(22, int(w * 0.026))
    font = get_font(size, "semibold")
    text = _tracked(brand_name.upper())
    draw.text((x, y), text, fill=primary, font=font)

    rule_y = y + size + int(h * 0.018)
    rule_w = int(w * 0.06)
    rule_h = max(3, int(h * 0.0035))
    draw.rectangle([x, rule_y, x + rule_w, rule_y + rule_h], fill=primary)
    return rule_y + rule_h


def _draw_signature(
    draw: ImageDraw.ImageDraw,
    brand_name: str,
    phone: str,
    x: int,
    y: int,
    w: int,
    align: str = "left",
):
    """Tiny bottom signature for layouts that don't already have the brand up top."""
    size = max(16, int(w * 0.018))
    font = get_font(size, "regular")
    text_parts = []
    if phone:
        text_parts.append(phone)
    text_parts.append("Confidential • 24/7")
    text = "   •   ".join(text_parts)
    if align == "center":
        tw, _ = measure(text, font)
        x = (w - tw) // 2
    draw.text((x, y), text, fill=MUTED, font=font)


# ---------------------------------------------------------------------------
# 1. CTA — headline + phone button (from the reference work)
# ---------------------------------------------------------------------------

def render_cta(
    img: Image.Image,
    headline: str,
    subtext: str,
    phone: str,
    brand_name: str,
    primary: RGB,
    accent: RGB,
):
    w, h = img.size
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w, h], fill=BG_WARM)

    margin_x = int(w * 0.075)
    content_w = w - 2 * margin_x

    rule_end = _draw_eyebrow(draw, brand_name, margin_x, int(h * 0.11), w, h, primary)

    head_font, head_lines = fit_text(
        headline, max_width=content_w, max_lines=4,
        start_size=int(w * 0.085), min_size=int(w * 0.055), weight="bold",
    )
    head_y = rule_end + int(h * 0.045)
    head_end = draw_text_block(draw, head_lines, head_font, margin_x, head_y,
                               color=INK, line_height_ratio=1.12)

    sub_font = get_font(max(24, int(w * 0.028)), "regular")
    sub_lines = wrap_lines(subtext, sub_font, content_w)
    sub_y = head_end + int(h * 0.02)
    draw_text_block(draw, sub_lines, sub_font, margin_x, sub_y,
                    color=MUTED, line_height_ratio=1.35)

    if phone:
        btn_size = max(32, int(w * 0.044))
        btn_font = get_font(btn_size, "semibold")
        btn_text = f"Call  {phone}"
        btn_tw, btn_th = measure(btn_text, btn_font)
        pad_x = int(w * 0.045)
        pad_y = int(btn_th * 0.55)
        btn_w = btn_tw + pad_x * 2
        btn_h = btn_th + pad_y * 2
        btn_y0 = int(h * 0.75)
        draw_rounded_rect(draw, (margin_x, btn_y0, margin_x + btn_w, btn_y0 + btn_h),
                          radius=btn_h // 2, fill=primary)
        bbox = btn_font.getbbox(btn_text)
        draw.text((margin_x + pad_x, btn_y0 + pad_y - bbox[1]),
                  btn_text, fill=WHITE, font=btn_font)
        micro_y = btn_y0 + btn_h + int(h * 0.025)
    else:
        micro_y = int(h * 0.88)

    micro_font = get_font(max(16, int(w * 0.018)), "regular")
    draw.text((margin_x, micro_y), "Confidential  •  Available 24/7",
              fill=MUTED, font=micro_font)


# ---------------------------------------------------------------------------
# 2. Bold headline — engagement question, no CTA button
# ---------------------------------------------------------------------------

def render_bold_headline(
    img: Image.Image,
    headline: str,
    subtext: str,
    phone: str,
    brand_name: str,
    primary: RGB,
    accent: RGB,
):
    w, h = img.size
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w, h], fill=BG_WARM)

    margin_x = int(w * 0.075)
    content_w = w - 2 * margin_x

    rule_end = _draw_eyebrow(draw, brand_name, margin_x, int(h * 0.11), w, h, primary)

    # Headline gets more room — up to 5 lines, with extra-large sizing
    head_font, head_lines = fit_text(
        headline, max_width=content_w, max_lines=5,
        start_size=int(w * 0.09), min_size=int(w * 0.055), weight="bold",
    )
    head_y = rule_end + int(h * 0.06)
    head_end = draw_text_block(draw, head_lines, head_font, margin_x, head_y,
                               color=INK, line_height_ratio=1.1)

    # Supporting line
    sub_font = get_font(max(26, int(w * 0.03)), "regular")
    sub_lines = wrap_lines(subtext, sub_font, content_w)
    sub_y = head_end + int(h * 0.025)
    draw_text_block(draw, sub_lines, sub_font, margin_x, sub_y,
                    color=MUTED, line_height_ratio=1.35)

    _draw_signature(draw, brand_name, phone, margin_x, int(h * 0.9), w)


# ---------------------------------------------------------------------------
# 3. Quote — large quote on tinted background
# ---------------------------------------------------------------------------

def render_quote(
    img: Image.Image,
    headline: str,
    subtext: str,
    phone: str,
    brand_name: str,
    primary: RGB,
    accent: RGB,
):
    w, h = img.size
    draw = ImageDraw.Draw(img)

    # Very subtle brand-tinted background — not a flat color, not a gradient
    draw.rectangle([0, 0, w, h], fill=tint_bg_for_brand(primary))

    margin_x = int(w * 0.10)
    content_w = w - 2 * margin_x

    # Large decorative quote mark at top-left, in brand primary, low-key
    mark_size = int(w * 0.18)
    mark_font = get_font(mark_size, "bold")
    draw.text((margin_x - int(w * 0.02), int(h * 0.08) - int(mark_size * 0.4)),
              "\u201C", fill=mix(primary, BG_WARM, 0.7), font=mark_font)

    # Headline (the quote) — centered vertically in a band
    head_font, head_lines = fit_text(
        headline, max_width=content_w, max_lines=5,
        start_size=int(w * 0.065), min_size=int(w * 0.042), weight="semibold",
    )
    _, line_h = measure("Ay", head_font)
    block_h = int(line_h * 1.25 * len(head_lines))
    head_y = int(h * 0.3)
    end_y = draw_text_block(draw, head_lines, head_font, margin_x, head_y,
                            color=INK, line_height_ratio=1.25)

    # Attribution (subtext)
    if subtext:
        attr_font = get_font(max(22, int(w * 0.024)), "medium")
        attr_text = f"— {subtext}"
        attr_lines = wrap_lines(attr_text, attr_font, content_w)
        draw_text_block(draw, attr_lines, attr_font, margin_x, end_y + int(h * 0.02),
                        color=MUTED, line_height_ratio=1.35)

    # Brand mark + phone at bottom — minimal
    _draw_signature(draw, brand_name, phone, margin_x, int(h * 0.9), w)


# ---------------------------------------------------------------------------
# 4. Service list — headline + checklist
# ---------------------------------------------------------------------------

def render_service_list(
    img: Image.Image,
    headline: str,
    subtext: str,
    phone: str,
    brand_name: str,
    primary: RGB,
    accent: RGB,
):
    w, h = img.size
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w, h], fill=BG_WARM)

    margin_x = int(w * 0.075)
    content_w = w - 2 * margin_x

    rule_end = _draw_eyebrow(draw, brand_name, margin_x, int(h * 0.09), w, h, primary)

    # Shorter headline — 3 lines max
    head_font, head_lines = fit_text(
        headline, max_width=content_w, max_lines=3,
        start_size=int(w * 0.07), min_size=int(w * 0.05), weight="bold",
    )
    head_y = rule_end + int(h * 0.04)
    list_start_y = draw_text_block(draw, head_lines, head_font, margin_x, head_y,
                                   color=INK, line_height_ratio=1.15)
    list_start_y += int(h * 0.035)

    # Split subtext by comma/semicolon/pipe into bullet items
    import re
    items = [i.strip() for i in re.split(r"[,;|]", subtext) if i.strip()]
    if not items:
        items = [subtext]

    bullet_size = max(28, int(w * 0.036))
    bullet_font = get_font(bullet_size, "medium")
    line_step = int(bullet_size * 1.7)

    y = list_start_y
    for item in items[:6]:
        # Draw a small filled circle as the bullet — no Unicode checkmarks
        dot_r = max(5, int(bullet_size * 0.12))
        dot_cx = margin_x + dot_r + 2
        dot_cy = y + int(bullet_size * 0.55)
        draw.ellipse([dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
                     fill=primary)
        # Item text
        text_x = margin_x + dot_r * 2 + int(w * 0.022)
        # Wrap long items
        item_lines = wrap_lines(item, bullet_font, content_w - (text_x - margin_x))
        for j, il in enumerate(item_lines):
            draw.text((text_x, y), il, fill=INK, font=bullet_font)
            y += line_step if j == 0 else int(bullet_size * 1.35)
        y += int(bullet_size * 0.15)  # small gap between items

    _draw_signature(draw, brand_name, phone, margin_x, int(h * 0.92), w)


# ---------------------------------------------------------------------------
# 5. Motivational — centered composition, uplifting feel
# ---------------------------------------------------------------------------

def render_motivational(
    img: Image.Image,
    headline: str,
    subtext: str,
    phone: str,
    brand_name: str,
    primary: RGB,
    accent: RGB,
):
    w, h = img.size
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w, h], fill=tint_bg_for_brand(primary))

    margin_x = int(w * 0.10)
    content_w = w - 2 * margin_x

    # Small brand eyebrow at top-center
    eyebrow_font = get_font(max(22, int(w * 0.024)), "semibold")
    eyebrow_text = _tracked(brand_name.upper())
    etw, eth = measure(eyebrow_text, eyebrow_font)
    draw.text(((w - etw) // 2, int(h * 0.10)), eyebrow_text, fill=primary, font=eyebrow_font)

    # Short accent rule, centered
    rule_w = int(w * 0.06)
    rule_h = max(3, int(h * 0.0035))
    rule_y = int(h * 0.10) + eth + int(h * 0.02)
    draw.rectangle([(w - rule_w) // 2, rule_y, (w + rule_w) // 2, rule_y + rule_h], fill=primary)

    # Headline — larger, centered, sentence case
    head_font, head_lines = fit_text(
        headline, max_width=content_w, max_lines=5,
        start_size=int(w * 0.08), min_size=int(w * 0.052), weight="bold",
    )
    _, line_h = measure("Ay", head_font)
    block_h = int(line_h * 1.2 * len(head_lines))
    head_y = int((h - block_h) / 2) - int(h * 0.02)
    end_y = draw_text_block(draw, head_lines, head_font, margin_x, head_y,
                            color=INK, line_height_ratio=1.2,
                            align="center", canvas_width=w)

    # Subtext
    sub_font = get_font(max(24, int(w * 0.028)), "regular")
    sub_lines = wrap_lines(subtext, sub_font, content_w)
    draw_text_block(draw, sub_lines, sub_font, margin_x, end_y + int(h * 0.025),
                    color=MUTED, line_height_ratio=1.35,
                    align="center", canvas_width=w)

    _draw_signature(draw, brand_name, phone, 0, int(h * 0.92), w, align="center")
