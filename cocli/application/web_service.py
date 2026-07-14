import toml
import boto3
from typing import Optional, Dict, Any
from cocli.core.config import get_campaign_dir
from cocli.core.reporting import get_campaign_stats, get_exclusions_data, get_queries_data, get_locations_data

class WebService:
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name

    def resolve_deployment_config(
        self,
        profile: Optional[str] = None,
        bucket_name: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> Dict[str, str]:
        """Resolves AWS profile, domain, and bucket name based on campaign config."""
        campaign_dir = get_campaign_dir(self.campaign_name)
        if not campaign_dir:
            raise ValueError(f"Campaign directory not found for {self.campaign_name}")

        config_path = campaign_dir / "config.toml"
        config: Dict[str, Any] = {}
        if config_path.exists():
            with open(config_path, "r") as f:
                config = toml.load(f)

        # Resolve AWS profile
        if not profile:
            aws_config = config.get("aws", {})
            profile = (
                aws_config.get("profile")
                or aws_config.get("aws_profile")
                or aws_config.get("aws-profile")
                or config.get("aws-profile")
            )
        if not profile:
            raise ValueError("AWS profile not specified.")

        # Resolve Domain
        aws_config = config.get("aws", {})
        hosted_zone_domain = aws_config.get("hosted-zone-domain") or config.get("hosted-zone-domain")

        if not domain:
            if not hosted_zone_domain:
                raise ValueError("Domain not specified and hosted-zone-domain missing in config.toml.")
            domain = f"cocli.{hosted_zone_domain}"

        # Resolve Bucket
        if not bucket_name:
            base_domain = str(hosted_zone_domain) if hosted_zone_domain else str(domain)
            bucket_slug = base_domain.replace(".", "-")
            bucket_name = f"cocli-web-assets-{bucket_slug}"

        return {
            "profile": profile,
            "domain": domain,
            "bucket_name": bucket_name,
        }

    def fetch_cdk_outputs(self, profile: str) -> Dict[str, str]:
        """Fetches identity pool/user pool details from CloudFormation stack."""
        env_updates: Dict[str, str] = {}
        session = boto3.Session(profile_name=profile)
        cf = session.client("cloudformation")
        stack_name = f"CdkScraperDeploymentStack-{self.campaign_name}"
        if self.campaign_name == "turboship":
            stack_name = "CdkScraperDeploymentStack"

        try:
            response = cf.describe_stacks(StackName=stack_name)
            outputs = response["Stacks"][0].get("Outputs", [])
            for output in outputs:
                key = output["OutputKey"]
                val = output["OutputValue"]
                if key == "IdentityPoolId":
                    env_updates["COCLI_IDENTITY_POOL_ID"] = val
                elif key == "UserPoolId":
                    env_updates["COCLI_USER_POOL_ID"] = val
                elif key == "UserPoolClientId":
                    env_updates["COCLI_USER_POOL_CLIENT_ID"] = val
                elif key == "CampaignUpdatesQueueUrl":
                    env_updates["COCLI_COMMAND_QUEUE_URL"] = val
        except Exception:
            pass

        return env_updates

    def get_campaign_reports(self) -> Dict[str, Any]:
        """Generates all reports for the campaign."""
        stats = get_campaign_stats(self.campaign_name)
        exclusions = get_exclusions_data(self.campaign_name)
        queries = get_queries_data(self.campaign_name)
        locations = get_locations_data(self.campaign_name)
        return {
            "stats": stats,
            "exclusions": exclusions,
            "queries": queries,
            "locations": locations,
        }
