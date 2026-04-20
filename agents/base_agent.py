"""Base class for all Social Media Team agents."""
from __future__ import annotations

import time
import traceback
from datetime import datetime
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY
from db.models import AgentRun, Brand, get_db


class BaseAgent:
    """Base class providing logging, DB tracking, and brand context loading."""

    name: str = "base_agent"
    display_name: str = "Base Agent"

    def __init__(self, brand_id: str | None = None):
        self.brand_id = brand_id
        self._run_id: int | None = None
        self._log_lines: list[str] = []

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self._log_lines.append(line)
        print(f"[{self.name}] {line}")

    def load_brand_context(self, brand_id: str) -> str:
        """Load brand context — tries DB first (cloud), then local files (dev)."""
        from config import BRANDS

        # Try DB first (cloud deployment)
        db = get_db()
        brand = db.query(Brand).filter_by(id=brand_id).first()
        if brand and brand.brand_context:
            context = brand.brand_context
            db.close()
            return context
        db.close()

        # Fallback to local files (dev) or in-repo files (cloud)
        info = BRANDS.get(brand_id)
        if not info:
            return ""
        for dir_key in ("context_dir", "context_dir_fallback"):
            context_dir = info.get(dir_key)
            if context_dir:
                style_path = Path(context_dir) / "brand-style.md"
                if style_path.exists():
                    return style_path.read_text(encoding="utf-8")
        return ""

    def load_content_calendar(self, brand_id: str) -> str:
        """Read content-calendar.md for a given brand."""
        from config import BRANDS
        info = BRANDS.get(brand_id)
        if not info:
            return ""
        context_dir = info.get("context_dir")
        if context_dir:
            cal_path = Path(context_dir) / "content-calendar.md"
            if cal_path.exists():
                return cal_path.read_text(encoding="utf-8")
        return ""

    def call_claude(self, prompt: str, model: str = "claude-sonnet-4-20250514",
                    max_tokens: int = 4096, max_retries: int = 5) -> str:
        """Call Claude API with automatic retry + exponential backoff for rate limits."""
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        for attempt in range(max_retries):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text
            except anthropic.RateLimitError as e:
                wait = min(2 ** attempt * 30, 180)  # 30s, 60s, 120s, 180s, 180s
                self.log(f"Rate limited (attempt {attempt+1}/{max_retries}), waiting {wait}s...")
                time.sleep(wait)
            except anthropic.APIError as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt * 10
                    self.log(f"API error (attempt {attempt+1}): {e}, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        raise anthropic.RateLimitError(
            message="Max retries exceeded for rate limit",
            response=None, body=None
        )

    def _start_run(self):
        db = get_db()
        run = AgentRun(
            agent_name=self.name,
            brand_id=self.brand_id or "all",
            status="running",
            started_at=datetime.utcnow(),
        )
        db.add(run)
        db.commit()
        self._run_id = run.id
        db.close()
        self.log(f"Run started (id={self._run_id})")

    def _complete_run(self, posts_created=0, posts_published=0):
        db = get_db()
        run = db.query(AgentRun).get(self._run_id)
        if run:
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            run.posts_created = posts_created
            run.posts_published = posts_published
            run.log = "\n".join(self._log_lines)
            db.commit()
        db.close()
        self.log(f"Run completed (created={posts_created}, published={posts_published})")

    def _fail_run(self, error: str):
        db = get_db()
        run = db.query(AgentRun).get(self._run_id)
        if run:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
            run.error_message = error
            run.log = "\n".join(self._log_lines)
            db.commit()
        db.close()
        self.log(f"Run FAILED: {error}")

    def execute(self, brand_id: str | None = None):
        """Main entry point — wraps run() with logging and error handling."""
        self.brand_id = brand_id or self.brand_id
        self._log_lines = []
        self._start_run()
        try:
            result = self.run()
            self._complete_run(
                posts_created=result.get("posts_created", 0) if result else 0,
                posts_published=result.get("posts_published", 0) if result else 0,
            )
            return result
        except Exception as e:
            self._fail_run(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            return None

    def run(self) -> dict | None:
        """Override in subclass. Return dict with posts_created, posts_published counts."""
        raise NotImplementedError
