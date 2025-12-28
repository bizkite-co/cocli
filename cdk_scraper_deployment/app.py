#!/usr/bin/env python3
import os
import platform
import aws_cdk as cdk
import tomli
from pathlib import Path

from cdk_scraper_deployment.cdk_scraper_deployment_stack import CdkScraperDeploymentStack

app = cdk.App()

# 1. Determine COCLI_DATA_HOME
# Try env var, then fallback to common locations or relative path
env_data_home = os.getenv("COCLI_DATA_HOME")
if env_data_home:
    data_home = Path(env_data_home).resolve()
else:
    # Fallback: Assume we are in repo/cdk_scraper_deployment/
    repo_root = Path(__file__).parent.parent
    data_home = (repo_root / "cocli_data").resolve()

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

CdkScraperDeploymentStack(app, "CdkScraperDeploymentStack",
    env=env,
    campaign_config={
        "name": campaign_name,
        "domain": domain,
        "zone_id": zone_id
    }
)

app.synth()