# POLICY: frictionless-data-policy-enforcement
import logging
from pathlib import Path

from playwright.async_api import BrowserContext
from .headers import ANTI_BOT_HEADERS

logger = logging.getLogger(__name__)

_STEALTH_INIT_SCRIPT = (Path(__file__).parent / "stealth_init.js").read_text()

async def setup_stealth_context(
    context: BrowserContext,
) -> None:
    """
    Applies absolute high-fidelity anti-bot measures to a Playwright context.
    Uses centralized project ANTI_BOT_HEADERS.
    """
    # 1. Comprehensive Stealth Script (Fingerprint Masking)
    await context.add_init_script(_STEALTH_INIT_SCRIPT)

    # 2. Set Centralized Extra Headers
    await context.set_extra_http_headers(ANTI_BOT_HEADERS)

async def setup_optimized_context(
    context: BrowserContext, 
) -> None:
    """
    No-op for maximum fidelity. 
    Efficiency considerations are strictly prohibited during this troubleshooting phase.
    """
    pass
