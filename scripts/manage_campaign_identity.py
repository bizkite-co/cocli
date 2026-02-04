#!/usr/bin/env python3
import argparse
import configparser
import json
from pathlib import Path
import boto3
import sys

from typing import Any, Dict

def get_limited_policy(bucket_name: str) -> Dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
                "Resource": f"arn:aws:s3:::{bucket_name}"
            },
            {
                "Effect": "Allow",
                "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
                "Resource": f"arn:aws:s3:::{bucket_name}/*"
            }
        ]
    }

def setup_iam_user(iam_client: Any, campaign_name: str, bucket_name: str) -> Dict[str, str]:
    user_name = f"cocli-scraper-{campaign_name}"
    policy_name = f"CocliScraperPolicy-{campaign_name}"
    print(f"Setting up IAM User: {user_name}...")
    try:
        iam_client.create_user(UserName=user_name)
    except Exception: # Broad catch for existing user
        print(f"  User {user_name} already exists.")

    iam_client.put_user_policy(
        UserName=user_name,
        PolicyName=policy_name,
        PolicyDocument=json.dumps(get_limited_policy(bucket_name))
    )
    print(f"  Attached limited policy for: {bucket_name}")

    print("  Generating fresh access keys...")
    response = iam_client.create_access_key(UserName=user_name)
    return {
        "access_key": str(response["AccessKey"]["AccessKeyId"]),
        "secret_key": str(response["AccessKey"]["SecretAccessKey"])
    }

def update_local_aws_config(profile_name: str, access_key: str, secret_key: str, region: str) -> None:
    aws_dir = Path.home() / ".aws"
    aws_dir.mkdir(exist_ok=True)
    
    creds = configparser.ConfigParser()
    creds_path = aws_dir / "credentials"
    if creds_path.exists():
        creds.read(creds_path)
    creds[profile_name] = {"aws_access_key_id": access_key, "aws_secret_access_key": secret_key}
    with open(creds_path, "w") as f:
        creds.write(f)
    
    conf = configparser.ConfigParser()
    conf_path = aws_dir / "config"
    if conf_path.exists():
        conf.read(conf_path)
    conf[f"profile {profile_name}"] = {"region": region, "output": "json"}
    with open(conf_path, "w") as f:
        conf.write(f)
    print(f"Updated local AWS profile: {profile_name}")

def update_envrc(campaign_name: str) -> None:
    import tomllib
    config_path = Path(f"data/campaigns/{campaign_name}/config.toml")
    admin_profile = None
    if config_path.exists():
        with open(config_path, "rb") as f:
            config_data = tomllib.load(f)
            admin_profile = config_data.get("aws", {}).get("profile")
    
    admin_profile = str(admin_profile or campaign_name)
    envrc_path = Path(".envrc")
    if envrc_path.exists():
        lines = []
        found = False
        with open(envrc_path, "r") as f:
            for line in f:
                if line.strip().startswith("export AWS_PROFILE="):
                    lines.append(f'export AWS_PROFILE="{admin_profile}"\n')
                    found = True
                else:
                    lines.append(line)
        if not found:
            lines.append(f'export AWS_PROFILE="{admin_profile}"\n')
        with open(envrc_path, "w") as f:
            f.writelines(lines)
        print(f"Updated .envrc with Admin Profile: {admin_profile}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Securely initialize campaign identity.")
    parser.add_argument("--campaign", required=True, help="Campaign name.")
    parser.add_argument("--admin-profile", default="westmonroe-support", help="Admin profile to use for creation.")
    parser.add_argument("--region", default="us-east-1", help="Region for the campaign bucket.")
    
    args = parser.parse_args()
    bucket_name = f"{args.campaign}-cocli-data-use1"
    
    print(f"--- Initializing Identity for {args.campaign} ---")
    
    try:
        session = boto3.Session(profile_name=args.admin_profile)
        iam = session.client("iam")
        sm = session.client("secretsmanager")
        
        # 1. IAM
        keys = setup_iam_user(iam, args.campaign, bucket_name)
        
        # 2. Secrets Manager
        secret_id = f"cocli/campaign/{args.campaign}"
        secret_val = {"aws_access_key_id": keys["access_key"], "aws_secret_access_key": keys["secret_key"], "region": args.region}
        try:
            sm.describe_secret(SecretId=secret_id)
            sm.put_secret_value(SecretId=secret_id, SecretString=json.dumps(secret_val))
        except sm.exceptions.ResourceNotFoundException:
            sm.create_secret(Name=secret_id, SecretString=json.dumps(secret_val))
        print(f"Synced secret: {secret_id}")
        
        # 3. Local Config
        update_local_aws_config(args.campaign, keys["access_key"], keys["secret_key"], args.region)
        
        print(f"\n[SUCCESS] Campaign '{args.campaign}' identity is ready.")
        print(f"Next step (on RPI network): python3 scripts/deploy_rpi_creds.py --campaign {args.campaign} --host <pi> --from-secret")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()