"""Seed the database with brand data from config."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BRANDS
from db.models import Brand, OAuthToken, init_db, get_db


def seed():
    init_db()
    db = get_db()

    for brand_id, info in BRANDS.items():
        existing = db.query(Brand).filter_by(id=brand_id).first()
        if not existing:
            db.add(Brand(
                id=brand_id,
                name=info["name"],
                short_name=info["short"],
                brand_color=info["color"],
                accent_color=info["accent"],
                context_path=str(info["context_dir"]),
                active=True,
            ))

        for platform, phone in info["phones"].items():
            existing_token = (
                db.query(OAuthToken)
                .filter_by(brand_id=brand_id, platform=platform)
                .first()
            )
            if not existing_token:
                db.add(OAuthToken(
                    brand_id=brand_id,
                    platform=platform,
                    tracking_phone=phone,
                ))

    db.commit()
    db.close()
    print("Database seeded with 3 brands and 15 platform configs.")


if __name__ == "__main__":
    seed()
