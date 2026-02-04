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
        subprocess.run(["scp", str(tmp_dir / "iot_config.json"), f"{args.user}@{args.host}:{remote_dir}/"], check=True)
        
        print("\n[SUCCESS] Pi is now uniquely identified via IoT Core.")
        print("It can now fetch short-lived STS tokens using its certificate.")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        # Clean up local sensitive files
        import shutil
        shutil.rmtree(tmp_dir)

if __name__ == "__main__":
    main()
