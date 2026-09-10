"""Build a Google Voice call URL targeting the configured Google Voice account."""

from __future__ import annotations

import re
from typing import Optional


def google_voice_url(phone: str, campaign_name: Optional[str] = None) -> str:
    """
    Build a Google Voice call URL targeting the configured Google Voice account.

    Loads configuration from the active campaign (or global config).
    Defaults to account_email="bizkitellc@gmail.com" and caller_number="(909) 323-2647".
    """
    from cocli.core.config import get_campaign, load_campaign_config, load_global_config

    camp = campaign_name or get_campaign()
    cfg = load_campaign_config(camp) if camp else load_global_config()
    gv_cfg = cfg.get("google_voice", {})

    account_email = gv_cfg.get("account_email") or "bizkitellc@gmail.com"
    account_index = gv_cfg.get("account_index", 0)

    cleaned = re.sub(r"\D", "", str(phone))
    if not cleaned.startswith("1") and len(cleaned) == 10:
        cleaned = "1" + cleaned
    elif cleaned.startswith("1") and len(cleaned) == 11:
        pass

    params: list[str] = []
    if account_email:
        params.append(f"authuser={account_email}")
    params.append(f"a=nc,%2B{cleaned}")

    query_str = "&".join(params)
    return f"https://voice.google.com/u/{account_index}/calls?{query_str}"
