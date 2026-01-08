import subprocess
import tomli
from pathlib import Path
import sys

def run_ssh(host: str, command: str) -> str:
    print(f"[{host}] Running: {command}")
    result = subprocess.run(
        ["ssh", f"mstouffer@{host}", command],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"[{host}] ERROR: {result.stderr}")
    return result.stdout.strip()

def main() -> None:
    config_path = Path.home() / ".config" / "cocli" / "cocli_config.toml"
    if not config_path.exists():
        print("Config file not found.")
        sys.exit(1)

    with open(config_path, "rb") as f:
        config = tomli.load(f)

    nodes = config.get("cluster", {}).get("nodes", {})

    for hostname, info in nodes.items():
        ip = info.get("ip")
        if not ip:
            continue
        
        print(f"--- Configuring {hostname} to IP {ip} ---")
        
        # Check if host is reachable via .local first
        local_host = f"{hostname}.local"
        
        # Command to set static IP using nmcli (Assuming Ethernet 'Wired connection 1')
        setup_cmd = f"""
        CONN=$(nmcli -g NAME,TYPE con show --active | grep ethernet | cut -d: -f1 | head -n 1)
        if [ -z "$CONN" ]; then
            CONN=$(nmcli -g NAME,TYPE con show | grep ethernet | cut -d: -f1 | head -n 1)
        fi
        if [ -n "$CONN" ]; then
            echo "Updating connection: $CONN"
            sudo nmcli con mod "$CONN" ipv4.addresses {ip}/24 ipv4.gateway 10.0.0.1 ipv4.method manual ipv4.dns "8.8.8.8,8.8.4.4"
            sudo nmcli con up "$CONN"
        else
            echo "No ethernet connection found."
        fi
        """
        run_ssh(local_host, setup_cmd)

if __name__ == "__main__":
    main()