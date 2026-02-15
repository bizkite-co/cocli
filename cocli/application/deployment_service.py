import logging
import subprocess
from typing import Any, Dict, Optional

from ..core.config import get_campaign, load_campaign_config

logger = logging.getLogger(__name__)

class DeploymentService:
    def __init__(self, campaign_name: Optional[str] = None):
        self.campaign_name = campaign_name or get_campaign() or "default"

    def deploy_infra(self) -> Dict[str, Any]:
        """
        Deploys AWS Infrastructure using CDK.
        Corresponds to 'make deploy-infra'.
        """
        try:
            # We can't easily run interactive CDK from here, but we can trigger it
            # This is a simplification.
            cmd = f"make deploy-infra CAMPAIGN={self.campaign_name}"
            subprocess.run(cmd, shell=True, check=True)
            return {"status": "success", "message": "Infra deployment triggered."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def scale_service(self, count: int) -> Dict[str, Any]:
        """
        Scales the enrichment service in Fargate.
        Corresponds to 'make scale'.
        """
        config = load_campaign_config(self.campaign_name)
        aws_config = config.get("aws", {})
        profile = aws_config.get("profile")
        region = aws_config.get("region", "us-east-1")
        
        try:
            cmd = [
                "aws", "ecs", "update-service",
                "--cluster", "ScraperCluster",
                "--service", "EnrichmentService",
                "--desired-count", str(count),
                "--region", region
            ]
            if profile:
                cmd.extend(["--profile", profile])
                
            subprocess.run(cmd, check=True)
            return {"status": "success", "count": count}
        except Exception as e:
            logger.error(f"Failed to scale service: {e}")
            return {"status": "error", "message": str(e)}
            
    def get_service_status(self) -> Dict[str, Any]:
        """
        Returns status of Fargate service.
        """
        from ..core.reporting import get_boto3_session, get_active_fargate_tasks
        config = load_campaign_config(self.campaign_name)
        session = get_boto3_session(config)
        
        count = get_active_fargate_tasks(session)
        return {"status": "active", "running_tasks": count}
