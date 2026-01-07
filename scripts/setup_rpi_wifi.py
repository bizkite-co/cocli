import argparse
import json
import subprocess
import sys
from rich.console import Console

console = Console()

def check_op_signin():
    """Checks if the user is signed in to 1Password CLI."""
    try:
        subprocess.run(["op", "whoami"], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False

def get_op_item(item_id):
    """Fetches item details from 1Password."""
    try:
        result = subprocess.run(["op", "item", "get", item_id, "--format", "json"], check=True, capture_output=True, text=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error fetching 1Password item:[/bold red] {e.stderr}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Setup WiFi on a Raspberry Pi using 1Password credentials.")
    parser.add_argument("host", help="Hostname or IP of the Raspberry Pi (e.g., coclipi.local)")
    parser.add_argument("--user", default="mstouffer", help="SSH user for the Pi.")
    args = parser.parse_args()

    if not check_op_signin():
        console.print("[bold red]Error:[/bold red] You are not signed in to 1Password. Please run 'op signin' first.")
        sys.exit(1)

    item_id = "bs3pts5vnyagrjnypklhv2t7mi"
    item = get_op_item(item_id)
    if not item:
        sys.exit(1)

    # Extract fields
    fields = item.get("fields", [])
    password = next((f.get("value") for f in fields if f.get("label") == "wireless network password"), None)
    ssid = next((f.get("value") for f in fields if f.get("label") == "authentication"), None)
    # The user also mentioned 2.4netword, but ssid (authentication) is likely the primary one
    
    if not ssid or not password:
        console.print("[bold red]Error:[/bold red] Could not find 'authentication' (SSID) or 'wireless network password' in 1Password item.")
        sys.exit(1)

    console.print(f"[bold green]Found credentials for SSID:[/bold green] {ssid}")
    console.print(f"[dim]Attempting to connect {args.host} to WiFi...[/dim]")

    # Command to connect via nmcli
    # Use sudo nmcli dev wifi connect 'SSID' password 'PASSWORD'
    cmd = f"sudo nmcli dev wifi connect '{ssid}' password '{password}'"
    
    try:
        subprocess.run(["ssh", f"{args.user}@{args.host}", cmd], check=True)
        console.print(f"[bold green]Success![/bold green] {args.host} is now connecting to {ssid}.")
        console.print("[yellow]Note:[/yellow] You may now unplug the Ethernet cable. The Pi should remain reachable via its hostname.")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Failed to connect WiFi on Pi:[/bold red] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
