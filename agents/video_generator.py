"""Agent: Video Generator — Creates AI Twin talking-head videos via Captions.ai API.

Uses the AI Creator API (api.captions.ai) to generate short-form videos
with AI Twins (Ron, Daniel, Elianna) for TikTok and other video platforms.

Schedule: Daily at 7:30am (after Creative Director)
Reads: draft/approved posts that need videos (TikTok, YouTube Shorts, Reels)
Produces: video_url on each post
"""
from __future__ import annotations

import os
import time
from datetime import datetime

import requests

from agents.base_agent import BaseAgent
from config import BRANDS, PROJECT_ROOT
from db.models import Post, get_db

# Captions.ai / Mirage API configuration
CAPTIONS_API_KEY = os.getenv("CAPTIONS_API_KEY", "")
CAPTIONS_API_BASE = "https://api.captions.ai/api/creator"

# AI Twin assignments per brand (discovered from account)
AI_TWIN_MAP = {
    "nova": "Ron",
    "briarwood": "Daniel",
    "eudaimonia": "Elianna",
}

# Fallback community creator if no twin assigned
DEFAULT_CREATOR = "Ron"

# Platforms that get video content
VIDEO_PLATFORMS = {"tiktok", "youtube"}

# Max script length (API limit: 800 chars)
MAX_SCRIPT_LENGTH = 780

# Poll settings
POLL_INTERVAL = 15  # seconds between poll attempts
POLL_MAX_ATTEMPTS = 40  # ~10 minutes max wait


