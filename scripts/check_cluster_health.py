import subprocess
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()

def run_ssh(host: str, command: str) -> str:
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", f"mstouffer@{host}", command],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return f"ERROR: {result.stderr.strip()}"
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {str(e)}"

def decode_throttled(status_str: str) -> list[str]:
    try:
        status = int(status_str.split('=')[1], 16)
    except (IndexError, ValueError):
        return ["Unknown Status"]

    flags = []
    if status & 0x1: 
        flags.append("[bold red]Undervoltage NOW[/bold red]")
    if status & 0x2: 
        flags.append("[bold red]Freq Capped NOW[/bold red]")
    if status & 0x4: 
        flags.append("[bold yellow]Throttled NOW[/bold yellow]")
    if status & 0x8: 
        flags.append("[bold yellow]Temp Limit NOW[/bold yellow]")
    if status & 0x10000: 
        flags.append("[dim]Undervoltage (History)[/dim]")
    if status & 0x20000: 
        flags.append("[dim]Freq Capped (History)[/dim]")
    if status & 0x40000: 
        flags.append("[dim]Throttled (History)[/dim]")
    if status & 0x80000: 
        flags.append("[dim]Temp Limit (History)[/dim]")
    
    if not flags:
        return ["[green]✓ Healthy[/green]"]
    return flags

def check_host(host: str, name: str) -> None:
    console.print(f"\n[bold blue]─── {name} ({host}) ───[/bold blue]")
    
    # Run combined command to save SSH overhead
    cmd = "uptime; vcgencmd measure_volts; vcgencmd get_throttled; docker ps --format '{{.Names}}|{{.Status}}'"
    output = run_ssh(host, cmd)
    
    if "ERROR" in output:
        console.print(f"[red]Offline or unreachable: {output}[/red]")
        return

    lines = output.split("\n")
    uptime = lines[0] if len(lines) > 0 else "Unknown"
    volts = lines[1] if len(lines) > 1 else "Unknown"
    throttled = lines[2] if len(lines) > 2 else "Unknown"
    containers = lines[3:] if len(lines) > 3 else []

    # Format Table
    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    table.add_row("Uptime", uptime)
    table.add_row("Voltage", volts.replace("volt=", ""))
    
    health_flags = decode_throttled(throttled)
    table.add_row("Health", ", ".join(health_flags))

    console.print(table)

    if containers:
        cont_table = Table(title="Active Containers", box=box.ROUNDED, title_style="dim")
        cont_table.add_column("Container", style="bold white")
        cont_table.add_column("Status", style="green")
        for c in containers:
            if "|" in c:
                c_name, c_status = c.split("|")
                cont_table.add_row(c_name, c_status)
        console.print(cont_table)
    else:
        console.print("[dim]No active cocli containers.[/dim]")

def main() -> None:
    from cocli.core.config import get_campaign, load_campaign_config
    campaign_name = get_campaign() or "turboship"
    config = load_campaign_config(campaign_name)
    
    scaling = config.get("prospecting", {}).get("scaling", {})
    cluster_config = config.get("cluster", {})
    
    nodes = cluster_config.get("nodes", [])
    if not nodes:
        for host_key in scaling.keys():
            if host_key == "fargate":
                continue
            host = host_key if "." in host_key else f"{host_key}.pi"
            nodes.append({"host": host, "label": host_key.capitalize()})

    console.print(Panel(f"[bold green]Cluster Health Overview: {campaign_name}[/bold green]", expand=False))
    
    if not nodes:
        console.print("[yellow]No worker nodes configured for this campaign.[/yellow]")
        return

    for node in nodes:
        check_host(node["host"], node.get("label", node["host"]))

if __name__ == "__main__":
    main()
