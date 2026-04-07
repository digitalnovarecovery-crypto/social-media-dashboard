"""Agent 6: Performance Analyst — Weekly metrics collection + call tracking.

Schedule: Mondays at 9am
Reads: platform APIs for engagement data, call tracking for conversions
Produces: metrics records in DB + KPI progress toward 60 calls/month
"""
from __future__ import annotations

from datetime import datetime, timedelta

import requests

from agents.base_agent import BaseAgent
from config import BRANDS
from db.models import CallRecord, Metric, OAuthToken, Post, get_db


class PerformanceAnalyst(BaseAgent):
    name = "performance_analyst"
    display_name = "Performance Analyst"

    MONTHLY_CALL_GOAL = 60
    TARGET_CONVERSION_RATE = 0.10  # 10%

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

        for platform in ["facebook", "instagram", "tiktok", "linkedin", "youtube"]:
            existing = (
                db.query(Metric)
                .filter_by(brand_id=brand_id, platform=platform, week_ending=week_ending)
                .first()
            )
            if existing:
                continue

            # Count published posts
            published = (
                db.query(Post)
                .filter_by(brand_id=brand_id, platform=platform, status="published")
                .filter(Post.published_time >= last_week)
                .count()
            )

            # Try to fetch real engagement data from platform API
            engagement = self._fetch_platform_metrics(db, brand_id, platform, last_week)

            # Count calls attributed to this platform/brand this week
            calls_this_week = (
                db.query(CallRecord)
                .filter_by(brand_id=brand_id, platform=platform)
                .filter(CallRecord.call_time >= last_week)
                .count()
            )
            qualified_calls = (
                db.query(CallRecord)
                .filter_by(brand_id=brand_id, platform=platform, qualified=True)
                .filter(CallRecord.call_time >= last_week)
                .count()
            )
            converted = (
                db.query(CallRecord)
                .filter_by(brand_id=brand_id, platform=platform, converted=True)
                .filter(CallRecord.call_time >= last_week)
                .count()
            )

            conversion_rate = (converted / qualified_calls * 100) if qualified_calls > 0 else 0.0

            db.add(Metric(
                brand_id=brand_id,
                platform=platform,
                week_ending=week_ending,
                posts_published=published,
                engagement_rate=engagement.get("engagement_rate", 0.0),
                reach=engagement.get("reach", 0),
                impressions=engagement.get("impressions", 0),
                followers=engagement.get("followers", 0),
                calls_attributed=qualified_calls,
                total_calls=calls_this_week,
                conversion_rate=conversion_rate,
            ))
            count += 1
            self.log(
                f"{platform}/{brand_id}: {published} posts, "
                f"reach={engagement.get('reach', 0)}, "
                f"calls={calls_this_week} (qualified={qualified_calls})"
            )

        db.commit()
        db.close()
        return count

    def _fetch_platform_metrics(self, db, brand_id: str, platform: str, since: datetime) -> dict:
        """Try to fetch real metrics from platform APIs."""
        token = (
            db.query(OAuthToken)
            .filter_by(brand_id=brand_id, platform=platform)
            .first()
        )

        if not token or not token.access_token:
            return {}

        try:
            if platform == "facebook":
                return self._fetch_facebook_metrics(token, since)
            elif platform == "instagram":
                return self._fetch_instagram_metrics(token, since)
        except Exception as e:
            self.log(f"Failed to fetch {platform} metrics for {brand_id}: {e}")

        return {}

    def _fetch_facebook_metrics(self, token: OAuthToken, since: datetime) -> dict:
        """Fetch Facebook page insights."""
        url = f"https://graph.facebook.com/v19.0/{token.page_id}/insights"
        params = {
            "metric": "page_impressions,page_engaged_users,page_fans",
            "period": "week",
            "access_token": token.access_token,
        }
        resp = requests.get(url, params=params, timeout=30)
        if not resp.ok:
            return {}

        data = resp.json().get("data", [])
        metrics = {}
        for item in data:
            name = item.get("name")
            values = item.get("values", [])
            if values:
                val = values[-1].get("value", 0)
                if name == "page_impressions":
                    metrics["impressions"] = val
                    metrics["reach"] = val  # approx
                elif name == "page_engaged_users":
                    metrics["engagement_rate"] = val
                elif name == "page_fans":
                    metrics["followers"] = val
        return metrics

    def _fetch_instagram_metrics(self, token: OAuthToken, since: datetime) -> dict:
        """Fetch Instagram business account insights."""
        url = f"https://graph.facebook.com/v19.0/{token.page_id}/insights"
        params = {
            "metric": "impressions,reach,follower_count",
            "period": "day",
            "since": int(since.timestamp()),
            "access_token": token.access_token,
        }
        resp = requests.get(url, params=params, timeout=30)
        if not resp.ok:
            return {}

        data = resp.json().get("data", [])
        metrics = {}
        for item in data:
            name = item.get("name")
            values = item.get("values", [])
            total = sum(v.get("value", 0) for v in values)
            if name == "impressions":
                metrics["impressions"] = total
            elif name == "reach":
                metrics["reach"] = total
            elif name == "follower_count":
                metrics["followers"] = values[-1].get("value", 0) if values else 0
        return metrics