class VideoGenerator(BaseAgent):
    name = "video_generator"
    display_name = "Video Generator"

    def run(self) -> dict:
        if not CAPTIONS_API_KEY:
            self.log("ERROR: CAPTIONS_API_KEY not set. Skipping video generation.")
            return {"posts_created": 0}

        brands = [self.brand_id] if self.brand_id else list(BRANDS.keys())
        total = 0

        # List available creators first
        creators = self._list_creators()
        if creators:
            self.log(f"Available creators: {', '.join(creators)}")

        for brand_id in brands:
            count = self._generate_videos(brand_id, creators)
            total += count

        return {"posts_created": total}

    def _list_creators(self) -> list[str]:
        """List available AI creators/twins from the API."""
        try:
            resp = requests.post(
                f"{CAPTIONS_API_BASE}/list",
                headers={
                    "x-api-key": CAPTIONS_API_KEY,
                    "Content-Type": "application/json",
                },
                json={},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                # Response may be a list of creator names or objects
                if isinstance(data, list):
                    names = []
                    for item in data:
                        if isinstance(item, str):
                            names.append(item)
                        elif isinstance(item, dict):
                            names.append(item.get("name", item.get("creatorName", str(item))))
                    return names
                elif isinstance(data, dict) and "creators" in data:
                    return [c.get("name", str(c)) for c in data["creators"]]
            self.log(f"List creators response ({resp.status_code}): {resp.text[:200]}")
            return []
        except Exception as e:
            self.log(f"Failed to list creators: {e}")
            return []

    def _generate_videos(self, brand_id: str, available_creators: list[str]) -> int:
        db = get_db()

        # Find posts that need video (TikTok/YouTube, no video_url yet)
        posts = (
            db.query(Post)
            .filter_by(brand_id=brand_id)
            .filter(Post.status.in_(["draft", "approved", "scheduled"]))
            .filter(Post.platform.in_(VIDEO_PLATFORMS))
            .filter((Post.video_url == None) | (Post.video_url == ""))
            .order_by(Post.id)
            .limit(5)  # Process max 5 videos per brand per run (credit conservation)
            .all()
        )

        if not posts:
            self.log(f"No posts need videos for {brand_id}")
            db.close()
            return 0

        brand_info = BRANDS[brand_id]
        creator = AI_TWIN_MAP.get(brand_id, DEFAULT_CREATOR)

        # Validate creator exists in available list
        if available_creators and creator not in available_creators:
            # Try case-insensitive match
            match = next((c for c in available_creators if c.lower() == creator.lower()), None)
            if match:
                creator = match
            else:
                self.log(f"WARNING: Creator '{creator}' not found. Available: {available_creators}")
                # Use first available creator
                creator = available_creators[0] if available_creators else creator

        count = 0
        for post in posts:
            try:
                video_url = self._create_video(brand_info, post, creator)
                if video_url:
                    post.video_url = video_url
                    count += 1
                    self.log(f"Video generated for post {post.id} ({post.platform}): {video_url[:80]}...")
                else:
                    self.log(f"Video generation returned None for post {post.id}")
            except Exception as e:
                self.log(f"Video generation error for post {post.id}: {e}")

        db.commit()
        db.close()
        self.log(f"Generated {count} videos for {brand_id}")
        return count

    def _create_video(self, brand_info: dict, post: Post, creator_name: str) -> str | None:
        """Generate a video using the Captions AI Creator API."""

        # Step 1: Generate a video script from the post caption using Claude
        script = self._generate_script(brand_info, post)
        if not script:
            self.log(f"Script generation failed for post {post.id}")
            return None

        self.log(f"Script for post {post.id} ({len(script)} chars): {script[:100]}...")

        # Step 2: Submit video generation request
        operation_id = self._submit_video(creator_name, script)
        if not operation_id:
            return None

        self.log(f"Submitted video job {operation_id} for post {post.id}")

        # Step 3: Poll until complete
        video_url = self._poll_video(operation_id)
        return video_url

    def _generate_script(self, brand_info: dict, post: Post) -> str | None:
        """Use Claude to create a short, engaging video script from the post caption."""
        brand_name = brand_info["name"]
        phone = brand_info.get("phones", {}).get(post.platform, "")

        prompt = f"""You are a scriptwriter for {brand_name}, a addiction recovery/treatment center.
Write a short, engaging video script for a TikTok/short-form video.
The script will be read by an AI presenter (talking head).

Rules:
- Maximum 780 characters (STRICT LIMIT - this is an API constraint)
- Speak directly to the viewer ("you", "your")
- Warm, empathetic, hopeful tone
- Include a clear call to action at the end (mention calling {phone} if provided)
- No stage directions, no [brackets], no emojis
- Write as natural spoken words — this will be read aloud
- Keep it 20-40 seconds when spoken (roughly 60-120 words)

Post caption to base the script on:
{(post.caption or '')[:500]}

Write ONLY the script text. Nothing else."""

        try:
            script = self.call_claude(prompt, max_tokens=300).strip()
            # Enforce character limit
            if len(script) > MAX_SCRIPT_LENGTH:
                script = script[:MAX_SCRIPT_LENGTH].rsplit(" ", 1)[0]
            return script
        except Exception as e:
            self.log(f"Script generation failed: {e}")
            return None

    def _submit_video(self, creator_name: str, script: str) -> str | None:
        """Submit a video generation request to the Captions AI Creator API."""
        try:
            resp = requests.post(
                f"{CAPTIONS_API_BASE}/submit",
                headers={
                    "x-api-key": CAPTIONS_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "creatorName": creator_name,
                    "script": script,
                },
                timeout=30,
            )

            if resp.status_code == 200:
                data = resp.json()
                op_id = data.get("operationId") or data.get("id") or data.get("jobId")
                if op_id:
                    return op_id
                self.log(f"Submit response missing operationId: {data}")
                return None
            else:
                self.log(f"Submit failed ({resp.status_code}): {resp.text[:300]}")
                return None
        except Exception as e:
            self.log(f"Submit request failed: {e}")
            return None

    def _poll_video(self, operation_id: str) -> str | None:
        """Poll the Captions API until the video is ready or fails."""
        for attempt in range(POLL_MAX_ATTEMPTS):
            try:
                resp = requests.post(
                    f"{CAPTIONS_API_BASE}/poll",
                    headers={
                        "x-api-key": CAPTIONS_API_KEY,
                        "Content-Type": "application/json",
                    },
                    json={"operationId": operation_id},
                    timeout=30,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    # When complete, response contains {"url": "..."}
                    video_url = data.get("url")
                    if video_url:
                        self.log(f"Video ready: {video_url[:80]}...")
                        return video_url
                    # Still processing — check for status field
                    status = data.get("status", "processing")
                    if status in ("failed", "error", "cancelled"):
                        self.log(f"Video generation failed: {data}")
                        return None
                    self.log(f"Poll attempt {attempt+1}/{POLL_MAX_ATTEMPTS}: {status}")
                elif resp.status_code == 202:
                    # Still processing
                    self.log(f"Poll attempt {attempt+1}/{POLL_MAX_ATTEMPTS}: processing...")
                else:
                    self.log(f"Poll error ({resp.status_code}): {resp.text[:200]}")

            except Exception as e:
                self.log(f"Poll request failed: {e}")

            time.sleep(POLL_INTERVAL)

        self.log(f"Video generation timed out after {POLL_MAX_ATTEMPTS * POLL_INTERVAL}s")
        return None
