# POLICY: frictionless-data-policy-enforcement
import socket
import json
from rich.console import Console
from rich.table import Table
from cocli.core.paths import paths

console = Console()

def audit_gossip() -> None:
    console.print("[bold cyan]--- Gossip Bridge Audit ---[/bold cyan]")
    
    # 1. Check for Sync Markers in Filesystem
    console.print("\n[bold]1. Checking Local Filesystem for Gossip-Synced Markers...[/bold]")
    campaign = "roadmap"
    q_dir = paths.campaign(campaign).queue("gm-list").completed / "results"
    
    gossip_markers = []
    if q_dir.exists():
        for json_file in q_dir.rglob("*.json"):
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)
                    if data.get("synced_via") == "gossip":
                        gossip_markers.append({
                            "path": json_file.relative_to(q_dir),
                            "node": data.get("remote_node"),
                            "time": data.get("timestamp")
                        })
            except Exception:
                continue

    if gossip_markers:
        table = Table(title="Recent Gossip Syncs")
        table.add_column("Task", style="magenta")
        table.add_column("Remote Node", style="green")
        table.add_column("Timestamp", style="dim")
        for m in gossip_markers[-10:]:
            table.add_row(str(m["path"]), m["node"], m["time"])
        console.print(table)
    else:
        console.print("[yellow]No gossip-synced markers found in local results.[/yellow]")

    # 2. Network Listener (Passive)
    console.print("\n[bold]2. Listening for Live Gossip (15s timeout)...[/bold]")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('0.0.0.0', 9999))
    except Exception as e:
        console.print(f"[red]Could not bind to port 9999: {e}[/red]")
        return

    sock.settimeout(15.0)
    received_count = 0
    
    try:
        while True:
            data, addr = sock.recvfrom(65535)
            msg = data.decode('utf-8', errors='replace')
            received_count += 1
            
            # Identify record type
            rtype = "WAL"
            if msg.startswith("H"):
                rtype = "Heartbeat"
            elif msg.startswith("C"):
                rtype = "Config"
            elif msg.startswith("Q"):
                rtype = "Queue"
            
            console.print(f"[green]Received {rtype} from {addr}:[/green] [dim]{msg.strip()[:100]}...[/dim]")
    except socket.timeout:
        if received_count == 0:
            console.print("[yellow]Timed out with no gossip received.[/yellow]")
        else:
            console.print(f"\n[bold green]Audit complete. Received {received_count} datagrams.[/bold green]")
    finally:
        sock.close()

def send_test_gossip(target_ip: str) -> None:
    """Sends a test QueueDatagram to a specific IP."""
    from cocli.models.wal.record import QueueDatagram
    from cocli.core.wal import get_node_id
    from datetime import datetime, UTC
    
    datagram = QueueDatagram(
        queue_name="test-queue",
        task_id="test-task",
        status="completed",
        timestamp=datetime.now(UTC).isoformat(),
        node_id=get_node_id()
    )
    
    msg = datagram.to_usv()
    console.print(f"[blue]Sending test datagram to {target_ip}:9999...[/blue]")
    console.print(f"[dim]Content: {msg.strip()}[/dim]")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(msg.encode('utf-8'), (target_ip, 9999))
    sock.close()
    console.print("[green]Sent.[/green]")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        send_test_gossip(sys.argv[1])
    else:
        audit_gossip()
