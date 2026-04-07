"""Agent 2: Caption Writer — Daily caption generation.

Schedule: Daily at 6am
Reads: today's calendar entries from DB + brand-style.md
Produces: Post records with captions in DB (status=draft)
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json

from agents.base_agent import BaseAgent
from config import BRANDS
from db.models import CalendarEntry, Post, get_db


class CaptionWriter(BaseAgent):
    name = "caption_writer"
    display_name = "Caption Writer"

    def run(self) -> dict:
        brands = [self.brand_id] if self.brand_id else list(BRANDS.keys())
        total = 0

        for brand_id in brands:
            count = self._write_captions(brand_id)
            total += count

        return {"posts_created": total}

    def _write_captions(self, brand_id: str) -> int:
        db = get_db()
        today = datetime.now()
        day_name = today.strftime("%a")
        month_str = today.strftime("%Y-%m")

        # Try current month first, then next month if nothing found
        entries = (
            db.query(CalendarEntry)
            .filter_by(brand_id=brand_id, month=month_str, day=day_name)
            .all()
        )

        if not entries:
            # Check next month's entries for today's day name
            next_month = (today.replace(day=1) + timedelta(days=32)).strftime("%Y-%m")
            entries = (
                db.query(CalendarEntry)
                .filter_by(brand_id=brand_id, month=next_month, day=day_name)
                .all()
            )
            if entries:
                self.log(f"Using next month ({next_month}) entries for {brand_id}")

        if not entries:
            # Fallback: grab any unwritten entries (up to 5 per platform)
            written_ids = {p.calendar_entry_id for p in db.query(Post).filter_by(brand_id=brand_id).all()}
            entries = [
                e for e in db.query(CalendarEntry).filter_by(brand_id=brand_id).all()
                if e.id not in written_ids
            ][:25]  # Cap at 25 entries per run
            if entries:
                self.log(f"Using {len(entries)} unwritten entries for {brand_id}")

        if not entries:
            self.log(f"No calendar entries for {brand_id} on {day_name}")
            db.close()
            return 0

        already_written = {
            p.calendar_entry_id
            for p in db.query(Post).filter(
                Post.brand_id == brand_id,
                Post.calendar_entry_id.in_([e.id for e in entries]),
            ).all()
        }

        to_write = [e for e in entries if e.id not in already_written]
        if not to_write:
            self.log(f"All captions already written for {brand_id} on {day_name}")
            db.close()
            return 0

        self.log(f"Writing {len(to_write)} captions for {brand_id}")
        brand_context = self.load_brand_context(brand_id)
        phones = BRANDS[brand_id]["phones"]

        count = 0

        for entry in to_write:
            phone = phones.get(entry.platform, phones.get("instagram", ""))
            caption = self._generate_caption(brand_context, entry, phone)

            if caption:
                scheduled = self._calculate_schedule_time(today, entry)
                db.add(Post(
                    calendar_entry_id=entry.id,
                    brand_id=brand_id,
                    platform=entry.platform,
                    status="draft",
                    caption=caption.get("caption", ""),
                    hashtags=caption.get("hashtags", ""),
                    image_prompt=entry.visual_direction,
                    scheduled_time=scheduled,
                ))
                count += 1

        db.commit()
        db.close()
        self.log(f"Created {count} draft posts for {brand_id}")
        return count

    def _generate_caption(self, brand_context: str, entry: CalendarEntry, phone: str) -> dict | None:
        prompt = f"""Write a social media caption for this post:

Platform: {entry.platform}
Topic: {entry.topic}
Angle: {entry.angle}
Pillar: {entry.pillar}
Format: {entry.format}
Awareness Level: {entry.awareness_level}
Target Persona: {entry.persona_target}
Phone Number for CTA: {phone}

BRAND CONTEXT (excerpt):
{brand_context[:2000]}

Return JSON with:
- caption: the full caption text (platform-native length and style)
- hashtags: 3-6 relevant hashtags as a string

The caption MUST:
1. Start with a scroll-stopping hook
2. Include a CTA with the phone number {phone}
3. Mention specific services (detox, inpatient rehab, IOP, sober living)
4. Match the brand's tone: warm, direct, non-judgmental
5. Be appropriate for {entry.platform}

Return ONLY valid JSON."""

        try:
            text = self.call_claude(prompt, max_tokens=1000)
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
            return json.loads(text)
        except Exception as e:
            self.log(f"Caption generation failed: {e}")
            return None

    def _calculate_schedule_time(self, today: datetime, entry: CalendarEntry) -> datetime:
        platform_times = {
            "facebook": 10,
            "instagram": 12,
            "tiktok": 18,
            "linkedin": 8,
        }
        hour = platform_times.get(entry.platform, 12)
        return today.replace(hour=hour, minute=0, second=0, microsecond=0)
