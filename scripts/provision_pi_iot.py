#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path
import boto3
import sys
import requests

def _generate_get_tokens_script() -> str:
    return """#!/bin/bash
CAMPAIGN=$1
if [ -z "$CAMPAIGN" ]; then
    # Fallback to legacy path if no campaign provided
    if [ -d "$HOME/.cocli/iot" ]; then IOT_DIR="$HOME/.cocli/iot"; else IOT_DIR="/root/.cocli/iot"; fi
    CONFIG="$IOT_DIR/iot_config.json"
else
    # New campaign-specific path
    if [ -d "$HOME/.cocli/iot/$CAMPAIGN" ]; then IOT_DIR="$HOME/.cocli/iot/$CAMPAIGN"; else IOT_DIR="/root/.cocli/iot/$CAMPAIGN"; fi
    CONFIG="$IOT_DIR/iot_config.json"
fi

CURL=$(which curl 2>/dev/null || echo curl)
CERT="$IOT_DIR/cert.pem"
KEY="$IOT_DIR/private.key"
ROOT_CA="$IOT_DIR/root-CA.crt"

if [ ! -f "$CONFIG" ]; then
    echo "Error: Config not found at $CONFIG" >&2
    exit 1
fi

ENDPOINT=$(python3 -c "import json; print(json.load(open('$CONFIG'))['endpoint'])")
ALIAS=$(python3 -c "import json; print(json.load(open('$CONFIG'))['role_alias'])")

$CURL -s --cert "$CERT" --key "$KEY" --cacert "$ROOT_CA" \\
    "https://$ENDPOINT/role-aliases/$ALIAS/credentials" \\
    | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    out = {
        'Version': 1,
        'AccessKeyId': d['credentials']['accessKeyId'],
        'SecretAccessKey': d['credentials']['secretAccessKey'],
        'SessionToken': d['credentials']['sessionToken'],
        'Expiration': d['credentials']['expiration']
    }
    print(json.dumps(out))
except Exception as e:
    print(f'Error parsing IoT credentials: {e}', file=sys.stderr)
    sys.exit(1)
"
"""

def _configure_local_aws_profile(campaign: str, role: str) -> None:
    import configparser
    import os
    p = os.path.expanduser("~/.aws/config")
    c = configparser.ConfigParser()
    if os.path.exists(p):
        c.read(p)
    
    # We create profile: <campaign>-<role>-iot
    # e.g. roadmap-scraper-iot
    section = f"profile {campaign}-{role}-iot"
    if not c.has_section(section):
        c.add_section(section)
    
    home = os.path.expanduser("~")
    script_path = os.path.join(home, ".cocli/iot/get_tokens.sh")
    c.set(section, "credential_process", f"{script_path} {campaign}")
    c.set(section, "region", "us-east-1")
    
    # Also maintain legacy 'roadmap-iot' as an alias for the primary role
    if role == "scraper":
        legacy_section = f"profile {campaign}-iot"
        if not c.has_section(legacy_section):
            c.add_section(legacy_section)
        c.set(legacy_section, "credential_process", f"{script_path} {campaign}")
        c.set(legacy_section, "region", "us-east-1")

    with open(p, "w") as f:
        c.write(f)

def _configure_remote_aws_profile(host: str, user: str, campaign: str, role: str) -> None:
    setup_profile_cmd = f"""
    mkdir -p ~/.aws && python3 -c '
import configparser, os
p = os.path.expanduser("~/.aws/config")
c = configparser.ConfigParser()
if os.path.exists(p):
    c.read(p)

section = f"profile {campaign}-{role}-iot"
if not c.has_section(section): 
    c.add_section(section)

home = os.path.expanduser("~")
script_path = os.path.join(home, ".cocli/iot/get_tokens.sh")

c.set(section, "credential_process", f"{{script_path}} {campaign}")
c.set(section, "region", "us-east-1")

if "{role}" == "scraper":
    legacy = f"profile {campaign}-iot"
    if not c.has_section(legacy): c.add_section(legacy)
    c.set(legacy, "credential_process", f"{{script_path}} {campaign}")
    c.set(legacy, "region", "us-east-1")

with open(p, "w") as f: 
    c.write(f)
'
    """
    subprocess.run(["ssh", f"{user}@{host}", setup_profile_cmd], check=True)

