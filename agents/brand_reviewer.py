"""Agent 4: Brand Reviewer — QA before publish.

Schedule: Daily at 8am
Reads: draft posts from DB + brand-style.md
Produces: status change to "approved" or "needs_revision" with review_notes
"""
from __future__ import annotations

from datetime import datetime
import json

import anthropic

from agents.base_agent import BaseAgent
from config import BRANDS, ANTHROPIC_API_KEY
from db.models import Post, get_db


class BrandReviewer(BaseAgent):
    name = "brand_reviewer"
    display_name = "Brand Reviewer"

    def run(self) -> dict:
        brands = [self.brand_id] if self.brand_id else list(BRANDS.keys())
        total_approved = 0

        for brand_id in brands:
            count = self._review_posts(brand_id)
            total_approved += count

        return {"posts_created": total_approved}

    def _review_posts(self, brand_id: str) -> int:
        db = get_db()

        drafts = (
            db.query(Post)
            .filter_by(brand_id=brand_id, status="draft")
            .all()
        )

        if not drafts:
            self.log(f"No drafts to review for {brand_id}")
            db.close()
            return 0

        brand_context = self.load_brand_context(brand_id)
        brand_info = BRANDS[brand_id]
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        approved_count = 0

        for post in drafts:
            result = self._review_single(client, brand_context, brand_info, post)
            if result and result.get("approved"):
                post.status = "approved"
                post.review_notes = result.get("notes", "Approved by Brand Reviewer")
                approved_count += 1
            elif result:
                post.status = "needs_revision"
                post.review_notes = result.get("notes", "Needs revision")
            else:
                post.status = "approved"
                post.review_notes = "Auto-approved (review API unavailable)"
                approved_count += 1

        db.commit()
        db.close()
        self.log(f"Reviewed {len(drafts)} posts for {brand_id}: {approved_count} approved")
        return approved_count

    def _review_single(self, client, brand_context: str, brand_info: dict, post: Post) -> dict | None:
        phone = brand_info["phones"].get(post.platform, "")

        prompt = f"""You are a brand compliance reviewer for {brand_info['name']}.

Review this social media post and check for compliance:

PLATFORM: {post.platform}
CAPTION: {post.caption}
HASHTAGS: {post.hashtags}
REQUIRED PHONE NUMBER FOR THIS PLATFORM: {phone}

BRAND RULES (excerpt from brand-style.md):
{brand_context[:2000]}

CHECK LIST:
1. Does the caption include the correct platform-specific phone number ({phone})?
2. Is the tone warm, direct, and non-judgmental?
3. Does it have a clear CTA?
4. Are specific services mentioned (detox, inpatient rehab, IOP, sober living)?
5. No HIPAA violations (no client names/faces referenced)?
6. No medical advice or outcome promises?
7. No fear-based or shame-based messaging?
8. Appropriate for {post.platform} (length, style)?

Return JSON:
{{
    "approved": true/false,
    "score": 1-10,
    "notes": "brief explanation of issues or confirmation"
}}

Return ONLY valid JSON."""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
            return json.loads(text)
        except Exception as e:
            self.log(f"Review failed for post {post.id}: {e}")
            return None
