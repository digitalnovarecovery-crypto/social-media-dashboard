from agents.base_agent import BaseAgent
from agents.content_strategist import ContentStrategist
from agents.caption_writer import CaptionWriter
from agents.creative_director import CreativeDirector
from agents.brand_reviewer import BrandReviewer
from agents.publisher import Publisher
from agents.performance_analyst import PerformanceAnalyst

ALL_AGENTS = {
    "content_strategist": ContentStrategist,
    "caption_writer": CaptionWriter,
    "creative_director": CreativeDirector,
    "brand_reviewer": BrandReviewer,
    "publisher": Publisher,
    "performance_analyst": PerformanceAnalyst,
}

AGENT_DISPLAY = {
    "content_strategist": {"name": "Content Strategist", "icon": "📅", "desc": "Monthly calendar generation"},
    "caption_writer": {"name": "Caption Writer", "icon": "✍️", "desc": "Daily caption writing"},
    "creative_director": {"name": "Creative Director", "icon": "🎨", "desc": "Visual direction + image prompts"},
    "brand_reviewer": {"name": "Brand Reviewer", "icon": "✅", "desc": "QA before publish"},
    "publisher": {"name": "Publisher", "icon": "📤", "desc": "API publishing to platforms"},
    "performance_analyst": {"name": "Performance Analyst", "icon": "📊", "desc": "Weekly metrics + insights"},
}
