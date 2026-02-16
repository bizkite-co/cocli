import logging
from typing import Any, Dict, Optional, cast, List
from datetime import datetime, timezone

from ..core.reporting import get_campaign_stats
from ..core.config import get_campaign, get_context

logger = logging.getLogger(__name__)

class ReportingService:
    def __init__(self, campaign_name: Optional[str] = None):
        self.campaign_name = campaign_name or get_campaign() or "default"

    def get_environment_status(self) -> Dict[str, Any]:
        """
        Returns the current status of the cocli environment.
        Corresponds to 'cocli status'.
        """
        import os
        
        campaign_name = get_campaign()
        context_filter = get_context()
        
        # Scrape Strategy Detection
        is_fargate = os.getenv("COCLI_RUNNING_IN_FARGATE") == "true"
        aws_profile = os.getenv("AWS_PROFILE")
        local_dev = os.getenv("LOCAL_DEV")
        
        strategy = "Unknown"
        details = []

        if is_fargate:
            strategy = "Cloud / Fargate"
            details.append("Running inside AWS Fargate container")
            details.append("Using IAM Task Role for permissions")
        elif local_dev:
            strategy = "Local Docker (Hybrid)"
            details.append("Running in local Docker container")
            if aws_profile:
                 details.append(f"Using AWS Profile: {aws_profile}")
        else:
            strategy = "Local Host"
            details.append("Running directly on host machine")
            if aws_profile:
                 details.append(f"Using AWS Profile: {aws_profile}")
            else:
                 details.append("Using default AWS credentials chain")

        queue_url = os.getenv("COCLI_ENRICHMENT_QUEUE_URL")
        
        return {
            "campaign": campaign_name,
            "context": context_filter,
            "strategy": strategy,
            "strategy_details": details,
            "enrichment_queue_url": queue_url
        }

    def get_campaign_stats(self, campaign_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns a comprehensive dictionary of campaign statistics.
        Caches the result to disk.
        """
        target_campaign = campaign_name or self.campaign_name
        try:
            stats = get_campaign_stats(target_campaign)
            stats['last_updated'] = datetime.now(timezone.utc).isoformat()
            stats['campaign_name'] = target_campaign
            
            # Cache to disk
            self.save_cached_report(target_campaign, "status", stats)
            
            return stats
        except Exception as e:
            logger.error(f"Failed to get campaign stats for {target_campaign}: {e}")
            return {
                "error": str(e),
                "campaign_name": target_campaign,
                "last_updated": datetime.now(timezone.utc).isoformat()
            }

    async def get_cluster_health(self) -> List[Dict[str, Any]]:
        """
        Returns health status of all workers in the cluster.
        This is an SSH-based real-time check.
        """
        # We might need to resolve the worker service from the global container 
        # or instantiate a new one for this campaign.
        # Given ServiceContainer's factory pattern, we can just create one.
        from .worker_service import WorkerService
        ws = WorkerService(campaign_name=self.campaign_name)
        return await ws.get_cluster_health()

    def save_cached_report(self, campaign_name: str, report_type: str, data: Dict[str, Any]) -> None:
        """Saves a report to the local reports cache and the campaign exports dir."""
        from ..core.config import get_cocli_app_data_dir, get_campaigns_dir
        
        # 1. Save to User App Data Cache (Hidden fallback)
        report_dir = get_cocli_app_data_dir() / "reports" / campaign_name
        report_dir.mkdir(parents=True, exist_ok=True)
        
        import json
        with open(report_dir / f"{report_type}.json", "w") as f:
            json.dump(data, f, indent=2)

        # 2. Save to Campaign Exports Directory (Primary location)
        exports_dir = get_campaigns_dir() / campaign_name / "exports"
        if exports_dir.exists():
            with open(exports_dir / f"{report_type}.json", "w") as f:
                json.dump(data, f, indent=2)

    def load_cached_report(self, campaign_name: str, report_type: str) -> Optional[Dict[str, Any]]:
        """Loads a report from the campaign exports dir or the user cache fallback."""
        from ..core.config import get_cocli_app_data_dir, get_campaigns_dir
        import json

        # 1. Try Campaign Exports first
        report_file = get_campaigns_dir() / campaign_name / "exports" / f"{report_type}.json"
        if report_file.exists():
            try:
                with open(report_file, "r") as f:
                    return cast(Dict[str, Any], json.load(f))
            except Exception:
                pass

        # 2. Fallback to User App Data Cache
        fallback_file = get_cocli_app_data_dir() / "reports" / campaign_name / f"{report_type}.json"
        if fallback_file.exists():
            try:
                with open(fallback_file, "r") as f:
                    return cast(Dict[str, Any], json.load(f))
            except Exception:
                return None
        return None

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
