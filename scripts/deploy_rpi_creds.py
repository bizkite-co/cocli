import argparse
import configparser
import subprocess
import sys
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy AWS credentials for a specific profile to a Raspberry Pi.")
    parser.add_argument("--profile", required=True, help="Local AWS profile name to extract.")
    parser.add_argument("--host", required=True, help="RPi hostname or IP (e.g., octoprint.local).")
    parser.add_argument("--user", default="mstouffer", help="SSH user for the RPi.")
    
    args = parser.parse_args()
    
    home = Path.home()
    aws_creds_path = home / ".aws" / "credentials"
    aws_config_path = home / ".aws" / "config"
    
    if not aws_creds_path.exists():
        print(f"Error: {aws_creds_path} not found.")
        sys.exit(1)
        
    creds = configparser.ConfigParser()
    creds.read(aws_creds_path)
    
    if args.profile not in creds:
        print(f"Error: Profile '{args.profile}' not found in {aws_creds_path}.")
        sys.exit(1)
        
    # Create temporary credentials content
    new_creds = configparser.ConfigParser()
    new_creds[args.profile] = dict(creds[args.profile])
    # Also set as default for convenience on the Pi
    new_creds["default"] = dict(creds[args.profile])
    
    # Extract config (especially region)
    new_config = configparser.ConfigParser()
    if aws_config_path.exists():
        config = configparser.ConfigParser()
        config.read(aws_config_path)
        profile_section = f"profile {args.profile}"
        if profile_section in config:
            new_config[args.profile] = dict(config[profile_section])
            new_config["default"] = dict(config[profile_section])
        elif args.profile in config:
             new_config[args.profile] = dict(config[args.profile])
             new_config["default"] = dict(config[args.profile])

    # Write to temporary files
    tmp_dir = Path("/tmp/cocli_rpi_aws")
    tmp_dir.mkdir(exist_ok=True)
    
    tmp_creds = tmp_dir / "credentials"
    tmp_config = tmp_dir / "config"
    
    with open(tmp_creds, "w") as f:
        new_creds.write(f)
    
    with open(tmp_config, "w") as f:
        new_config.write(f)
        
    print(f"Deploying profile '{args.profile}' to {args.user}@{args.host}...")
    
    try:
        # Create .aws directory on Pi
        subprocess.run(["ssh", f"{args.user}@{args.host}", "mkdir -p ~/.aws"], check=True)
        
        # SCP files
        subprocess.run(["scp", str(tmp_creds), f"{args.user}@{args.host}:~/.aws/credentials"], check=True)
        subprocess.run(["scp", str(tmp_config), f"{args.user}@{args.host}:~/.aws/config"], check=True)
        
        print("Success! Credentials deployed.")
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
