import logging
import requests
import os
import time
from typing import Optional, Dict
from playwright.async_api import Page

logger = logging.getLogger(__name__)

# Simple in-memory cache to rate-limit alerts
# alert_key -> timestamp
_last_alert_times: Dict[str, float] = {}
ALERT_COOLDOWN_SECONDS = 900 # 15 minutes

def send_alert(
    message: str,
    title: Optional[str] = None,
    priority: int = 3,
    tags: Optional[list[str]] = None,
    cooldown_key: Optional[str] = None,
) -> bool:
    """
    Sends an alert notification to ntfy.sh.
    Resolves ntfy topic/url from:
    1. Env var COCLI_ALERT_NTFY_URL
    2. Campaign config.toml [alerts] ntfy-url or [alerts] ntfy_url
    """
    now = time.time()
    if cooldown_key:
        last_time = _last_alert_times.get(cooldown_key, 0)
        if now - last_time < ALERT_COOLDOWN_SECONDS:
            logger.debug(f"Alert for '{cooldown_key}' suppressed due to cooldown.")
            return False

    ntfy_url = os.getenv("COCLI_ALERT_NTFY_URL")
    
    if not ntfy_url:
        from cocli.core.config import get_campaign
        campaign_name = get_campaign()
        if campaign_name:
            try:
                from cocli.models.campaigns.campaign import Campaign
                campaign = Campaign.load(campaign_name)
                if hasattr(campaign, "alerts") and campaign.alerts and campaign.alerts.ntfy_url:
                    ntfy_url = campaign.alerts.ntfy_url
            except Exception:
                pass

    if not ntfy_url:
        logger.debug("ntfy.sh alerting is not configured (no URL found).")
        return False

    try:
        headers = {}
        if title:
            headers["Title"] = title
        headers["Priority"] = str(priority)
        if tags:
            headers["Tags"] = ",".join(tags)
            
        resp = requests.post(
            ntfy_url,
            data=message.encode("utf-8"),
            headers=headers,
            timeout=5
        )
        if resp.status_code == 200:
            logger.info(f"Alert sent to ntfy.sh: {message}")
            if cooldown_key:
                _last_alert_times[cooldown_key] = now
            return True
        else:
            logger.warning(f"Failed to send alert to ntfy.sh (status code: {resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending alert to ntfy.sh: {e}")
        return False


async def check_and_alert_google_maps_block(page: Page, context_message: str) -> bool:
    """
    Checks the current page HTML content for known Google Maps rate-limit/CAPTCHA/block signatures.
    If found, triggers a critical ntfy alert.
    """
    try:
        url = page.url
        if "consent.google.com" in url or "google.com/recaptcha" in url:
            msg = f"Google Maps redirection block detected at {url}. Context: {context_message}"
            import socket
            hostname = socket.gethostname()
            send_alert(
                message=f"[{hostname}] {msg}",
                title="Google Maps Redirection Block",
                priority=5,
                tags=["critical", "skull", "fire"],
                cooldown_key=f"google_maps_block_{hostname}"
            )
            return True
            
        html = await page.content()
        html_lower = html.lower()
        
        signatures = [
            "unusual traffic from your computer network",
            "systems have detected unusual traffic",
            "unusual traffic",
            "recaptcha",
            "validate your identity",
            "solving the captcha"
        ]
        
        for sig in signatures:
            if sig in html_lower:
                msg = f"Google Maps block page detected containing signature: '{sig}'. Context: {context_message}"
                import socket
                hostname = socket.gethostname()
                send_alert(
                    message=f"[{hostname}] {msg}",
                    title="Google Maps Block Page",
                    priority=5,
                    tags=["critical", "skull", "fire"],
                    cooldown_key=f"google_maps_block_{hostname}"
                )
                return True
                
    except Exception as e:
        logger.debug(f"Failed to check page for block signatures: {e}")
        
    return False
