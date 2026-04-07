"""Agent 3: Creative Director — Generates actual branded visuals via Canva API.

Schedule: Daily at 7am
Reads: today's draft posts from DB
Produces: image_url on each post (actual Canva-generated images)
"""
from __future__ import annotations

import time
from datetime import datetime

import requests

from agents.base_agent import BaseAgent
from config import BRANDS, CANVA_API_TOKEN, CANVA_BRAND_KIT_ID
from db.models import Post, get_db

CANVA_BASE = "https://api.canva.com/rest/v1"

# Map platform to Canva design type
DESIGN_TYPE_MAP = {
    "facebook": "facebook_post",
    "instagram": "instagram_post",
    "tiktok": "your_story",      # vertical format for TikTok
    "linkedin": "facebook_post",  # similar landscape format
    "youtube": "youtube_thumbnail",
}


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

        brand_context = self.load_brand_context(brand_id)
        brand_info = BRANDS[brand_id]
        count = 0

        for post in posts:
            # Step 1: Generate design concept via Claude
            design_query = self._build_design_query(brand_info, post)
            if not design_query:
                continue

            # Step 2: Generate actual image via Canva API
            image_url = self._generate_canva_image(design_query, post.platform, brand_info)
            if image_url:
                post.image_url = image_url
                post.image_prompt = design_query  # store the query for reference
                count += 1
                self.log(f"Generated visual for post {post.id} ({post.platform})")
            else:
                # Fallback: just store the prompt for manual creation
                post.image_prompt = design_query
                self.log(f"Canva unavailable — stored prompt for post {post.id}")

        db.commit()
        db.close()
        self.log(f"Generated {count} visuals for {brand_id}")
        return count

    def _build_design_query(self, brand_info: dict, post: Post) -> str | None:
        """Use Claude to create a detailed Canva design query."""
        prompt = f"""You are a creative director for {brand_info['name']}, a treatment center.

Write a concise Canva design generation query for this social media post:

Platform: {post.platform}
Content type: {post.content_type or 'post'}
Caption excerpt: {(post.caption or '')[:300]}
Visual direction: {post.image_prompt or 'brand-consistent social media graphic'}
Brand primary color: {brand_info['color']}
Brand accent color: {brand_info['accent']}

Requirements:
- NO faces or identifiable people (HIPAA compliance)
- Use brand colors: primary {brand_info['color']}, accent {brand_info['accent']}
- Nature imagery preferred: roads, forests, sunlight, paths, mountains
- Warm, hopeful, professional mood
- Include headline text from the caption
- Include phone number in accent color if relevant
- Professional healthcare brand feel

Return ONLY a single Canva design query string (2-4 sentences max). No JSON, no markdown.
Example: "Create a Facebook post with dark blue background and gold accents. Show a misty forest path at sunrise with the headline 'Recovery Starts Here' in bold white text. Include phone number (737) 345-0811 in gold at the bottom."
"""
        try:
            return self.call_claude(prompt, max_tokens=300).strip()
        except Exception as e:
            self.log(f"Design query generation failed: {e}")
            return None

    def _generate_canva_image(self, query: str, platform: str, brand_info: dict) -> str | None:
        """Generate image via Canva Connect API and return the public URL."""
        if not CANVA_API_TOKEN:
            self.log("No CANVA_API_TOKEN configured — skipping image generation")
            return None

        headers = {
            "Authorization": f"Bearer {CANVA_API_TOKEN}",
            "Content-Type": "application/json",
        }

        design_type = DESIGN_TYPE_MAP.get(platform, "facebook_post")

        # Step 1: Generate design
        gen_payload = {
            "design_type": {"name": design_type},
            "query": query,
        }
        if CANVA_BRAND_KIT_ID:
            gen_payload["brand_kit_id"] = CANVA_BRAND_KIT_ID

        try:
            resp = requests.post(
                f"{CANVA_BASE}/designs/autofill",
                json=gen_payload,
                headers=headers,
                timeout=60,
            )

            # Try the Magic Design endpoint if autofill fails
            if not resp.ok:
                resp = requests.post(
                    f"{CANVA_BASE}/ai/designs",
                    json=gen_payload,
                    headers=headers,
                    timeout=60,
                )

            if not resp.ok:
                self.log(f"Canva design generation failed: {resp.status_code} {resp.text[:200]}")
                return None

            result = resp.json()
            design_id = result.get("design", {}).get("id")
            if not design_id:
                # Check for job-based response
                job_id = result.get("job", {}).get("id")
                if job_id:
                    design_id = self._poll_canva_job(job_id, headers)

            if not design_id:
                self.log("No design_id returned from Canva")
                return None

            # Step 2: Export as PNG
            export_resp = requests.post(
                f"{CANVA_BASE}/exports",
                json={
                    "design_id": design_id,
                    "format": {"type": "png", "width": 1200},
                },
                headers=headers,
                timeout=60,
            )

            if not export_resp.ok:
                self.log(f"Canva export failed: {export_resp.status_code}")
                return None

            export_result = export_resp.json()
            export_job_id = export_result.get("job", {}).get("id")
            if export_job_id:
                return self._poll_export_job(export_job_id, headers)

            # Direct URL response
            urls = export_result.get("urls", [])
            if urls:
                return urls[0]

            return None

        except Exception as e:
            self.log(f"Canva API error: {e}")
            return None

    def _poll_canva_job(self, job_id: str, headers: dict, max_attempts: int = 10) -> str | None:
        """Poll a Canva job until completion."""
        for _ in range(max_attempts):
            time.sleep(3)
            resp = requests.get(f"{CANVA_BASE}/ai/designs/{job_id}", headers=headers, timeout=30)
            if resp.ok:
                data = resp.json()
                status = data.get("job", {}).get("status")
                if status == "success":
                    designs = data.get("job", {}).get("result", {}).get("generated_designs", [])
                    if designs:
                        return designs[0].get("design_id") or designs[0].get("id")
                elif status == "failed":
                    return None
        return None

    def _poll_export_job(self, job_id: str, headers: dict, max_attempts: int = 10) -> str | None:
        """Poll a Canva export job until completion."""
        for _ in range(max_attempts):
            time.sleep(3)
            resp = requests.get(f"{CANVA_BASE}/exports/{job_id}", headers=headers, timeout=30)
            if resp.ok:
                data = resp.json()
                status = data.get("job", {}).get("status")
                if status == "success":
                    urls = data.get("job", {}).get("result", {}).get("urls", [])
                    if urls:
                        return urls[0]
                elif status == "failed":
                    return None
        return None
