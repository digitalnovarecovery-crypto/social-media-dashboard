"""Agent 3: Creative Director — Visual direction + image prompt generation.

Schedule: Daily at 7am
Reads: today's draft posts from DB
Produces: image_prompt field on each post, ready for image generation
"""
from __future__ import annotations

from datetime import datetime
import json

import anthropic

from agents.base_agent import BaseAgent
from config import BRANDS, ANTHROPIC_API_KEY
from db.models import Post, get_db


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
            .filter(Post.image_prompt != None)
            .filter(Post.image_url == None)
            .all()
        )

        if not posts:
            self.log(f"No posts need visual direction for {brand_id}")
            db.close()
            return 0

        brand_context = self.load_brand_context(brand_id)
        brand_info = BRANDS[brand_id]
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        count = 0

        for post in posts:
            prompt = self._build_image_prompt(
                client, brand_context, brand_info, post
            )
            if prompt:
                post.image_prompt = prompt
                count += 1

        db.commit()
        db.close()
        self.log(f"Generated {count} image prompts for {brand_id}")
        return count

    def _build_image_prompt(self, client, brand_context: str, brand_info: dict, post: Post) -> str | None:
        prompt = f"""You are a creative director for a treatment center's social media.

Create a detailed image generation prompt for this social media post:

Platform: {post.platform}
Caption excerpt: {(post.caption or '')[:300]}
Visual direction note: {post.image_prompt or 'none'}
Brand color: {brand_info['color']}
Accent color: {brand_info['accent']}
Brand name: {brand_info['name']}

Requirements:
- NO faces or identifiable people (HIPAA compliance)
- Use brand colors prominently
- Include space for text overlay if it's a graphic post
- Nature imagery preferred: roads, forests, sunlight, paths
- Warm, hopeful mood
- Phone number must be legible if included in graphic

Return ONLY a single detailed image prompt string (no JSON, no markdown).
The prompt should follow this structure:
Subject + Composition + Location + Style + Lighting + Camera angle"""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            self.log(f"Image prompt generation failed: {e}")
            return None
