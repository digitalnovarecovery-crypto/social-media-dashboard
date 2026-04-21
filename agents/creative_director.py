"""Agent 3: Creative Director — Generates professional branded visuals using Pillow.

Schedule: Daily at 7am
Reads: today's draft posts from DB
Produces: image_url on each post (locally generated branded images served via /static/)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import textwrap
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from agents.base_agent import BaseAgent
from config import BRANDS, PROJECT_ROOT
from db.models import Post, get_db

# Platform-specific image dimensions
PLATFORM_SIZES = {
    "facebook": (1200, 630),
    "instagram": (1080, 1080),
    "tiktok": (1080, 1920),
    "linkedin": (1200, 627),
    "youtube": (1280, 720),
}

# Ensure static/images directory exists
IMAGES_DIR = PROJECT_ROOT / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert #RRGGBB to (R, G, B)."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def darken(rgb: tuple, factor: float = 0.6) -> tuple[int, int, int]:
    return tuple(max(0, int(c * factor)) for c in rgb)


def lighten(rgb: tuple, factor: float = 0.3) -> tuple[int, int, int]:
    return tuple(min(255, int(c + (255 - c) * factor)) for c in rgb)


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get the best available font. Falls back to default if none found."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/ubuntu/Ubuntu-Regular.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    # Last resort
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


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
            try:
                # Step 1: Generate creative brief via Claude
                brief = self._generate_brief(brand_info, post)

                # Step 2: Generate branded image
                image_path = self._generate_image(brief, post, brand_info)

                if image_path:
                    # Store as relative URL path for serving via /static/
                    post.image_url = f"/static/images/{image_path.name}"
                    post.image_prompt = brief.get("headline", "")
                    count += 1
                    self.log(f"Generated visual for post {post.id} ({post.platform})")
            except Exception as e:
                self.log(f"Failed to generate visual for post {post.id}: {e}")

        db.commit()
        db.close()
        self.log(f"Generated {count} visuals for {brand_id}")
        return count

    def _generate_brief(self, brand_info: dict, post: Post) -> dict:
        """Use Claude to generate a creative brief for the image."""
        prompt = f"""You are a creative director for {brand_info['name']}.

Generate a creative brief for a social media image. Return ONLY valid JSON, no other text.

Platform: {post.platform}
Caption: {(post.caption or '')[:400]}
Brand colors: primary {brand_info['color']}, accent {brand_info['accent']}

Return this exact JSON structure:
{{
  "headline": "Short impactful headline (max 6 words)",
  "subtext": "One supporting line (max 12 words)",
  "mood": "one of: sunrise, forest, ocean, mountain, sky, garden, path, light",
  "layout": "one of: centered, split, bottom_bar, overlay",
  "emoji_accent": "one relevant emoji"
}}

