"""Agent 7: Token Manager — Automatically refreshes expiring OAuth tokens.

Schedule: Daily at 5am (before other agents run)
Reads: oauth_tokens table
Produces: refreshed access tokens before they expire
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import requests

from agents.base_agent import BaseAgent
from config import BRANDS
from db.models import OAuthToken, get_db

META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")


class TokenManager(BaseAgent):
    name = "token_manager"
    display_name = "Token Manager"

    def run(self) -> dict:
        db = get_db()
        tokens = db.query(OAuthToken).filter(OAuthToken.access_token != None).all()
        refreshed = 0
        warnings = 0

        for token in tokens:
            if not token.access_token:
                continue

            # Check if token is expiring soon (within 7 days) or already expired
            if token.expires_at and token.expires_at > datetime.utcnow() + timedelta(days=7):
                continue  # still good

            # Try to refresh based on platform
            if token.platform in ("facebook", "instagram"):
                success = self._refresh_meta_token(token)
                if success:
                    refreshed += 1
                else:
                    warnings += 1
                    self.log(
                        f"WARNING: {token.brand_id}/{token.platform} token "
                        f"needs manual refresh via Graph API Explorer"
                    )

            elif token.platform == "linkedin":
                success = self._refresh_linkedin_token(token)
                if success:
                    refreshed += 1
                else:
                    warnings += 1

        db.commit()
        db.close()

        if warnings > 0:
            self.log(f"{warnings} tokens need manual attention!")

        return {"posts_created": refreshed}

    def _refresh_meta_token(self, token: OAuthToken) -> bool:
        """Exchange a short-lived Meta token for a long-lived one (60 days)."""
        if not META_APP_ID or not META_APP_SECRET:
            self.log("META_APP_ID or META_APP_SECRET not configured")
            return False

        # First try: exchange for long-lived token
        url = "https://graph.facebook.com/v19.0/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "fb_exchange_token": token.access_token,
        }

        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.ok:
                data = resp.json()
                new_token = data.get("access_token")
                expires_in = data.get("expires_in", 5184000)  # default 60 days

                if new_token and new_token != token.access_token:
                    token.access_token = new_token
                    token.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                    self.log(
                        f"Refreshed {token.brand_id}/{token.platform} token — "
                        f"expires {token.expires_at.strftime('%Y-%m-%d')}"
                    )
                    return True
                elif new_token:
                    # Same token returned, update expiry
                    token.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                    return True

            self.log(f"Meta token refresh failed: {resp.text[:200]}")
            return False

        except Exception as e:
            self.log(f"Meta token refresh error: {e}")
            return False

    def _refresh_linkedin_token(self, token: OAuthToken) -> bool:
        """Refresh LinkedIn OAuth token using refresh_token."""
        if not token.refresh_token:
            self.log(f"No refresh_token for {token.brand_id}/linkedin")
            return False

        try:
            resp = requests.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token.refresh_token,
                    "client_id": os.getenv("LINKEDIN_CLIENT_ID", ""),
                    "client_secret": os.getenv("LINKEDIN_CLIENT_SECRET", ""),
                },
                timeout=30,
            )
            if resp.ok:
                data = resp.json()
                token.access_token = data.get("access_token")
                token.refresh_token = data.get("refresh_token", token.refresh_token)
                token.expires_at = datetime.utcnow() + timedelta(
                    seconds=data.get("expires_in", 86400)
                )
                self.log(f"Refreshed {token.brand_id}/linkedin token")
                return True

            self.log(f"LinkedIn token refresh failed: {resp.text[:200]}")
            return False
        except Exception as e:
            self.log(f"LinkedIn refresh error: {e}")
            return False
