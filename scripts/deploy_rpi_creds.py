import argparse
import configparser
import subprocess
import sys
from pathlib import Path

import boto3

def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy AWS credentials for a specific profile to a Raspberry Pi.")
    parser.add_argument("--profile", help="Local AWS profile name to extract.")
    parser.add_argument("--host", required=True, help="RPi hostname or IP (e.g., octoprint.local).")
    parser.add_argument("--user", default="mstouffer", help="SSH user for the RPi.")
    parser.add_argument("--campaign", required=True, help="Campaign slug to use as the profile name and secret ID.")
    parser.add_argument("--from-secret", action="store_true", help="Fetch credentials from AWS Secrets Manager instead of local profile.")
    
    args = parser.parse_args()

    if not args.from_secret and not args.profile:
        print("Error: Either --profile or --from-secret must be specified.")
        sys.exit(1)
    
    # Use boto3 to get credentials
    try:
        if args.from_secret:
            print(f"Fetching credentials from Secrets Manager for campaign '{args.campaign}'...")
            # Use default session to fetch the secret
            sm_client = boto3.client("secretsmanager")
            secret_id = f"cocli/campaign/{args.campaign}"
            response = sm_client.get_secret_value(SecretId=secret_id)
            import json
            secret_data = json.loads(response["SecretString"])
            
            access_key = secret_data["aws_access_key_id"]
            secret_key = secret_data["aws_secret_access_key"]
            region = secret_data.get("region", "us-east-1")
            token = secret_data.get("aws_session_token")
        else:
            session = boto3.Session(profile_name=args.profile)
            raw_creds = session.get_credentials()
            if not raw_creds:
                print(f"Error: No credentials found for profile '{args.profile}'")
                sys.exit(1)
            creds = raw_creds.get_frozen_credentials()
            access_key = creds.access_key
            secret_key = creds.secret_key
            token = creds.token
            region = session.region_name or "us-east-1"
            
    except Exception as e:
        print(f"Error fetching credentials: {e}")
        sys.exit(1)
        
    target_profile = args.campaign
    print(f"Targeting profile '{target_profile}' on {args.host}")

    # Create temporary credentials content
    new_creds = configparser.ConfigParser()
    new_creds[target_profile] = {
        "aws_access_key_id": str(access_key),
        "aws_secret_access_key": str(secret_key)
    }
    if token:
        new_creds[target_profile]["aws_session_token"] = str(token)
    
    # Mirror to [default]
    new_creds["default"] = dict(new_creds[target_profile])
    
    new_config = configparser.ConfigParser()
    target_config_section = f"profile {target_profile}"
    new_config[target_config_section] = {
        "region": region,
        "output": "json"
    }
    # Mirror to [default]
    new_config["default"] = {
        "region": region,
        "output": "json"
    }

    # Write to temporary files
    tmp_dir = Path("/tmp/cocli_rpi_aws")
    tmp_dir.mkdir(exist_ok=True)
    
    tmp_creds = tmp_dir / "credentials"
    tmp_config = tmp_dir / "config"
    
    with open(tmp_creds, "w") as f:
        new_creds.write(f)
    
    with open(tmp_config, "w") as f:
        new_config.write(f)
        
    print(f"Deploying profile '{target_profile}' to {args.user}@{args.host}...")
    
    try:
        # Create .aws directory on Pi
        subprocess.run(["ssh", f"{args.user}@{args.host}", "mkdir -p ~/.aws"], check=True)
        
        # Merge logic: Append to existing files on Pi rather than overwriting
        # (This is safer for multi-campaign workers)
        # For simplicity in this script, we'll just SCP and let the user know it overwrites for now,
        # OR we could cat them. Let's try to be smart.
        
        # 1. SCP the new snippets
        subprocess.run(["scp", str(tmp_creds), f"{args.user}@{args.host}:~/.aws/credentials.new"], check=True)
        subprocess.run(["scp", str(tmp_config), f"{args.user}@{args.host}:~/.aws/config.new"], check=True)
        
        # 2. Run a remote script to merge them
        merge_cmd = (
            "python3 -c '"
            "import configparser, os; "
            "cp = configparser.ConfigParser(); cp.read([os.path.expanduser(\"~/.aws/credentials\"), os.path.expanduser(\"~/.aws/credentials.new\")]); "
            "f = open(os.path.expanduser(\"~/.aws/credentials\"), \"w\"); cp.write(f); f.close(); "
            "cp = configparser.ConfigParser(); cp.read([os.path.expanduser(\"~/.aws/config\"), os.path.expanduser(\"~/.aws/config.new\")]); "
            "f = open(os.path.expanduser(\"~/.aws/config\"), \"w\"); cp.write(f); f.close(); "
            "os.remove(os.path.expanduser(\"~/.aws/credentials.new\")); "
            "os.remove(os.path.expanduser(\"~/.aws/config.new\")); "
            "'"
        )
        subprocess.run(["ssh", f"{args.user}@{args.host}", merge_cmd], check=True)
        
        print(f"Success! Profile '{target_profile}' added/updated on {args.host}.")
    except subprocess.CalledProcessError as e:
        print(f"Error during deployment: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        if tmp_creds.exists():
            tmp_creds.unlink()
        if tmp_config.exists():
            tmp_config.unlink()
        if tmp_dir.exists():
            tmp_dir.rmdir()

if __name__ == "__main__":
    main()
