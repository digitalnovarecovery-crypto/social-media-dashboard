"""Agent 3: Creative Director — Generates branded visuals using Pillow.

Schedule: Daily at 7am
Reads: today's draft posts from DB
Produces: image_url on each post (branded social media graphics)
"""
from __future__ import annotations

import math
import os
import textwrap
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from agents.base_agent import BaseAgent
from config import BRANDS, PROJECT_ROOT
from db.models import Post, get_db

# Where generated images are saved (Flask serves /static/ automatically)
GENERATED_DIR = PROJECT_ROOT / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# Public base URL for serving images
PUBLIC_URL = os.getenv(
    "PUBLIC_URL",
    os.getenv(
        "RAILWAY_PUBLIC_DOMAIN",
        "social-media-dashboard-production-a19f.up.railway.app",
    ),
)
# Normalise: strip protocol if provided, we'll add https://
if PUBLIC_URL.startswith("http"):
    _BASE = PUBLIC_URL.rstrip("/")
else:
    _BASE = f"https://{PUBLIC_URL.rstrip('/')}"

# Platform -> (width, height)
PLATFORM_SIZES = {
    "facebook": (1200, 630),
    "instagram": (1080, 1080),
    "tiktok": (1080, 1920),
    "linkedin": (1200, 627),
    "youtube": (1280, 720),
}


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _lighten(rgb: tuple, factor: float = 0.3) -> tuple[int, int, int]:
    return tuple(min(255, int(c + (255 - c) * factor)) for c in rgb)


