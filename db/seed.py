"""Seed the database with brand data, context, and OAuth tokens from env vars."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BRANDS
from db.models import Brand, OAuthToken, init_db, get_db
from sqlalchemy.exc import IntegrityError

# Map brand_id to env var names for all platform tokens
TOKEN_MAP = {
    "nova": {
        "facebook": {"page_id": "NOVA_FB_PAGE_ID", "token": "NOVA_FB_ACCESS_TOKEN"},
        "instagram": {"page_id": "NOVA_IG_BUSINESS_ID", "token": "NOVA_IG_ACCESS_TOKEN"},
        "tiktok": {"page_id": "", "token": "NOVA_TT_ACCESS_TOKEN"},
        "linkedin": {"page_id": "NOVA_LI_ORG_ID", "token": "NOVA_LI_ACCESS_TOKEN"},
        "youtube": {"page_id": "NOVA_YT_CHANNEL_ID", "token": "NOVA_YT_ACCESS_TOKEN"},
    },
    "briarwood": {
        "facebook": {"page_id": "BWD_FB_PAGE_ID", "token": "BWD_FB_ACCESS_TOKEN"},
        "instagram": {"page_id": "BWD_IG_BUSINESS_ID", "token": "BWD_IG_ACCESS_TOKEN"},
        "tiktok": {"page_id": "", "token": "BWD_TT_ACCESS_TOKEN"},
        "linkedin": {"page_id": "BWD_LI_ORG_ID", "token": "BWD_LI_ACCESS_TOKEN"},
        "youtube": {"page_id": "BWD_YT_CHANNEL_ID", "token": "BWD_YT_ACCESS_TOKEN"},
    },
    "eudaimonia": {
        "facebook": {"page_id": "ERH_FB_PAGE_ID", "token": "ERH_FB_ACCESS_TOKEN"},
        "instagram": {"page_id": "ERH_IG_BUSINESS_ID", "token": "ERH_IG_ACCESS_TOKEN"},
        "tiktok": {"page_id": "", "token": "ERH_TT_ACCESS_TOKEN"},
        "linkedin": {"page_id": "ERH_LI_ORG_ID", "token": "ERH_LI_ACCESS_TOKEN"},
        "youtube": {"page_id": "ERH_YT_CHANNEL_ID", "token": "ERH_YT_ACCESS_TOKEN"},
    },
}


def _load_brand_context(brand_id: str) -> str:
    """Load brand context from local files or in-repo fallback."""
    info = BRANDS.get(brand_id)
    if not info:
        return ""

    # Try primary context_dir first (local dev), then fallback (in-repo for cloud)
    dirs_to_try = []
    if info.get("context_dir"):
        dirs_to_try.append(Path(info["context_dir"]))
    if info.get("context_dir_fallback"):
        dirs_to_try.append(Path(info["context_dir_fallback"]))

    context_parts = []
    for context_dir in dirs_to_try:
        if not context_dir.exists():
            continue
        for filename in ["brand-style.md", "social-strategy.md", "content-calendar.md"]:
            filepath = context_dir / filename
            if filepath.exists():
                content = filepath.read_text(encoding="utf-8")
                context_parts.append(f"# {filename}\n\n{content}")
        if context_parts:
            break  # Found files in this directory, don't check fallback

    return "\n\n---\n\n".join(context_parts)


def seed():
    init_db()
    db = get_db()

    for brand_id, info in BRANDS.items():
        existing = db.query(Brand).filter_by(id=brand_id).first()
        brand_context = _load_brand_context(brand_id)

        if not existing:
            db.add(Brand(
                id=brand_id,
                name=info["name"],
                short_name=info["short"],
                brand_color=info["color"],
                accent_color=info["accent"],
                context_path=str(info.get("context_dir", "")),
                active=True,
                brand_context=brand_context,
            ))
        else:
            # Update brand context if we have new local files
            if brand_context and (not existing.brand_context or len(brand_context) > len(existing.brand_context or "")):
                existing.brand_context = brand_context

        # Create/update OAuth tokens for ALL platforms
        for platform, phone in info["phones"].items():
            existing_token = (
                db.query(OAuthToken)
                .filter_by(brand_id=brand_id, platform=platform)
                .first()
            )

            # Get env var values for this brand/platform
            env_vars = TOKEN_MAP.get(brand_id, {}).get(platform, {})
            page_id = os.getenv(env_vars.get("page_id", ""), "") if env_vars.get("page_id") else ""
            access_token = os.getenv(env_vars.get("token", ""), "") if env_vars.get("token") else ""

            if not existing_token:
                db.add(OAuthToken(
                    brand_id=brand_id,
                    platform=platform,
                    tracking_phone=phone,
                    page_id=page_id,
                    access_token=access_token,
                ))
            else:
                # Always update tokens from env vars (overwrite stale values)
                if page_id:
                    existing_token.page_id = page_id
                if access_token:
                    existing_token.access_token = access_token
                if phone:
                    existing_token.tracking_phone = phone

    try:
        db.commit()
    except IntegrityError:
        # Another worker raced ahead and seeded first — safe to ignore.
        db.rollback()
    db.close()
    print("Database seeded with 3 brands, brand context, and platform configs.")


if __name__ == "__main__":
    seed()
