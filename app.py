"""Social Media Team Dashboard — 6 Autonomous AI Agents
Run: python app.py -> http://localhost:5001
"""
from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from flask_cors import CORS
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import BRANDS, AGENT_SCHEDULES, FLASK_SECRET, FLASK_DEBUG, PORT
from db.models import (
    AgentRun, Brand, CallRecord, CalendarEntry, Metric, OAuthToken, Post,
    get_db, init_db,
)
from agents import ALL_AGENTS, AGENT_DISPLAY

# -- App setup ----------------------------------------------------------------
app = Flask(__name__)
app.secret_key = FLASK_SECRET
CORS(app)

# -- Scheduler ----------------------------------------------------------------
scheduler = BackgroundScheduler(daemon=True)


def run_agent_job(agent_key: str, brand_id: str | None = None):
    """Run an agent in a background thread."""
    agent_cls = ALL_AGENTS.get(agent_key)
    if not agent_cls:
        return
    agent = agent_cls(brand_id=brand_id)
    agent.execute()


def setup_scheduler():
    """Register all agent schedules."""
    # Token Manager: daily at 5am (before other agents)
    scheduler.add_job(
        run_agent_job, "cron",
        args=["token_manager"],
        hour=5, minute=0,
        id="token_manager", replace_existing=True,
    )
    # Content Strategist: 1st of month
    scheduler.add_job(
        run_agent_job, "cron",
        args=["content_strategist"],
        day=1, hour=6, minute=0,
        id="content_strategist", replace_existing=True,
    )
    # Caption Writer: daily
    scheduler.add_job(
        run_agent_job, "cron",
        args=["caption_writer"],
        hour=6, minute=0,
        id="caption_writer", replace_existing=True,
    )
    # Creative Director: daily
    scheduler.add_job(
        run_agent_job, "cron",
        args=["creative_director"],
        hour=7, minute=0,
        id="creative_director", replace_existing=True,
    )
    # Brand Reviewer: daily
    scheduler.add_job(
        run_agent_job, "cron",
        args=["brand_reviewer"],
        hour=8, minute=0,
        id="brand_reviewer", replace_existing=True,
    )
    # Publisher: every 15 minutes
    scheduler.add_job(
        run_agent_job, "cron",
        args=["publisher"],
        minute="*/15",
        id="publisher", replace_existing=True,
    )
    # Performance Analyst: Mondays 9am
    scheduler.add_job(
        run_agent_job, "cron",
        args=["performance_analyst"],
        day_of_week="mon", hour=9, minute=0,
        id="performance_analyst", replace_existing=True,
    )
    scheduler.start()


# -- Helpers ------------------------------------------------------------------

def current_brand_id() -> str:
    return session.get("brand_id", "nova")


def current_brand() -> dict:
    bid = current_brand_id()
    return {**BRANDS.get(bid, BRANDS["nova"]), "id": bid}


@app.context_processor
def inject_globals():
    brand = current_brand()
    return {
        "brand": brand,
        "brand_id": brand["id"],
        "brand_name": brand["name"],
        "brand_color": brand["color"],
        "accent_color": brand["accent"],
        "all_brands": BRANDS,
        "now": datetime.now(),
    }


# -- Routes: Navigation ------------------------------------------------------

@app.route("/switch-brand/<brand_id>")
def switch_brand(brand_id):
    if brand_id in BRANDS:
        session["brand_id"] = brand_id
    return redirect(request.referrer or url_for("dashboard"))


# -- Routes: Dashboard --------------------------------------------------------

