#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path
import boto3
import sys

def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a Raspberry Pi with an IoT Certificate identity.")
    parser.add_argument("--host", required=True, help="RPi hostname (e.g. cocli5x0.pi)")
    parser.add_argument("--campaign", required=True, help="Campaign name.")
    parser.add_argument("--user", default="mstouffer", help="SSH user.")
    parser.add_argument("--profile", default="westmonroe-support", help="Admin AWS profile.")
    
    args = parser.parse_args()
    
    session = boto3.Session(profile_name=args.profile)
    iot = session.client("iot")
    
    print(f"--- Provisioning {args.host} for Campaign: {args.campaign} ---")
    
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
    import requests
    root_ca_url = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"
    root_ca_response = requests.get(root_ca_url)
    root_ca_response.raise_for_status()
    (tmp_dir / "root-CA.crt").write_text(root_ca_response.text)
    
    # 4. Push to Pi
    remote_dir = "~/.cocli/iot"
    print(f"Pushing certs to {args.user}@{args.host}:{remote_dir}...")
    try:
        subprocess.run(["ssh", f"{args.user}@{args.host}", f"mkdir -p {remote_dir} && chmod 700 {remote_dir}"], check=True)
        subprocess.run(["scp", str(tmp_dir / "cert.pem"), f"{args.user}@{args.host}:{remote_dir}/"], check=True)
        subprocess.run(["scp", str(tmp_dir / "private.key"), f"{args.user}@{args.host}:{remote_dir}/"], check=True)
        subprocess.run(["scp", str(tmp_dir / "root-CA.crt"), f"{args.user}@{args.host}:{remote_dir}/"], check=True)
        subprocess.run(["ssh", f"{args.user}@{args.host}", f"chmod 600 {remote_dir}/*"], check=True)
        
        # Save Metadata
        metadata = {
            "campaign": args.campaign,
            "role_alias": f"CocliScraperAlias-{args.campaign}",
            "endpoint": iot.describe_endpoint(endpointType='iot:CredentialProvider')['endpointAddress']
        }
        (tmp_dir / "iot_config.json").write_text(json.dumps(metadata, indent=2))
        
        # 3.2 Create get_tokens.sh helper
        get_tokens_content = """#!/bin/bash
CURL=$(which curl 2>/dev/null || echo curl)
# Try both host and container paths
if [ -d "$HOME/.cocli/iot" ]; then
    IOT_DIR="$HOME/.cocli/iot"
else
    IOT_DIR="/root/.cocli/iot"
fi

CERT="$IOT_DIR/cert.pem"
KEY="$IOT_DIR/private.key"
ROOT_CA="$IOT_DIR/root-CA.crt"
CONFIG="$IOT_DIR/iot_config.json"

if [ ! -f "$CONFIG" ]; then
    echo "Error: Config not found at $CONFIG" >&2
    exit 1
fi

ENDPOINT=$(python3 -c "import json; print(json.load(open('$CONFIG'))['endpoint'])")
ALIAS=$(python3 -c "import json; print(json.load(open('$CONFIG'))['role_alias'])")

$CURL -s --cert "$CERT" --key "$KEY" --cacert "$ROOT_CA" \\
    "https://$ENDPOINT/role-aliases/$ALIAS/credentials" \\
    | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    out = {
        "Version": 1,
        "AccessKeyId": d["credentials"]["accessKeyId"],
        "SecretAccessKey": d["credentials"]["secretAccessKey"],
        "SessionToken": d["credentials"]["sessionToken"],
        "Expiration": d["credentials"]["expiration"]
    }
    print(json.dumps(out))
except Exception as e:
    print(f"Error parsing IoT credentials: {e}", file=sys.stderr)
    sys.exit(1)
'
"""
        (tmp_dir / "get_tokens.sh").write_text(get_tokens_content)

        subprocess.run(["scp", str(tmp_dir / "iot_config.json"), f"{args.user}@{args.host}:{remote_dir}/"], check=True)
        subprocess.run(["scp", str(tmp_dir / "get_tokens.sh"), f"{args.user}@{args.host}:{remote_dir}/"], check=True)
        subprocess.run(["ssh", f"{args.user}@{args.host}", f"chmod +x {remote_dir}/get_tokens.sh"], check=True)

        # 5. Configure AWS Profile for automatic refresh
        print(f"Configuring AWS profile '{args.campaign}-iot' on {args.host}...")
        
        # Let's use a simpler approach for the profile in the AWS config
        setup_profile_cmd = f"""
        python3 -c '
import configparser, os
p = os.path.expanduser("~/.aws/config")
c = configparser.ConfigParser()
c.read(p)
sections = ["profile {args.campaign}-iot", "profile roadmap-iot"]
for s in sections:
    if not c.has_section(s): c.add_section(s)
    c.set(s, "credential_process", "/root/.cocli/iot/get_tokens.sh")
    c.set(s, "region", "us-east-1")
with open(p, "w") as f: c.write(f)
'
        """
        # We use /root/.cocli/iot/ because that's where it's mounted in the container.
        # But we also want it to work on the host. 
        # Actually, the supervisor in the container uses AWS_PROFILE=roadmap-iot.
        
        subprocess.run(["ssh", f"{args.user}@{args.host}", setup_profile_cmd], check=True)
        
        print("\n[SUCCESS] Pi is now uniquely identified via IoT Core.")
        print(f"AWS profiles '{args.campaign}-iot' and 'roadmap-iot' configured for automatic refresh.")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        # Clean up local sensitive files
        import shutil
        shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    main()
