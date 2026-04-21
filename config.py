"""Application configuration — cloud-ready."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

# Database: PostgreSQL in production, SQLite fallback for local dev
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    DB_PATH = PROJECT_ROOT / "db" / "social_media.db"
    DATABASE_URL = f"sqlite:///{DB_PATH}"
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

CONTEXT_ROOT = PROJECT_ROOT.parent  # local dev only
BRAND_DATA_DIR = PROJECT_ROOT / "brand_data"  # in-repo brand context (for cloud)

FLASK_SECRET = os.getenv("FLASK_SECRET", "dev-secret-change-in-production")
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
PORT = int(os.getenv("PORT", "5001"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Canva API (kept for future template-based generation)
CANVA_API_TOKEN = os.getenv("CANVA_API_TOKEN", "")
CANVA_BRAND_KIT_ID = os.getenv("CANVA_BRAND_KIT_ID", "")

# Public URL for serving generated images
PUBLIC_URL = os.getenv(
    "PUBLIC_URL",
    os.getenv(
        "RAILWAY_PUBLIC_DOMAIN",
        "social-media-dashboard-production-a19f.up.railway.app",
    ),
)

# Brand configurations
BRANDS = {
    "nova": {
        "name": "Nova Recovery Center",
        "short": "NOVA",
        "color": "#1d2a3b",
        "accent": "#efc732",
        "context_dir": CONTEXT_ROOT / "nova-recovery-center" / "context",
        "context_dir_fallback": BRAND_DATA_DIR / "nova",
        "phones": {
            "facebook": "(737) 345-0811",
            "instagram": "(512) 387-9914",
            "youtube": "(737) 234-7547",
            "tiktok": "(737) 387-4734",
            "linkedin": "(737) 367-2432",
        },
    },
    "briarwood": {
        "name": "Briarwood Detox Center",
        "short": "BWD",
        "color": "#1b1814",
        "accent": "#f6ea2c",
        "context_dir": CONTEXT_ROOT / "briarwood-detox-center" / "context",
        "context_dir_fallback": BRAND_DATA_DIR / "briarwood",
        "phones": {
            "facebook": "(512) 641-5513",
            "instagram": "(737) 317-4390",
            "youtube": "(737) 747-7217",
            "tiktok": "(737) 214-8257",
            "linkedin": "(737) 264-6109",
        },
    },
    "eudaimonia": {
        "name": "Eudaimonia Recovery Homes",
        "short": "ERH",
        "color": "#2d6a2e",
        "accent": "#fee21d",
        "context_dir": CONTEXT_ROOT / "eudaimonia-sober-living" / "context",
        "context_dir_fallback": BRAND_DATA_DIR / "eudaimonia",
        "phones": {
            "facebook": "(512) 985-2139",
            "instagram": "(737) 378-8653",
            "youtube": "(737) 427-3277",
            "tiktok": "(737) 427-3962",
            "linkedin": "(737) 530-4256",
        },
    },
}

# Agent schedules (cron-style)
AGENT_SCHEDULES = {
    "content_strategist": {"day": 1, "hour": 6, "minute": 0},   # 1st of month at 6am
    "caption_writer": {"hour": 6, "minute": 0},                  # Daily 6am
    "creative_director": {"hour": 7, "minute": 0},               # Daily 7am
    "brand_reviewer": {"hour": 8, "minute": 0},                  # Daily 8am
    "publisher": {"minute": "*/15"},                              # Every 15 min (checks queue)
    "performance_analyst": {"day_of_week": "mon", "hour": 9},    # Mondays 9am
}