@app.route("/")
def dashboard():
    db = get_db()
    bid = current_brand_id()
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    posts_week = db.query(Post).filter(
        Post.brand_id == bid,
        Post.created_at >= week_ago,
    ).count()

    posts_queued = db.query(Post).filter(
        Post.brand_id == bid,
        Post.status.in_(["draft", "approved"]),
    ).count()

    posts_published = db.query(Post).filter(
        Post.brand_id == bid,
        Post.status == "published",
    ).count()

    upcoming = (
        db.query(Post)
        .filter(Post.brand_id == bid, Post.status.in_(["approved", "scheduled"]))
        .order_by(Post.scheduled_time)
        .limit(10)
        .all()
    )

    agent_statuses = {}
    for agent_key in ALL_AGENTS:
        last_run = (
            db.query(AgentRun)
            .filter_by(agent_name=agent_key)
            .order_by(AgentRun.started_at.desc())
            .first()
        )
        agent_statuses[agent_key] = {
            "info": AGENT_DISPLAY[agent_key],
            "last_run": last_run,
            "status": last_run.status if last_run else "never_run",
        }

    # Per-platform counts
    platform_counts = {}
    for platform in ["facebook", "instagram", "tiktok", "linkedin"]:
        platform_counts[platform] = {
            "published": db.query(Post).filter_by(
                brand_id=bid, platform=platform, status="published"
            ).count(),
            "queued": db.query(Post).filter_by(
                brand_id=bid, platform=platform,
            ).filter(Post.status.in_(["draft", "approved"])).count(),
        }

    db.close()

    return render_template(
        "dashboard.html",
        posts_week=posts_week,
        posts_queued=posts_queued,
        posts_published=posts_published,
        upcoming=upcoming,
        agent_statuses=agent_statuses,
        platform_counts=platform_counts,
    )


# -- Routes: Agents -----------------------------------------------------------

@app.route("/agents")
def agents_page():
    db = get_db()
    agent_data = []

    for agent_key, info in AGENT_DISPLAY.items():
        runs = (
            db.query(AgentRun)
            .filter_by(agent_name=agent_key)
            .order_by(AgentRun.started_at.desc())
            .limit(10)
            .all()
        )
        next_run = None
        job = scheduler.get_job(agent_key)
        if job:
            next_run = job.next_run_time

        agent_data.append({
            "key": agent_key,
            "info": info,
            "runs": runs,
            "next_run": next_run,
            "last_status": runs[0].status if runs else "never_run",
        })

    db.close()
    return render_template("agents.html", agents=agent_data)


@app.route("/agents/<agent_key>/run", methods=["POST"])
def run_agent(agent_key):
    if agent_key not in ALL_AGENTS:
        flash(f"Unknown agent: {agent_key}", "error")
        return redirect(url_for("agents_page"))

    brand_id = request.form.get("brand_id") or current_brand_id()
    thread = threading.Thread(
        target=run_agent_job, args=[agent_key, brand_id], daemon=True
    )
    thread.start()
    flash(f"Agent '{AGENT_DISPLAY[agent_key]['name']}' started for {brand_id}", "success")
    return redirect(url_for("agents_page"))


# -- Routes: Calendar ---------------------------------------------------------

@app.route("/calendar")
def calendar_page():
    db = get_db()
    bid = current_brand_id()
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))

    entries = (
        db.query(CalendarEntry)
        .filter_by(brand_id=bid, month=month)
        .order_by(CalendarEntry.week, CalendarEntry.day)
        .all()
    )

    by_week = {}
    for entry in entries:
        week = entry.week
        if week not in by_week:
            by_week[week] = []
        by_week[week].append(entry)

    db.close()
    return render_template("calendar.html", entries=entries, by_week=by_week, month=month)


# -- Routes: Posts ------------------------------------------------------------

@app.route("/posts")
def posts_page():
    db = get_db()
    bid = current_brand_id()
    status_filter = request.args.get("status", "all")
    platform_filter = request.args.get("platform", "all")

    query = db.query(Post).filter_by(brand_id=bid)
    if status_filter != "all":
        query = query.filter_by(status=status_filter)
    if platform_filter != "all":
        query = query.filter_by(platform=platform_filter)

    posts = query.order_by(Post.scheduled_time.desc()).limit(100).all()
    db.close()

    return render_template(
        "posts.html", posts=posts,
        status_filter=status_filter, platform_filter=platform_filter,
    )


