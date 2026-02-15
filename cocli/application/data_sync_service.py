import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..core.config import get_campaign, load_campaign_config, get_cocli_base_dir
from ..commands.smart_sync import run_smart_sync
from ..core.paths import paths

logger = logging.getLogger(__name__)

class DataSyncService:
    def __init__(self, campaign_name: Optional[str] = None):
        self.campaign_name = campaign_name or get_campaign() or "default"

    def sync_prospects(self, force: bool = False, full: bool = False) -> Dict[str, Any]:
        return self._sync_target("prospects", force, full)

    def sync_companies(self, force: bool = False, full: bool = False) -> Dict[str, Any]:
        return self._sync_target("companies", force, full)

    def sync_emails(self, force: bool = False, full: bool = False) -> Dict[str, Any]:
        return self._sync_target("emails", force, full)

    def sync_queues(self, force: bool = False, full: bool = False) -> Dict[str, Any]:
        return self._sync_target("queues", force, full)

    def sync_all(self, force: bool = False, full: bool = False) -> Dict[str, Any]:
        results = {}
        results["prospects"] = self.sync_prospects(force, full)
        results["companies"] = self.sync_companies(force, full)
        results["emails"] = self.sync_emails(force, full)
        results["queues"] = self.sync_queues(force, full)
        return results

    def _sync_target(self, target: str, force: bool = False, full: bool = False) -> Dict[str, Any]:
        config = load_campaign_config(self.campaign_name)
        aws_config = config.get("aws", {})
        bucket_name = aws_config.get("data_bucket_name") or f"cocli-data-{self.campaign_name}"
        data_dir = get_cocli_base_dir()
        
        prefix = ""
        local_base = Path(".")
        
        if target == "prospects":
            prefix = f"campaigns/{self.campaign_name}/indexes/google_maps_prospects/"
            local_base = data_dir / "campaigns" / self.campaign_name / "indexes" / "google_maps_prospects"
        elif target == "companies":
            prefix = "companies/"
            local_base = data_dir / "companies"
        elif target == "emails":
            prefix = f"campaigns/{self.campaign_name}/indexes/emails/"
            local_base = data_dir / "campaigns" / self.campaign_name / "indexes" / "emails"
        elif target == "queues":
            # For brevity, we'll just implement the wrapper for the most important ones or use the loop logic
            # This is a simplification for the service layer
            pass
            
        try:
            if target == "queues":
                 for q in ["gm-list", "gm-details", "enrichment"]:
                    local_base_completed = paths.queue(self.campaign_name, q) / "completed"
                    local_base_pending = paths.queue(self.campaign_name, q) / "pending"
                    
                    # Pending
                    run_smart_sync(f"{q}-pending", bucket_name, f"campaigns/{self.campaign_name}/queues/{q}/pending/", 
                                   local_base_pending, self.campaign_name, aws_config, force=force, full=full,
                                   completed_dir=local_base_completed)
                    # Completed
                    run_smart_sync(f"{q}-completed", bucket_name, f"campaigns/{self.campaign_name}/queues/{q}/completed/", 
                                   local_base_completed, self.campaign_name, aws_config, force=force, full=full)
            else:
                run_smart_sync(target, bucket_name, prefix, local_base, self.campaign_name, aws_config, force=force, full=full)
            return {"status": "success", "target": target}
        except Exception as e:
            logger.error(f"Sync failed for {target}: {e}")
            return {"status": "error", "message": str(e), "target": target}

    def push_queue(self, queue_name: str = "enrichment") -> Dict[str, Any]:
        """
        Pushes local queue items to S3.
        Corresponds to 'make push-queue' / 'scripts/push_queue.py'.
        """
        import boto3
        from ..core.paths import paths
        
        config = load_campaign_config(self.campaign_name)
        aws_config = config.get("aws", {})
        bucket_name = aws_config.get("data_bucket_name") or f"cocli-data-{self.campaign_name}"
        profile_name = aws_config.get("profile") or aws_config.get("aws_profile")

        try:
            session = boto3.Session(profile_name=profile_name)
            s3 = session.client("s3")
            
            local_queue_dir = paths.queue(self.campaign_name, queue_name) / "pending"
            if not local_queue_dir.exists():
                return {"status": "error", "message": f"Queue directory not found: {local_queue_dir}"}
                
            s3_prefix = f"campaigns/{self.campaign_name}/queues/{queue_name}/pending/"
            
            uploaded_count = 0
            for root, _, files in os.walk(local_queue_dir):
                for file in files:
                    local_path = Path(root) / file
                    rel_path = local_path.relative_to(local_queue_dir)
                    s3_key = f"{s3_prefix}{rel_path}"
                    
                    # Simple check to avoid redundant uploads
                    should_upload = True
                    try:
                        head = s3.head_object(Bucket=bucket_name, Key=s3_key)
                        if head['ContentLength'] == local_path.stat().st_size:
                            should_upload = False
                    except Exception:
                        pass
                        
                    if should_upload:
                        s3.upload_file(str(local_path), bucket_name, s3_key)
                        uploaded_count += 1
            
            return {"status": "success", "uploaded_count": uploaded_count}
        except Exception as e:
            logger.error(f"Push queue failed for {queue_name}: {e}")
            return {"status": "error", "message": str(e)}
