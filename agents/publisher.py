"""Agent 5: Publisher — Publishes approved posts to platforms.

Schedule: Every 15 minutes (checks queue)
Reads: approved posts where scheduled_time <= now
Produces: status change to "published" + platform_post_id, or "failed" with error
"""
from __future__ import annotations

from datetime import datetime

from agents.base_agent import BaseAgent
from config import BRANDS
from db.models import Post, OAuthToken, get_db


class Publisher(BaseAgent):
    name = "publisher"
    display_name = "Publisher"

    def run(self) -> dict:
        db = get_db()
        now = datetime.utcnow()

        ready_posts = (
            db.query(Post)
            .filter_by(status="approved")
            .filter(Post.scheduled_time <= now)
            .order_by(Post.scheduled_time)
            .limit(10)
            .all()
        )

        if not ready_posts:
            self.log("No posts ready to publish")
            db.close()
            return {"posts_published": 0}

        published = 0
        for post in ready_posts:
            token = (
                db.query(OAuthToken)
                .filter_by(brand_id=post.brand_id, platform=post.platform)
                .first()
            )

            if not token or not token.access_token:
                self.log(
                    f"No API token for {post.brand_id}/{post.platform} — "
                    f"post {post.id} marked as scheduled (manual publish needed)"
                )
                post.status = "scheduled"
                continue

            success = self._publish_to_platform(post, token)
            if success:
                post.status = "published"
                post.published_time = datetime.utcnow()
                published += 1
            else:
                post.status = "failed"

        db.commit()
        db.close()
        return {"posts_published": published}

    def _publish_to_platform(self, post: Post, token: OAuthToken) -> bool:
        """Dispatch to the correct platform publisher."""
        try:
            if post.platform == "facebook":
                return self._publish_facebook(post, token)
            elif post.platform == "instagram":
                return self._publish_instagram(post, token)
            elif post.platform == "linkedin":
                return self._publish_linkedin(post, token)
            elif post.platform == "tiktok":
                return self._publish_tiktok(post, token)
            else:
                self.log(f"Unknown platform: {post.platform}")
                return False
        except Exception as e:
            self.log(f"Publish failed for post {post.id}: {e}")
            post.review_notes = f"Publish error: {e}"
            return False

    def _publish_facebook(self, post: Post, token: OAuthToken) -> bool:
        import requests

        url = f"https://graph.facebook.com/v19.0/{token.page_id}/feed"
        data = {
            "message": f"{post.caption}\n\n{post.hashtags or ''}".strip(),
            "access_token": token.access_token,
        }

        if post.image_url:
            url = f"https://graph.facebook.com/v19.0/{token.page_id}/photos"
            data["url"] = post.image_url

        resp = requests.post(url, data=data, timeout=30)
        if resp.ok:
            result = resp.json()
            post.platform_post_id = result.get("id", result.get("post_id", ""))
            self.log(f"Published to Facebook: {post.platform_post_id}")
            return True

        self.log(f"Facebook publish failed: {resp.text}")
        post.review_notes = f"FB error: {resp.text[:200]}"
        return False

    def _publish_instagram(self, post: Post, token: OAuthToken) -> bool:
        import requests

        if not post.image_url:
            self.log(f"Instagram requires an image — post {post.id} skipped")
            post.review_notes = "IG requires image_url"
            return False

        # Step 1: Create media container
        url = f"https://graph.facebook.com/v19.0/{token.page_id}/media"
        data = {
            "image_url": post.image_url,
            "caption": f"{post.caption}\n\n{post.hashtags or ''}".strip(),
            "access_token": token.access_token,
        }
        resp = requests.post(url, data=data, timeout=30)
        if not resp.ok:
            self.log(f"IG container creation failed: {resp.text}")
            return False

        container_id = resp.json().get("id")

        # Step 2: Publish the container
        publish_url = f"https://graph.facebook.com/v19.0/{token.page_id}/media_publish"
        pub_resp = requests.post(publish_url, data={
            "creation_id": container_id,
            "access_token": token.access_token,
        }, timeout=30)

        if pub_resp.ok:
            post.platform_post_id = pub_resp.json().get("id", "")
            self.log(f"Published to Instagram: {post.platform_post_id}")
            return True

        self.log(f"IG publish failed: {pub_resp.text}")
        return False

    def _publish_linkedin(self, post: Post, token: OAuthToken) -> bool:
        import requests

        url = "https://api.linkedin.com/rest/posts"
        headers = {
            "Authorization": f"Bearer {token.access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": "202401",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        body = {
            "author": f"urn:li:organization:{token.page_id}",
            "commentary": f"{post.caption}\n\n{post.hashtags or ''}".strip(),
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
            },
            "lifecycleState": "PUBLISHED",
        }

        resp = requests.post(url, json=body, headers=headers, timeout=30)
        if resp.ok or resp.status_code == 201:
            post.platform_post_id = resp.headers.get("x-restli-id", "")
            self.log(f"Published to LinkedIn: {post.platform_post_id}")
            return True

        self.log(f"LinkedIn publish failed: {resp.status_code} {resp.text}")
        return False

    def _publish_tiktok(self, post: Post, token: OAuthToken) -> bool:
        self.log(f"TikTok publishing requires video upload — post {post.id} marked for manual review")
        post.review_notes = "TikTok: requires video upload via Content Posting API (manual for now)"
        return False