@app.route("/posts/<int:post_id>")
def post_detail(post_id):
    db = get_db()
    post = db.query(Post).get(post_id)
    db.close()
    if not post:
        flash("Post not found", "error")
        return redirect(url_for("posts_page"))
    return render_template("post_detail.html", post=post)


@app.route("/posts/<int:post_id>/approve", methods=["POST"])
def approve_post(post_id):
    db = get_db()
    post = db.query(Post).get(post_id)
    if post:
        post.status = "approved"
        post.review_notes = "Manually approved via dashboard"
        db.commit()
        flash(f"Post {post_id} approved", "success")
    db.close()
    return redirect(request.referrer or url_for("posts_page"))


@app.route("/posts/<int:post_id>/reject", methods=["POST"])
def reject_post(post_id):
    db = get_db()
    post = db.query(Post).get(post_id)
    if post:
        post.status = "needs_revision"
        post.review_notes = request.form.get("notes", "Rejected via dashboard")
        db.commit()
        flash(f"Post {post_id} rejected", "warning")
    db.close()
    return redirect(request.referrer or url_for("posts_page"))


@app.route("/posts/bulk-approve", methods=["POST"])
def bulk_approve():
    post_ids = request.form.getlist("post_ids")
    db = get_db()
    count = 0
    for pid in post_ids:
        post = db.query(Post).get(int(pid))
        if post and post.status in ("draft", "needs_revision"):
            post.status = "approved"
            count += 1
    db.commit()
    db.close()
    flash(f"{count} posts approved", "success")
    return redirect(url_for("posts_page"))


# -- Routes: Performance ------------------------------------------------------

@app.route("/performance")
def performance_page():
    db = get_db()
    bid = current_brand_id()

    metrics = (
        db.query(Metric)
        .filter_by(brand_id=bid)
        .order_by(Metric.week_ending.desc())
        .limit(20)
        .all()
    )

    # Aggregate by platform
    platform_summary = {}
    for m in metrics:
        if m.platform not in platform_summary:
            platform_summary[m.platform] = {
                "total_published": 0,
                "avg_engagement": 0,
                "total_reach": 0,
                "latest_followers": 0,
                "weeks": 0,
            }
        s = platform_summary[m.platform]
        s["total_published"] += m.posts_published
        s["total_reach"] += m.reach
        s["weeks"] += 1
        if m.followers > s["latest_followers"]:
            s["latest_followers"] = m.followers

    db.close()
    return render_template(
        "performance.html",
        metrics=metrics,
        platform_summary=platform_summary,
    )


# -- Routes: Settings ---------------------------------------------------------

@app.route("/settings")
def settings_page():
    db = get_db()
    brands = db.query(Brand).all()
    tokens = db.query(OAuthToken).all()
    db.close()
    return render_template("settings.html", brands=brands, tokens=tokens)


# -- API routes (for AJAX) ----------------------------------------------------

@app.route("/api/agent-status")
def api_agent_status():
    db = get_db()
    statuses = {}
    for agent_key in ALL_AGENTS:
        last_run = (
            db.query(AgentRun)
            .filter_by(agent_name=agent_key)
            .order_by(AgentRun.started_at.desc())
            .first()
        )
        statuses[agent_key] = {
            "status": last_run.status if last_run else "never_run",
            "last_run": last_run.started_at.isoformat() if last_run and last_run.started_at else None,
        }
    db.close()
    return jsonify(statuses)


@app.route("/api/posts/count")
def api_post_counts():
    db = get_db()
    bid = request.args.get("brand", current_brand_id())
        if bid not in BRANDS:
                    db.close()
                    return jsonify({"error": f"Unknown brand: {bid}"}), 400
    counts = {
                "brand": bid,
        "draft": db.query(Post).filter_by(brand_id=bid, status="draft").count(),
        "approved": db.query(Post).filter_by(brand_id=bid, status="approved").count(),
        "scheduled": db.query(Post).filter_by(brand_id=bid, status="scheduled").count(),
        "published": db.query(Post).filter_by(brand_id=bid, status="published").count(),
        "failed": db.query(Post).filter_by(brand_id=bid, status="failed").count(),
    }
    db.close()
    return jsonify(counts)