def _darken(rgb: tuple, factor: float = 0.3) -> tuple[int, int, int]:
    return tuple(max(0, int(c * (1 - factor))) for c in rgb)


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Try to load a nice font; fall back gracefully."""
    candidates = [
        # Bold
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ] if bold else [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    # Absolute fallback
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def generate_branded_image(
    headline: str,
    platform: str,
    brand_info: dict,
    post_id: int,
    phone: str = "",
) -> str | None:
    """Generate a branded social media graphic and return its public URL."""
    w, h = PLATFORM_SIZES.get(platform, (1200, 630))
    primary = _hex_to_rgb(brand_info["color"])
    accent = _hex_to_rgb(brand_info["accent"])
    brand_name = brand_info["name"]

    img = Image.new("RGB", (w, h), primary)
    draw = ImageDraw.Draw(img)

    # --- Decorative gradient overlay (top-to-bottom darken) ---
    for y in range(h):
        factor = (y / h) * 0.4
        row_color = _darken(primary, factor)
        draw.line([(0, y), (w, y)], fill=row_color)

    # --- Accent bar at top ---
    bar_h = max(8, h // 80)
    draw.rectangle([0, 0, w, bar_h], fill=accent)

    # --- Accent bar at bottom ---
    draw.rectangle([0, h - bar_h, w, h], fill=accent)

    # --- Decorative accent stripe on left ---
    stripe_w = max(6, w // 150)
    draw.rectangle([0, bar_h, stripe_w, h - bar_h], fill=accent)

    # --- Brand name (top area) ---
    brand_font_size = max(20, min(w, h) // 20)
    brand_font = _get_font(brand_font_size, bold=True)
    brand_bbox = brand_font.getbbox(brand_name)
    brand_tw = brand_bbox[2] - brand_bbox[0]
    brand_x = (w - brand_tw) // 2
    brand_y = bar_h + max(20, h // 15)
    draw.text((brand_x, brand_y), brand_name, fill=accent, font=brand_font)

    # --- Small divider line under brand name ---
    div_y = brand_y + (brand_bbox[3] - brand_bbox[1]) + 15
    div_w = min(120, w // 5)
    draw.rectangle(
        [(w // 2 - div_w // 2, div_y), (w // 2 + div_w // 2, div_y + 3)],
        fill=accent,
    )

    # --- Headline text (center) ---
    headline_font_size = max(28, min(w, h) // 12)
    headline_font = _get_font(headline_font_size, bold=True)
    max_text_w = int(w * 0.8)
    lines = _wrap_text(headline, headline_font, max_text_w)

    # Limit to 5 lines max
    if len(lines) > 5:
        lines = lines[:5]
        lines[-1] = lines[-1][:40] + "..."

    line_h = headline_font.getbbox("Ay")[3] - headline_font.getbbox("Ay")[1]
    total_text_h = len(lines) * (line_h + 10)
    start_y = (h - total_text_h) // 2 + max(10, h // 20)

    for i, line in enumerate(lines):
        line_bbox = headline_font.getbbox(line)
        lw = line_bbox[2] - line_bbox[0]
        lx = (w - lw) // 2
        ly = start_y + i * (line_h + 10)
        # Text shadow
        draw.text((lx + 2, ly + 2), line, fill=_darken(primary, 0.5), font=headline_font)
        draw.text((lx, ly), line, fill=(255, 255, 255), font=headline_font)

    # --- Phone number (bottom area) ---
    if phone:
        phone_font_size = max(18, min(w, h) // 25)
        phone_font = _get_font(phone_font_size, bold=True)
        phone_bbox = phone_font.getbbox(phone)
        phone_tw = phone_bbox[2] - phone_bbox[0]
        phone_x = (w - phone_tw) // 2
        phone_y = h - bar_h - (phone_bbox[3] - phone_bbox[1]) - max(25, h // 12)

        # Phone icon placeholder (small circle)
        icon_r = phone_font_size // 4
        draw.ellipse(
            [phone_x - icon_r * 3, phone_y + 2, phone_x - icon_r, phone_y + icon_r * 2 + 2],
            fill=accent,
        )
        draw.text((phone_x, phone_y), phone, fill=accent, font=phone_font)

    # --- Small watermark ---
    wm_font = _get_font(max(12, min(w, h) // 50))
    wm_text = brand_info.get("short", brand_name[:3].upper())
    wm_bbox = wm_font.getbbox(wm_text)
    draw.text(
        (w - (wm_bbox[2] - wm_bbox[0]) - 15, h - bar_h - (wm_bbox[3] - wm_bbox[1]) - 10),
        wm_text,
        fill=(*accent, 128) if img.mode == "RGBA" else accent,
        font=wm_font,
    )

    # --- Save ---
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"{platform}_{post_id}_{ts}.png"
    filepath = GENERATED_DIR / filename
    img.save(str(filepath), "PNG", optimize=True)

    return f"{_BASE}/static/generated/{filename}"


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

    def _create_visuals(self, brand_id: str) -> int:
        db = get_db()

        posts = (
            db.query(Post)
            .filter_by(brand_id=brand_id, status="draft")
            .filter(Post.image_url == None)
            .all()
        )

        if not posts:
            self.log(f"No posts need visuals for {brand_id}")
            db.close()
            return 0

        brand_info = BRANDS[brand_id]
        count = 0

        for post in posts:
            # Step 1: Extract a short headline from the caption using Claude
            headline = self._extract_headline(brand_info, post)
            if not headline:
                headline = brand_info["name"]  # fallback

            # Step 2: Get the phone number for this brand/platform
            phone = brand_info.get("phones", {}).get(post.platform, "")

            # Step 3: Generate the branded image
            try:
                image_url = generate_branded_image(
                    headline=headline,
                    platform=post.platform,
                    brand_info=brand_info,
                    post_id=post.id,
                    phone=phone,
                )
                if image_url:
                    post.image_url = image_url
                    post.image_prompt = headline
                    count += 1
                    self.log(f"Generated visual for post {post.id} ({post.platform})")
                else:
                    self.log(f"Image generation returned None for post {post.id}")
            except Exception as e:
                self.log(f"Image generation error for post {post.id}: {e}")

        db.commit()
        db.close()
        self.log(f"Generated {count} visuals for {brand_id}")
        return count

    def _extract_headline(self, brand_info: dict, post: Post) -> str | None:
        """Use Claude to extract a short, punchy headline from the post caption."""
        prompt = f"""Extract a short, impactful headline (5-10 words max) from this social media caption for {brand_info['name']}.
The headline should be suitable for overlaying on a social media graphic.
Make it inspiring, hopeful, and recovery-focused.

Caption: {(post.caption or '')[:500]}

Return ONLY the headline text, nothing else. No quotes, no explanation."""
        try:
            return self.call_claude(prompt, max_tokens=50).strip().strip('"\'')
        except Exception as e:
            self.log(f"Headline extraction failed: {e}")
            return None
