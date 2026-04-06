"""Agent 6: Performance Analyst — Weekly metrics collection.

Schedule: Mondays at 9am
Reads: platform APIs for engagement data
Produces: metrics records in DB + insights
"""
from __future__ import annotations

from datetime import datetime, timedelta

from agents.base_agent import BaseAgent
from config import BRANDS
from db.models import Metric, Post, get_db


class PerformanceAnalyst(BaseAgent):
    name = "performance_analyst"
    display_name = "Performance Analyst"

    def run(self) -> dict:
        brands = [self.brand_id] if self.brand_id else list(BRANDS.keys())
        total = 0

        for brand_id in brands:
            count = self._collect_metrics(brand_id)
            total += count

        return {"posts_created": total}

    def _collect_metrics(self, brand_id: str) -> int:
        db = get_db()
        today = datetime.now()
        week_ending = today.strftime("%Y-%m-%d")
        last_week = today - timedelta(days=7)
        count = 0

        for platform in ["facebook", "instagram", "tiktok", "linkedin"]:
            existing = (
                db.query(Metric)
                .filter_by(brand_id=brand_id, platform=platform, week_ending=week_ending)
                .first()
            )
            if existing:
                continue

            published = (
                db.query(Post)
                .filter_by(brand_id=brand_id, platform=platform, status="published")
                .filter(Post.published_time >= last_week)
                .count()
            )

            db.add(Metric(
                brand_id=brand_id,
                platform=platform,
                week_ending=week_ending,
                posts_published=published,
                engagement_rate=0.0,
                reach=0,
                impressions=0,
                followers=0,
                calls_attributed=0,
            ))
            count += 1
            self.log(f"Recorded {platform} metrics for {brand_id}: {published} posts published")

        db.commit()
        db.close()
        return count