@app.route("/api/kpi")
def api_kpi():
    """Return monthly KPI progress — 60 calls/month, 10% conversion."""
    db = get_db()
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # All brands combined for the 60 calls/month goal
    total_calls = db.query(CallRecord).filter(CallRecord.call_time >= month_start).count()
    qualified = db.query(CallRecord).filter(
        CallRecord.call_time >= month_start, CallRecord.qualified == True
    ).count()
    converted = db.query(CallRecord).filter(
        CallRecord.call_time >= month_start, CallRecord.converted == True
    ).count()

    # Per-brand breakdown
    brands_kpi = {}
    for bid in BRANDS:
        brand_calls = db.query(CallRecord).filter(
            CallRecord.call_time >= month_start, CallRecord.brand_id == bid
        ).count()
        brand_qualified = db.query(CallRecord).filter(
            CallRecord.call_time >= month_start, CallRecord.brand_id == bid,
            CallRecord.qualified == True,
        ).count()
        brand_converted = db.query(CallRecord).filter(
            CallRecord.call_time >= month_start, CallRecord.brand_id == bid,
            CallRecord.converted == True,
        ).count()
        brands_kpi[bid] = {
            "calls": brand_calls,
            "qualified": brand_qualified,
            "converted": brand_converted,
            "conversion_rate": (brand_converted / brand_qualified * 100) if brand_qualified > 0 else 0,
        }

    db.close()
    return jsonify({
        "month": now.strftime("%B %Y"),
        "goal_calls": 60,
        "goal_conversion": 10.0,
        "total_calls": total_calls,
        "qualified_calls": qualified,
        "converted": converted,
        "conversion_rate": (converted / qualified * 100) if qualified > 0 else 0,
        "progress_pct": min(100, int(qualified / 60 * 100)),
        "brands": brands_kpi,
    })


@app.route("/api/tokens/update", methods=["POST"])
def api_update_token():
    """Update an OAuth token from the dashboard settings page."""
    data = request.get_json()
    brand_id = data.get("brand_id")
    platform = data.get("platform")
    access_token = data.get("access_token")
    page_id = data.get("page_id")

    if not brand_id or not platform:
        return jsonify({"error": "brand_id and platform required"}), 400

    db = get_db()
    token = db.query(OAuthToken).filter_by(brand_id=brand_id, platform=platform).first()
    if not token:
        db.close()
        return jsonify({"error": "Token not found"}), 404

    if access_token:
        token.access_token = access_token
    if page_id:
        token.page_id = page_id
    token.expires_at = datetime.utcnow() + timedelta(days=60)

    db.commit()
    db.close()
    return jsonify({"status": "updated", "brand_id": brand_id, "platform": platform})


# -- Template Filters ---------------------------------------------------------

@app.template_filter("format_dt")
def format_dt(value):
    if isinstance(value, datetime):
        return value.strftime("%b %d, %H:%M")
    return str(value) if value else "—"


@app.template_filter("status_color")
def status_color(status):
    colors = {
        "draft": "gray",
        "approved": "blue",
        "scheduled": "amber",
        "published": "green",
        "failed": "red",
        "needs_revision": "orange",
        "running": "blue",
        "completed": "green",
        "never_run": "gray",
    }
    return colors.get(status, "gray")


# -- Startup (runs for both gunicorn and direct execution) -------------------

def startup():
    """Initialize DB, seed, and start scheduler."""
    init_db()
    db = get_db()
    if db.query(Brand).count() == 0:
        db.close()
        from db.seed import seed
        seed()
    else:
        db.close()
    setup_scheduler()
    print(f"\n  Social Media Team Dashboard — 6 agents scheduled and running\n")


# Run startup on import (for gunicorn) — but only once
import os
if os.environ.get("WERKZEUG_RUN_MAIN") != "true" or not FLASK_DEBUG:
    startup()


# -- Main (local dev) --------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", PORT))
    app.run(host="0.0.0.0", port=port, debug=FLASK_DEBUG)
