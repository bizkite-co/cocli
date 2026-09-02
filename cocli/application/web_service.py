from __future__ import annotations
import subprocess
import toml
import boto3
from typing import Optional, Any, Callable
from cocli.core.config import get_campaign_dir
from cocli.core.reporting import get_campaign_stats, get_exclusions_data, get_queries_data, get_locations_data
from cocli.application.lead_export_service import LeadExportResult

class WebService:
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name

    def resolve_deployment_config(
        self,
        profile: Optional[str] = None,
        bucket_name: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> dict[str, str]:
        """Resolves AWS profile, domain, and bucket name based on campaign config."""
        campaign_dir = get_campaign_dir(self.campaign_name)
        if not campaign_dir:
            raise ValueError(f"Campaign directory not found for {self.campaign_name}")

        config_path = campaign_dir / "config.toml"
        config: dict[str, Any] = {}
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

    def fetch_cdk_outputs(self, profile: str) -> dict[str, str]:
        """Fetches identity pool/user pool details from CloudFormation stack."""
        env_updates: dict[str, str] = {}
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

        # Some campaigns' auth (User Pool Client + Hosted UI domain) is owned
        # by a separate, external CDK stack rather than CdkScraperDeploymentStack
        # - e.g. turboship's is managed by turboheatweldingtools/homepage's
        # TurboshipAuthStack, which can recreate its User Pool Client under a
        # new ID independently of this repo. Rather than hardcoding that
        # repo's naming scheme here, a campaign opts into a live SSM lookup
        # by setting these two keys in its own config.toml:
        #   [aws]
        #   cognito_client_id_ssm_param = "/prod/cocli/cognito/client-id"
        #   cognito_domain_ssm_param = "/prod/cocli/cognito/domain-url"
        # Campaigns that don't set them keep using the static
        # cocli_user_pool_client_id / cocli_user_pool_domain config values.
        campaign_dir = get_campaign_dir(self.campaign_name)
        if campaign_dir:
            config_path = campaign_dir / "config.toml"
            if config_path.exists():
                with open(config_path, "r") as f:
                    aws_config = toml.load(f).get("aws", {})
                client_id_param = aws_config.get("cognito_client_id_ssm_param")
                domain_param = aws_config.get("cognito_domain_ssm_param")
                if client_id_param or domain_param:
                    try:
                        ssm = session.client("ssm")
                        if client_id_param:
                            env_updates["COCLI_USER_POOL_CLIENT_ID"] = ssm.get_parameter(Name=client_id_param)["Parameter"]["Value"]
                        if domain_param:
                            env_updates["COCLI_USER_POOL_DOMAIN"] = ssm.get_parameter(Name=domain_param)["Parameter"]["Value"]
                    except Exception:
                        pass

        # Fallback: the pool itself has a domain configured (Cognito Hosted
        # UI custom domain) even when no SSM parameter is available - fetch
        # it directly so the dashboard's login redirect isn't silently
        # disabled when the local token expires.
        user_pool_id = env_updates.get("COCLI_USER_POOL_ID")
        if user_pool_id and "COCLI_USER_POOL_DOMAIN" not in env_updates:
            try:
                idp = session.client("cognito-idp")
                pool = idp.describe_user_pool(UserPoolId=user_pool_id)["UserPool"]
                domain = pool.get("CustomDomain") or pool.get("Domain")
                if domain:
                    env_updates["COCLI_USER_POOL_DOMAIN"] = f"https://{domain}"
            except Exception:
                pass

        return env_updates

    def get_campaign_reports(self) -> dict[str, Any]:
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

    def export_and_upload_emails_csv(
        self,
        s3_client: Any,
        bucket_name: str,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> LeadExportResult:
        """
        Refreshes the customer-facing enriched-emails CSV end to end: pulls
        fresh gm-list/gm-details/enrichment results and WAL data from the Pi
        cluster, compacts the prospects index, regenerates the export
        USV/CSV, and uploads both to S3.

        This is the data-refresh subset of `cocli web deploy`, split out
        (2026-09-01) so it can run on its own cadence - needs AWS/1Password
        auth, so it's run manually - without also rebuilding/redeploying the
        static site shell (npm build + CDK output fetch), which stays a
        deliberate manual action via `web deploy`.
        """
        from cocli.application.index_service import IndexService
        from cocli.application.lead_export_service import export_enriched_emails

        def log(msg: str) -> None:
            if log_callback:
                log_callback(msg)

        log(
            "Syncing gm-list/gm-details/enrichment results from Pi cluster "
            f"for {self.campaign_name}..."
        )
        try:
            subprocess.run(
                ["uv", "run", "cocli", "sync", "pi-results", "--campaign", self.campaign_name],
                check=True,
            )
        except Exception as e:
            log(f"Warning: Could not sync Pi results: {e}")

        log(f"Syncing google_maps_prospects WAL from Pi cluster for {self.campaign_name}...")
        try:
            from cocli.application.pi_sync_service import PiSyncService

            wal_sync_results = PiSyncService(self.campaign_name).sync_prospect_wal_to_s3(
                index_name="google_maps_prospects"
            )
            for r in wal_sync_results:
                if r.success:
                    log(f"  {r.host}: pushed {r.files_synced} WAL files")
                else:
                    log(f"  {r.host}: WAL sync failed - {r.error}")
        except Exception as e:
            log(f"Warning: Could not sync Pi WAL to S3: {e}")

        log(f"Compacting google_maps_prospects index for {self.campaign_name}...")
        try:
            compact_result = IndexService(self.campaign_name).compact(
                index_name="google_maps_prospects", log_callback=log
            )
            if not compact_result.success:
                log(f"Warning: compaction failed: {compact_result.message}")
        except Exception as e:
            log(f"Warning: Could not compact google_maps_prospects index: {e}")

        log("Regenerating export CSV...")
        export_result = export_enriched_emails(self.campaign_name)
        log(f"Exported {export_result.exported_count} companies")

        s3_client.upload_file(
            str(export_result.output_usv), bucket_name, f"exports/{self.campaign_name}-emails.usv"
        )
        s3_client.upload_file(
            str(export_result.output_csv),
            bucket_name,
            f"exports/{self.campaign_name}-emails.csv",
            ExtraArgs={
                "ContentType": "text/csv",
                "ContentDisposition": f'attachment; filename="{self.campaign_name}-emails.csv"',
                "CacheControl": "no-cache, must-revalidate",
            },
        )
        log(f"Uploaded exports/{self.campaign_name}-emails.{{usv,csv}} to s3://{bucket_name}")

        return export_result
