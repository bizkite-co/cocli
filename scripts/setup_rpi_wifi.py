import argparse
import subprocess
import sys
from rich.console import Console
from cocli.utils.op_utils import get_op_item

console = Console()

def main() -> None:
    parser = argparse.ArgumentParser(description="Setup WiFi on a Raspberry Pi using 1Password credentials.")
    parser.add_argument("host", help="Hostname or IP of the Raspberry Pi (e.g., coclipi.local)")
    parser.add_argument("--user", default="mstouffer", help="SSH user for the Pi.")
    args = parser.parse_args()

    item_id = "bs3pts5vnyagrjnypklhv2t7mi"
    item = get_op_item(item_id)
    if not item:
        console.print("[bold red]Error:[/bold red] Could not retrieve 1Password item. Please ensure you are signed in or have a valid service account.")
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
