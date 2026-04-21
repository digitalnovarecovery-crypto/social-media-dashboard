from agents.base_agent import BaseAgent
from agents.content_strategist import ContentStrategist
from agents.caption_writer import CaptionWriter
from agents.creative_director import CreativeDirector
from agents.brand_reviewer import BrandReviewer
from agents.publisher import Publisher
from agents.performance_analyst import PerformanceAnalyst
from agents.token_manager import TokenManager
from agents.video_generator import VideoGenerator

ALL_AGENTS = {
    "token_manager": TokenManager,
    "content_strategist": ContentStrategist,
    "caption_writer": CaptionWriter,
    "creative_director": CreativeDirector,
    "video_generator": VideoGenerator,
    "brand_reviewer": BrandReviewer,
    "publisher": Publisher,
    "performance_analyst": PerformanceAnalyst,
}

AGENT_DISPLAY = {
    "token_manager": {"name": "Token Manager", "icon": "🔑", "desc": "Auto-refreshes expiring API tokens"},
    "content_strategist": {"name": "Content Strategist", "icon": "📅", "desc": "Monthly content calendar for all platforms"},
    "caption_writer": {"name": "Caption Writer", "icon": "✍️", "desc": "Daily captions, hooks, CTAs, and hashtags"},
    "creative_director": {"name": "Creative Director", "icon": "🎨", "desc": "Branded visuals via Canva API"},
    "video_generator": {"name": "Video Generator", "icon": "🎬", "desc": "AI Twin talking-head videos via Captions.ai"},
    "brand_reviewer": {"name": "Brand Reviewer", "icon": "✅", "desc": "QA review against brand guidelines"},
    "publisher": {"name": "Publisher", "icon": "📤", "desc": "Auto-publish to FB, IG, LI, TikTok"},
    "performance_analyst": {"name": "Performance Analyst", "icon": "📊", "desc": "Weekly metrics, call tracking, KPIs"},
}
