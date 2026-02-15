import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from ..core.reporting import get_campaign_stats
from ..core.config import get_campaign

logger = logging.getLogger(__name__)

class ReportingService:
    def __init__(self, campaign_name: Optional[str] = None):
        self.campaign_name = campaign_name or get_campaign() or "default"

    def get_campaign_stats(self, campaign_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns a comprehensive dictionary of campaign statistics.
        """
        target_campaign = campaign_name or self.campaign_name
        try:
            stats = get_campaign_stats(target_campaign)
            stats['last_updated'] = datetime.now(timezone.utc).isoformat()
            stats['campaign_name'] = target_campaign
            return stats
        except Exception as e:
            logger.error(f"Failed to get campaign stats for {target_campaign}: {e}")
            return {
                "error": str(e),
                "campaign_name": target_campaign,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

    def get_email_analysis(self, campaign_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns deep analysis on emails for the campaign.
        Corresponds to 'make analyze-emails' / 'scripts/debug_stats.py'.
        """
        target_campaign = campaign_name or self.campaign_name
        # For now, we'll just return some placeholder data or 
        # a subset of what get_campaign_stats provides until 
        # we migrate more of debug_stats.py
        stats = self.get_campaign_stats(target_campaign)
        return {
            "total_emails": stats.get("emails_found_count", 0),
            "companies_with_emails": stats.get("companies_with_emails_count", 0),
            "campaign_name": target_campaign
        }
