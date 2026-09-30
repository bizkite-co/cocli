#!/usr/bin/env python3
import os
import platform
import jsii
import aws_cdk as cdk
import tomli
from pathlib import Path
from constructs import IConstruct

from cdk_scraper_deployment.cdk_scraper_deployment_stack import CdkScraperDeploymentStack
from cdk_scraper_deployment.email_stack import CocliEmailStack
from cdk_scraper_deployment.testimonials_stack import FormIntakeStack, SIGNUP_FIELDS, TESTIMONIAL_FIELDS

# Stack id prefixes that get the 14-day (not 3-day) log retention below -
# both are FormIntakeStack instances that log raw captured submission data
# on receipt as a secondary recovery path alongside the S3 queue item.
_FORM_INTAKE_STACK_PREFIXES = ("CocliTestimonialsStack", "CocliSignupsStack")

@jsii.implements(cdk.IAspect)
class LogRetentionAspect:
    """3 days for the default high-volume scraper/worker log groups.

    FormIntakeStack instances (testimonials, signups) are an intentional
    exception at 14 days: their Lambda logs the raw captured submission
    data on receipt (see testimonials_stack.py) as a secondary recovery
    path alongside the S3 queue item itself - Mark asked for 14 days
    there specifically, not the standard 3, so a submission can still be
    recovered from CloudWatch even if the primary S3 write path had a
    problem.
    """

    def visit(self, node: IConstruct) -> None:
        if isinstance(node, cdk.aws_logs.CfnLogGroup):
            if any(prefix in node.node.path for prefix in _FORM_INTAKE_STACK_PREFIXES):
                node.retention_in_days = 14
            else:
                node.retention_in_days = 3

app = cdk.App()
cdk.Aspects.of(app).add(LogRetentionAspect())
# Findability in a shared/multi-tenant AWS account (Resource Groups, Cost
# Explorer) without renaming any already-deployed stack - CloudFormation
# can't rename a stack in place, so tagging is the non-disruptive answer.
cdk.Tags.of(app).add("Project", "cocli")

# 1. Determine COCLI_DATA_HOME
# Try env var, then fallback to common locations or relative path
env_data_home = os.getenv("COCLI_DATA_HOME")
if env_data_home:
    data_home = Path(env_data_home).resolve()
else:
    # Fallback: Assume we are in repo/cdk_scraper_deployment/
    repo_root = Path(__file__).parent.parent
    data_home = (repo_root / "data").resolve()

# 2. Determine Campaign Name
# Priority: 1. CDK Context (-c campaign=NAME)  2. Current Active Campaign (cocli_config.toml)
campaign_name = app.node.try_get_context("campaign")

if not campaign_name:
    # Try to find cocli_config.toml
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cocli"
    # Mac/Windows overrides (simplified check)
    if platform.system() == "Darwin":
        config_home = Path.home() / "Library" / "Preferences" / "cocli"
    
    # Check COCLI_CONFIG_HOME override
    if os.environ.get("COCLI_CONFIG_HOME"):
        config_home = Path(os.environ["COCLI_CONFIG_HOME"])
    
    cocli_config_path = config_home / "cocli_config.toml"
    
    if cocli_config_path.exists():
        try:
            with open(cocli_config_path, "rb") as f:
                global_config = tomli.load(f)
            campaign_name = global_config.get("campaign", {}).get("name")
        except Exception:
            pass

if not campaign_name:
    raise ValueError("No campaign specified. Use '-c campaign=NAME' or set a current campaign in cocli.")

print(f"Deploying infrastructure for campaign: {campaign_name}")

# 3. Load Campaign Configuration
campaign_dir = data_home / "campaigns" / campaign_name
config_path = campaign_dir / "config.toml"

if not config_path.exists():
    raise FileNotFoundError(f"Configuration file not found at: {config_path}")

with open(config_path, "rb") as f:
    config = tomli.load(f)

aws_config = config.get("aws", {})
domain = config.get("hosted-zone-domain") or aws_config.get("hosted-zone-domain")
zone_id = config.get("hosted-zone-id") or aws_config.get("hosted-zone-id")
account = aws_config.get("account")
region = aws_config.get("region", os.getenv("CDK_DEFAULT_REGION", "us-east-1"))

if not domain or not zone_id:
    raise ValueError(f"Campaign '{campaign_name}' is missing 'hosted-zone-domain' or 'hosted-zone-id' in config.toml")

