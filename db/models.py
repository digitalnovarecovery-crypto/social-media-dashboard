"""SQLAlchemy models for the Social Media Dashboard."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DB_PATH


class Base(DeclarativeBase):
    pass


class Brand(Base):
    __tablename__ = "brands"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    short_name = Column(String)
    brand_color = Column(String)
    accent_color = Column(String)
    context_path = Column(String)
    active = Column(Boolean, default=True)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    access_token = Column(Text)
    refresh_token = Column(Text)
    expires_at = Column(DateTime)
    page_id = Column(String)
    tracking_phone = Column(String)


class CalendarEntry(Base):
    __tablename__ = "calendar_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(String, nullable=False)
    month = Column(String)
    week = Column(Integer)
    day = Column(String)
    platform = Column(String)
    pillar = Column(String)
    format = Column(String)
    topic = Column(Text)
    angle = Column(Text)
    visual_direction = Column(Text)
    awareness_level = Column(String)
    persona_target = Column(String)
    objective = Column(String)
    notes = Column(Text)


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    calendar_entry_id = Column(Integer)
    brand_id = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    status = Column(String, default="draft")
    caption = Column(Text)
    hashtags = Column(Text)
    image_url = Column(String)
    image_prompt = Column(Text)
    scheduled_time = Column(DateTime)
    published_time = Column(DateTime)
    platform_post_id = Column(String)
    review_notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_name = Column(String, nullable=False)
    brand_id = Column(String)
    status = Column(String, default="pending")
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    posts_created = Column(Integer, default=0)
    posts_published = Column(Integer, default=0)
    error_message = Column(Text)
    log = Column(Text)


class Metric(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    week_ending = Column(String)
    posts_published = Column(Integer, default=0)
    engagement_rate = Column(Float, default=0.0)
    reach = Column(Integer, default=0)
    impressions = Column(Integer, default=0)
    followers = Column(Integer, default=0)
    calls_attributed = Column(Integer, default=0)
    best_post_id = Column(String)


# Engine & session factory
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Create all tables."""
    Base.metadata.create_all(engine)


def get_db() -> Session:
    """Get a database session."""
    return SessionLocal()
