"""Agent 1: Content Strategist — Monthly calendar generation.

Schedule: 1st of each month at 6am
Reads: brand-style.md + last month's performance metrics
Produces: calendar_entries in DB for the entire month
"""
from __future__ import annotations

from datetime import datetime, timedelta
import calendar as cal_mod
import json

import anthropic

from agents.base_agent import BaseAgent
from config import BRANDS, ANTHROPIC_API_KEY
from db.models import CalendarEntry, Metric, get_db


class ContentStrategist(BaseAgent):
    name = "content_strategist"
    display_name = "Content Strategist"

    def run(self) -> dict:
        brands = [self.brand_id] if self.brand_id else list(BRANDS.keys())
        total_created = 0

        for brand_id in brands:
            self.log(f"Generating content calendar for {brand_id}")
            count = self._generate_calendar(brand_id)
            total_created += count
            self.log(f"Created {count} calendar entries for {brand_id}")

        return {"posts_created": total_created}

    def _generate_calendar(self, brand_id: str) -> int:
        brand_context = self.load_brand_context(brand_id)
        if not brand_context:
            self.log(f"No brand-style.md found for {brand_id}, skipping")
            return 0

        now = datetime.now()
        target_month = now.replace(day=1) + timedelta(days=32)
        target_month = target_month.replace(day=1)
        month_str = target_month.strftime("%Y-%m")
        month_name = target_month.strftime("%B %Y")

        db = get_db()

        existing = db.query(CalendarEntry).filter_by(
            brand_id=brand_id, month=month_str
        ).count()
        if existing > 0:
            self.log(f"Calendar already exists for {brand_id} {month_str} ({existing} entries)")
            db.close()
            return 0

        last_month_metrics = self._get_last_month_metrics(db, brand_id)

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = self._build_prompt(brand_context, month_name, last_month_metrics, brand_id)

        self.log(f"Calling Claude API for {month_name} calendar...")
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )

        calendar_json = self._parse_response(response.content[0].text)
        count = 0

        for entry in calendar_json:
            db.add(CalendarEntry(
                brand_id=brand_id,
                month=month_str,
                week=entry.get("week", 1),
                day=entry.get("day", "Mon"),
                platform=entry.get("platform", "instagram"),
                pillar=entry.get("pillar", ""),
                format=entry.get("format", "single_image"),
                topic=entry.get("topic", ""),
                angle=entry.get("angle", ""),
                visual_direction=entry.get("visual_direction", ""),
                awareness_level=entry.get("awareness_level", "mof"),
                persona_target=entry.get("persona_target", ""),
                objective=entry.get("objective", "engagement"),
                notes=entry.get("notes", ""),
            ))
            count += 1

        db.commit()
        db.close()
        return count

    def _get_last_month_metrics(self, db, brand_id: str) -> str:
        metrics = (
            db.query(Metric)
            .filter_by(brand_id=brand_id)
            .order_by(Metric.week_ending.desc())
            .limit(4)
            .all()
        )
        if not metrics:
            return "No previous performance data available."

        lines = ["Last month's performance:"]
        for m in metrics:
            lines.append(
                f"  {m.platform} (w/e {m.week_ending}): "
                f"engagement={m.engagement_rate}, reach={m.reach}, "
                f"followers={m.followers}"
            )
        return "\n".join(lines)

    def _build_prompt(self, brand_context: str, month_name: str, metrics: str, brand_id: str) -> str:
        phones = BRANDS[brand_id]["phones"]
        phone_info = "\n".join(f"  {p}: {n}" for p, n in phones.items())

        return f"""You are a Social Media Content Strategist for a treatment center.

Generate a content calendar for {month_name} across 4 platforms: Facebook, Instagram, TikTok, LinkedIn.
7 posts per week per platform (28 total per week, ~112 per month).

BRAND CONTEXT:
{brand_context[:4000]}

PLATFORM PHONE NUMBERS (use correct number per platform):
{phone_info}

PERFORMANCE DATA:
{metrics}

Return ONLY a JSON array of objects. Each object must have:
- week (1-4)
- day (Mon/Tue/Wed/Thu/Fri/Sat/Sun)
- platform (facebook/instagram/tiktok/linkedin)
- pillar (e.g., "persona_pain_points", "objection_handling", "service_cta", "recovery_education", "trust_proof", "family_loved_ones", "motivational", "community_events")
- format (single_image/carousel/reel/video/text_post/link_post/document)
- topic (specific, not vague)
- angle (the hook or POV)
- visual_direction (1 sentence for the designer)
- awareness_level (tof/mof/bof)
- persona_target (e.g., "M1_ethan", "F3_stephanie", "parents", "spouses", "all")
- objective (awareness/engagement/conversion)
- notes (any special context)

Content mix: 40% ToF, 40% MoF, 20% BoF.
Every post must have a CTA (soft for ToF, direct for BoF).
Return ONLY valid JSON — no markdown, no explanation."""

    def _parse_response(self, text: str) -> list[dict]:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
            self.log("Failed to parse calendar JSON from Claude response")
            return []