# 4. Instantiate Stack
# If account is in config, use it. Otherwise rely on CLI profile.
env = None
if account:
    env = cdk.Environment(account=str(account), region=region)
else:
    env = cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=region)

# Determine the RPi user name (defaulting to the profile name used)
rpi_user_name = aws_config.get("rpi_user_name") or aws_config.get("profile") or aws_config.get("aws_profile") or "bizkite-support"
data_bucket_name = aws_config.get("data_bucket_name") or f"cocli-data-{campaign_name}"
ou_arn = aws_config.get("organizational-unit-arn")
worker_count = aws_config.get("worker_count", 1)

# Cognito Auth Configuration (Optional)
cognito_config = aws_config.get("cognito", {})
user_pool_id = cognito_config.get("user_pool_id")
user_pool_client_id = cognito_config.get("client_id")
user_pool_domain = cognito_config.get("domain")

# Use a unique stack name per campaign to avoid global naming conflicts and stuck stacks
# Maintaining legacy name for turboship to avoid resource duplication
if campaign_name == "turboship":
    stack_name = "CdkScraperDeploymentStack"
else:
    stack_name = f"CdkScraperDeploymentStack-{campaign_name}"

is_uat = "uat" in (aws_config.get("profile") or aws_config.get("aws_profile") or "").lower()

CdkScraperDeploymentStack(app, stack_name,
    env=env,
    campaign_config={
        "name": campaign_name,
        "domain": domain,
        "zone_id": zone_id,
        "data_bucket_name": data_bucket_name,
        "rpi_user_name": rpi_user_name,
        "user_pool_id": user_pool_id,
        "user_pool_client_id": user_pool_client_id,
        "user_pool_domain": user_pool_domain,
        "ou_arn": ou_arn,
        "worker_count": worker_count,
        "is_uat": is_uat,
    }
)

email_config = config.get("email") or {}
from_address = email_config.get("from_address") or ""
if from_address and "@" in from_address:
    product_domain = from_address.split("@", 1)[1]
    # Always its own subdomain, never the bare product domain: cocli's
    # outbound-sales email must not share reputation with whatever else
    # already sends mail as the product itself (transactional/reports) -
    # see the roadmap/getretirementtaxanalyzer.com precedent (2026-09-16),
    # where those were already separate, pre-existing uses of the bare
    # domain before this outbound-sales identity ever existed.
    sending_domain = f"outreach.{product_domain}"
    ses_region = email_config.get("ses_region") or "us-west-1"
    config_set_name = f"cocli-outreach-{campaign_name}"
    mail_from = f"bounce.{sending_domain}"
    email_env = cdk.Environment(account=str(account) if account else os.getenv("CDK_DEFAULT_ACCOUNT"), region=ses_region)
    CocliEmailStack(
        app,
        f"CocliEmailStack-{campaign_name}",
        env=email_env,
        campaign_name=campaign_name,
        sending_domain=sending_domain,
        mail_from_domain=mail_from,
        configuration_set_name=config_set_name,
    )

outreach_domain = aws_config.get("outreach-hosted-zone-domain")
if outreach_domain:
    form_intake_env = cdk.Environment(
        account=str(account) if account else os.getenv("CDK_DEFAULT_ACCOUNT"), region=region
    )
    # Stack id kept identical to before the FormIntakeStack generalization
    # (was CocliTestimonialsStack) - see testimonials_stack.py's module
    # docstring for why the class rename alone is safe but this id must
    # not change.
    FormIntakeStack(
        app,
        f"CocliTestimonialsStack-{campaign_name}",
        env=form_intake_env,
        campaign_name=campaign_name,
        data_bucket_name=data_bucket_name,
        allowed_origin=f"https://{outreach_domain}",
        queue_name="testimonials",
        fields=TESTIMONIAL_FIELDS,
        event_prefix="testimonial_submission",
    )
    # General "haven't emailed them yet" signup/lead-capture form (Mark,
    # 2026-09-30) - no password field, see SIGNUP_FIELDS. Notification
    # routing (ntfy / Twilio SMS via the cross-account notification
    # service) is deliberately deferred; this just gets every submission
    # recorded + trackable first.
    FormIntakeStack(
        app,
        f"CocliSignupsStack-{campaign_name}",
        env=form_intake_env,
        campaign_name=campaign_name,
        data_bucket_name=data_bucket_name,
        allowed_origin=f"https://{outreach_domain}",
        queue_name="signups",
        fields=SIGNUP_FIELDS,
        event_prefix="signup_submission",
    )

app.synth()