Requirements:
- Headline should be punchy and motivational
- Subtext should support the headline
- NO faces or people references (HIPAA)
- Nature and recovery themed
"""
        try:
            response = self.call_claude(prompt, max_tokens=200)
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            self.log(f"Brief generation failed: {e}")

        # Fallback brief
        return {
            "headline": "Your Recovery Journey",
            "subtext": "Take the first step today",
            "mood": "sunrise",
            "layout": "centered",
            "emoji_accent": "🌅",
        }

    def _generate_image(self, brief: dict, post: Post, brand_info: dict) -> Path | None:
        """Generate a professional branded image using Pillow."""
        platform = post.platform or "instagram"
        width, height = PLATFORM_SIZES.get(platform, (1080, 1080))

        primary = hex_to_rgb(brand_info["color"])
        accent = hex_to_rgb(brand_info["accent"])
        primary_dark = darken(primary, 0.4)
        primary_light = lighten(primary, 0.15)

        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        mood = brief.get("mood", "sunrise")
        layout = brief.get("layout", "centered")

        # === BACKGROUND: Rich gradient based on mood ===
        self._draw_gradient_background(draw, width, height, primary, primary_dark, primary_light, mood)

        # === DECORATIVE ELEMENTS ===
        self._draw_decorative_elements(draw, width, height, accent, mood)

        # === BRAND ACCENT BAR (top) ===
        bar_height = max(6, int(height * 0.008))
        draw.rectangle([(0, 0), (width, bar_height)], fill=accent)

        # === CONTENT LAYOUT ===
        headline = brief.get("headline", "Recovery Starts Here")
        subtext = brief.get("subtext", "Take the first step today")
        emoji = brief.get("emoji_accent", "")
        phone = brand_info.get("phones", {}).get(platform, "")
        brand_name = brand_info["name"]

        if layout == "bottom_bar":
            self._layout_bottom_bar(draw, img, width, height, headline, subtext, phone, brand_name, emoji, primary, accent)
        elif layout == "split":
            self._layout_split(draw, img, width, height, headline, subtext, phone, brand_name, emoji, primary, accent)
        else:
            self._layout_centered(draw, img, width, height, headline, subtext, phone, brand_name, emoji, primary, accent)

        # === SAVE ===
        uid = hashlib.md5(f"{post.id}-{post.brand_id}-{post.platform}".encode()).hexdigest()[:10]
        filename = f"{post.brand_id}_{platform}_{uid}.png"
        filepath = IMAGES_DIR / filename
        img.save(filepath, "PNG", quality=95)
        return filepath

    def _draw_gradient_background(self, draw, w, h, primary, primary_dark, primary_light, mood):
        """Draw a rich multi-stop gradient background."""
        # Color schemes based on mood
        mood_colors = {
            "sunrise": [(primary_dark[0], primary_dark[1], primary_dark[2]),
                        (min(255, primary[0] + 40), primary[1], max(0, primary[2] - 20)),
                        (min(255, primary_light[0] + 30), min(255, primary_light[1] + 20), primary_light[2])],
            "forest": [darken(primary, 0.3), primary, lighten(primary, 0.1)],
            "ocean": [(primary_dark[0], max(0, primary_dark[1] - 10), min(255, primary_dark[2] + 30)),
                      primary,
                      (primary_light[0], primary_light[1], min(255, primary_light[2] + 20))],
            "mountain": [darken(primary, 0.25), primary, lighten(primary, 0.2)],
            "sky": [(max(0, primary[0] - 20), max(0, primary[1] - 10), min(255, primary[2] + 40)),
                    primary,
                    lighten(primary, 0.25)],
            "garden": [darken(primary, 0.35), primary, lighten(primary, 0.15)],
            "path": [primary_dark, primary, primary_light],
            "light": [primary, lighten(primary, 0.2), lighten(primary, 0.35)],
        }

        colors = mood_colors.get(mood, mood_colors["sunrise"])

        # Draw gradient with 3 color stops
        for y in range(h):
            ratio = y / h
            if ratio < 0.5:
                # First half: color[0] → color[1]
                t = ratio * 2
                r = int(colors[0][0] + (colors[1][0] - colors[0][0]) * t)
                g = int(colors[0][1] + (colors[1][1] - colors[0][1]) * t)
                b = int(colors[0][2] + (colors[1][2] - colors[0][2]) * t)
            else:
                # Second half: color[1] → color[2]
                t = (ratio - 0.5) * 2
                r = int(colors[1][0] + (colors[2][0] - colors[1][0]) * t)
                g = int(colors[1][1] + (colors[2][1] - colors[1][1]) * t)
                b = int(colors[1][2] + (colors[2][2] - colors[1][2]) * t)

            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            draw.line([(0, y), (w, y)], fill=(r, g, b))

    def _draw_decorative_elements(self, draw, w, h, accent, mood):
        """Add subtle decorative geometric elements."""
        accent_faded = (*accent, 35)  # Very transparent

        # Create a temporary RGBA image for transparency
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)

        # Subtle circles in corners
        circle_r = int(min(w, h) * 0.15)
        odraw.ellipse(
            [w - circle_r - 20, -circle_r // 2, w + circle_r - 20, circle_r + circle_r // 2],
            fill=(*accent, 20)
        )
        odraw.ellipse(
            [-circle_r // 2, h - circle_r - 20, circle_r + circle_r // 2, h + circle_r - 20],
            fill=(*accent, 15)
        )

        # Diagonal accent line
        line_width = max(2, int(w * 0.003))
        odraw.line(
            [(int(w * 0.7), 0), (w, int(h * 0.3))],
            fill=(*accent, 25), width=line_width
        )
        odraw.line(
            [(0, int(h * 0.7)), (int(w * 0.3), h)],
            fill=(*accent, 20), width=line_width
        )

        # Convert back and composite
        # We'll just draw faded accent elements directly since base is RGB
        # Use simpler approach - draw very dark accent shapes
        faded = tuple(max(0, c // 8) for c in accent)
        draw.ellipse(
            [w - circle_r - 20, -circle_r // 2, w + circle_r - 20, circle_r + circle_r // 2],
            fill=None, outline=(*accent,), width=1
        )

    def _layout_centered(self, draw, img, w, h, headline, subtext, phone, brand_name, emoji, primary, accent):
        """Centered layout — headline in middle, subtext below."""
        # Headline
        headline_size = int(min(w, h) * 0.07)
        headline_font = get_font(headline_size, bold=True)
        lines = textwrap.wrap(headline.upper(), width=max(12, int(w / (headline_size * 0.55))))

        total_text_h = len(lines) * (headline_size + 10)
        y_start = (h // 2) - total_text_h - 20

        # Draw headline with shadow
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=headline_font)
            tw = bbox[2] - bbox[0]
            x = (w - tw) // 2
            y = y_start + i * (headline_size + 14)
            # Shadow
            draw.text((x + 2, y + 2), line, fill=(0, 0, 0), font=headline_font)
            # Main text
            draw.text((x, y), line, fill=(255, 255, 255), font=headline_font)

        # Accent divider line
        divider_y = y_start + total_text_h + 20
        divider_w = int(w * 0.2)
        draw.rectangle(
            [(w // 2 - divider_w // 2, divider_y), (w // 2 + divider_w // 2, divider_y + 4)],
            fill=accent
        )

        # Subtext
        sub_size = int(headline_size * 0.45)
        sub_font = get_font(sub_size)
        sub_y = divider_y + 20
        bbox = draw.textbbox((0, 0), subtext, font=sub_font)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2 + 1, sub_y + 1), subtext, fill=(0, 0, 0), font=sub_font)
        draw.text(((w - tw) // 2, sub_y), subtext, fill=(230, 230, 230), font=sub_font)

        # Brand name at bottom
        self._draw_brand_footer(draw, w, h, brand_name, phone, accent, primary)

    def _layout_bottom_bar(self, draw, img, w, h, headline, subtext, phone, brand_name, emoji, primary, accent):
        """Bottom bar layout — content sits in a bar at the bottom."""
        bar_h = int(h * 0.35)
        bar_y = h - bar_h

        # Semi-dark overlay bar
        for y in range(bar_y, h):
            ratio = (y - bar_y) / bar_h
            alpha = int(180 + ratio * 60)
            r = int(primary[0] * alpha / 255)
            g = int(primary[1] * alpha / 255)
            b = int(primary[2] * alpha / 255)
            draw.line([(0, y), (w, y)], fill=(r, g, b))

        # Accent line at top of bar
        draw.rectangle([(0, bar_y), (w, bar_y + 3)], fill=accent)

        # Headline in bar
        headline_size = int(min(w, h) * 0.055)
        headline_font = get_font(headline_size, bold=True)
        margin = int(w * 0.08)
        lines = textwrap.wrap(headline.upper(), width=max(15, int((w - margin * 2) / (headline_size * 0.55))))

        y = bar_y + int(bar_h * 0.15)
        for line in lines:
            draw.text((margin + 2, y + 2), line, fill=(0, 0, 0), font=headline_font)
            draw.text((margin, y), line, fill=(255, 255, 255), font=headline_font)
            y += headline_size + 10

        # Subtext
        sub_size = int(headline_size * 0.45)
        sub_font = get_font(sub_size)
        y += 8
        draw.text((margin, y), subtext, fill=accent, font=sub_font)

        # Brand + phone at very bottom
        self._draw_brand_footer(draw, w, h, brand_name, phone, accent, primary)

    def _layout_split(self, draw, img, w, h, headline, subtext, phone, brand_name, emoji, primary, accent):
        """Split layout — accent panel on left, content on right."""
        panel_w = int(w * 0.06)

        # Accent panel
        draw.rectangle([(0, 0), (panel_w, h)], fill=accent)

        # Headline
        headline_size = int(min(w, h) * 0.065)
        headline_font = get_font(headline_size, bold=True)
        margin = panel_w + int(w * 0.06)
        max_text_w = w - margin - int(w * 0.06)
        lines = textwrap.wrap(headline.upper(), width=max(12, int(max_text_w / (headline_size * 0.55))))

        y = int(h * 0.3)
        for line in lines:
            draw.text((margin + 2, y + 2), line, fill=(0, 0, 0), font=headline_font)
            draw.text((margin, y), line, fill=(255, 255, 255), font=headline_font)
            y += headline_size + 12

        # Divider
        y += 10
        draw.rectangle([(margin, y), (margin + int(w * 0.15), y + 4)], fill=accent)
        y += 20

        # Subtext
        sub_size = int(headline_size * 0.45)
        sub_font = get_font(sub_size)
        draw.text((margin, y), subtext, fill=(220, 220, 220), font=sub_font)

        # Brand + phone
        self._draw_brand_footer(draw, w, h, brand_name, phone, accent, primary)

    def _draw_brand_footer(self, draw, w, h, brand_name, phone, accent, primary):
        """Draw brand name and phone number at the bottom."""
        footer_h = int(h * 0.08)
        footer_y = h - footer_h

        # Darker footer background
        for y in range(footer_y, h):
            draw.line([(0, y), (w, y)], fill=darken(primary, 0.3))

        # Accent line above footer
        draw.rectangle([(0, footer_y), (w, footer_y + 2)], fill=accent)

        # Brand name (left)
        brand_size = int(footer_h * 0.35)
        brand_font = get_font(brand_size, bold=True)
        margin = int(w * 0.04)
        brand_y = footer_y + (footer_h - brand_size) // 2
        draw.text((margin, brand_y), brand_name.upper(), fill=accent, font=brand_font)

        # Phone number (right)
        if phone:
            phone_size = int(footer_h * 0.32)
            phone_font = get_font(phone_size, bold=True)
            bbox = draw.textbbox((0, 0), phone, font=phone_font)
            phone_w = bbox[2] - bbox[0]
            phone_y = footer_y + (footer_h - phone_size) // 2
            draw.text((w - phone_w - margin, phone_y), phone, fill=(255, 255, 255), font=phone_font)