def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a Raspberry Pi with an IoT Certificate identity.")
    parser.add_argument("--host", required=True, help="RPi hostname (e.g. cocli5x0.pi)")
    parser.add_argument("--campaign", required=True, help="Campaign name.")
    parser.add_argument("--role", choices=["scraper", "processor"], default="scraper", help="The granular role for this worker.")
    parser.add_argument("--user", default="mstouffer", help="SSH user.")
    parser.add_argument("--profile", default="westmonroe-support", help="Admin AWS profile.")
    
    args = parser.parse_args()
    
    session = boto3.Session(profile_name=args.profile)
    iot = session.client("iot")
    
    role_title = args.role.capitalize()
    role_alias = f"Cocli{role_title}Alias-{args.campaign}"
    
    print(f"--- Provisioning {args.host} as {role_title} for Campaign: {args.campaign} ---")
    
    # 1. Create Keys and Certificate
    print("Generating unique certificate...")
    response = iot.create_keys_and_certificate(setAsActive=True)
    cert_arn = response["certificateArn"]
    cert_pem = response["certificatePem"]
    priv_key = response["keyPair"]["PrivateKey"]
    
    # 2. Attach IoT Policy (Created by CDK)
    policy_name = f"CocliIoTAssumeRolePolicy-{args.campaign}"
    print(f"Attaching policy {policy_name} to certificate...")
    iot.attach_policy(policyName=policy_name, target=cert_arn)
    
    # 3. Save locally (temporary)
    tmp_dir = Path("/tmp/cocli_iot") / args.host
    tmp_dir.mkdir(parents=True, exist_ok=True)
    
    (tmp_dir / "cert.pem").write_text(cert_pem)
    (tmp_dir / "private.key").write_text(priv_key)
    
    # 3.1 Download Amazon Root CA
    print("Downloading Amazon Root CA...")
    root_ca_url = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"
    root_ca_response = requests.get(root_ca_url)
    root_ca_response.raise_for_status()
    (tmp_dir / "root-CA.crt").write_text(root_ca_response.text)
    
    # 4. Push to Target
    remote_root = "~/.cocli/iot"
    remote_dir = f"{remote_root}/{args.campaign}"
    
    try:
        if args.host in ["localhost", "127.0.0.1"]:
            print(f"Provisioning LOCAL machine: {remote_dir}...")
            local_root = Path.home() / ".cocli" / "iot"
            local_dir = local_root / args.campaign
            local_dir.mkdir(parents=True, exist_ok=True)
            local_root.chmod(0o700)
            local_dir.chmod(0o700)
            
            (local_dir / "cert.pem").write_text(cert_pem)
            (local_dir / "private.key").write_text(priv_key)
            (local_dir / "root-CA.crt").write_text(root_ca_response.text)
            (local_dir / "cert.pem").chmod(0o600)
            (local_dir / "private.key").chmod(0o600)
            (local_dir / "root-CA.crt").chmod(0o600)
            
            # Save Metadata
            metadata = {
                "campaign": args.campaign,
                "role": args.role,
                "role_alias": role_alias,
                "endpoint": iot.describe_endpoint(endpointType='iot:CredentialProvider')['endpointAddress']
            }
            (local_dir / "iot_config.json").write_text(json.dumps(metadata, indent=2))
            
            # Create get_tokens.sh helper
            get_tokens_content = _generate_get_tokens_script()
            (local_root / "get_tokens.sh").write_text(get_tokens_content)
            (local_root / "get_tokens.sh").chmod(0o755)
            
            _configure_local_aws_profile(args.campaign, args.role)
            print(f"\n[SUCCESS] Local machine is now provisioned as {role_title}.")
        else:
            print(f"Pushing certs to {args.user}@{args.host}:{remote_dir}...")
            subprocess.run(["ssh", f"{args.user}@{args.host}", f"mkdir -p {remote_dir} && chmod 700 {remote_root} && chmod 700 {remote_dir}"], check=True)
            subprocess.run(["scp", str(tmp_dir / "cert.pem"), f"{args.user}@{args.host}:{remote_dir}/"], check=True)
            subprocess.run(["scp", str(tmp_dir / "private.key"), f"{args.user}@{args.host}:{remote_dir}/"], check=True)
            subprocess.run(["scp", str(tmp_dir / "root-CA.crt"), f"{args.user}@{args.host}:{remote_dir}/"], check=True)
            subprocess.run(["ssh", f"{args.user}@{args.host}", f"chmod 600 {remote_dir}/*"], check=True)
            
            # Save Metadata
            metadata = {
                "campaign": args.campaign,
                "role": args.role,
                "role_alias": role_alias,
                "endpoint": iot.describe_endpoint(endpointType='iot:CredentialProvider')['endpointAddress']
            }
            (tmp_dir / "iot_config.json").write_text(json.dumps(metadata, indent=2))
            
            # Create get_tokens.sh helper
            get_tokens_content = _generate_get_tokens_script()
            (tmp_dir / "get_tokens.sh").write_text(get_tokens_content)

            subprocess.run(["scp", str(tmp_dir / "iot_config.json"), f"{args.user}@{args.host}:{remote_dir}/"], check=True)
            subprocess.run(["scp", str(tmp_dir / "get_tokens.sh"), f"{args.user}@{args.host}:{remote_root}/"], check=True)
            subprocess.run(["ssh", f"{args.user}@{args.host}", f"chmod +x {remote_root}/get_tokens.sh"], check=True)

            # 5. Configure AWS Profile for automatic refresh
            print(f"Configuring AWS profile '{args.campaign}-iot' on {args.host}...")
            _configure_remote_aws_profile(args.host, args.user, args.campaign, args.role)
            
            print(f"\n[SUCCESS] Pi ({args.host}) is now provisioned as {role_title}.")
            print(f"AWS profiles '{args.campaign}-iot' and 'roadmap-iot' configured for automatic refresh.")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        # Clean up local sensitive files
        import shutil
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    main()
