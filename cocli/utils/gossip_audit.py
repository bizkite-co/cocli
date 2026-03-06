# POLICY: frictionless-data-policy-enforcement
import socket
import json
import time
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from collections import deque
from typing import Deque, Dict, Any
from cocli.core.paths import paths

console = Console()

def audit_gossip(timeout_seconds: float = 60.0) -> None:
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
        table = Table(title="Recent Gossip Syncs (Disk)")
        table.add_column("Task", style="magenta")
        table.add_column("Remote Node", style="green")
        table.add_column("Timestamp", style="dim")
        # Sort by time if possible, otherwise just show last 10
        for m in gossip_markers[-10:]:
            table.add_row(str(m["path"]), m["node"], m["time"])
        console.print(table)
    else:
        console.print("[yellow]No gossip-synced markers found in local results.[/yellow]")

    # 2. Network Listener
    console.print(f"\n[bold]2. Listening for Live Gossip ({timeout_seconds}s timeout)...[/bold]")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('0.0.0.0', 9999))
    except Exception as e:
        console.print(f"[red]Could not bind to port 9999: {e}[/red]")
        return

    sock.settimeout(1.0) # Short timeout for loop responsiveness
    
    stats = {
        "Heartbeat": 0,
        "Config": 0,
        "Queue": 0,
        "WAL": 0,
        "Total": 0
    }
    
    recent_samples: Deque[Dict[str, Any]] = deque(maxlen=20)
    start_time = time.time()
    
    def generate_report_table() -> Table:
        table = Table(title=f"Gossip Traffic (Elapsed: {int(time.time() - start_time)}s / {timeout_seconds}s)")
        table.add_column("Type", style="cyan")
        table.add_column("Count", justify="right")
        
        for k, v in stats.items():
            table.add_row(k, str(v))
        
        return table

    def generate_samples_table() -> Table:
        table = Table(title="Recent Samples (Last 20)")
        table.add_column("Time", style="dim")
        table.add_column("Type")
        table.add_column("From")
        table.add_column("Payload", style="dim", overflow="fold")
        
        for s in reversed(list(recent_samples)):
            table.add_row(s["time"], s["type"], s["addr"], s["payload"])
        
        return table

    with Live(generate_report_table(), refresh_per_second=2) as live:
        try:
            while (time.time() - start_time) < timeout_seconds:
                try:
                    data, addr = sock.recvfrom(65535)
                    msg = data.decode('utf-8', errors='replace')
                    
                    stats["Total"] += 1
                    rtype = "WAL"
                    if msg.startswith("H"):
                        rtype = "Heartbeat"
                    elif msg.startswith("C"):
                        rtype = "Config"
                    elif msg.startswith("Q"):
                        rtype = "Queue"
                    
                    stats[rtype] += 1
                    
                    ts = datetime.now().strftime("%H:%M:%S")
                    recent_samples.append({
                        "time": ts,
                        "type": rtype,
                        "addr": f"{addr[0]}:{addr[1]}",
                        "payload": msg.strip()[:60]
                    })
                    
                    # Update display
                    group = Table.grid(padding=1)
                    group.add_row(generate_report_table())
                    group.add_row(generate_samples_table())
                    live.update(group)
                    
                except socket.timeout:
                    # Just keep looping to check time
                    live.update(generate_report_table())
                    continue
        except KeyboardInterrupt:
            console.print("\n[yellow]Audit interrupted by user.[/yellow]")
        finally:
            sock.close()

    console.print("\n[bold green]Audit complete.[/bold green]")

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
