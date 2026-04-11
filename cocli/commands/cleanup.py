import os
import shutil
import typer
from pathlib import Path
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command(name="geo-precision")
def cleanup_geo_precision(
    campaign: str = typer.Option(..., "--campaign", "-c", help="Campaign name"),
    dry_run: bool = typer.Option(
        True, "--dry-run/--no-dry-run", help="Simulate changes without applying them"
    ),
) -> None:
    """Normalize geo-coordinate directory structures from 4-decimal to 1-decimal precision."""
    data_root = Path(f"data/campaigns/{campaign}/queues/gm-list/completed/results/")

    if not data_root.exists():
        console.print(f"[red]Error: Data directory not found: {data_root}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[cyan]Scanning {data_root} for high-precision geo-directories...[/cyan]"
    )
    if dry_run:
        console.print(
            "[yellow]Running in DRY-RUN mode. No changes will be made.[/yellow]"
        )

    cleaned_count = 0
    # Directory structure: shard/lat/lon/phrase.usv
    # We want to normalize lat and lon directories from X.XXXX to X.X

    # 1. Find all lat/lon directories
    for root, dirs, files in os.walk(data_root):
        for d in dirs:
            # Check if directory name looks like 4+ decimal places (e.g., 25.0400)
            if "." in d and len(d.split(".")[1]) > 1:
                # 2. Normalize to 1 decimal place
                try:
                    val = float(d)
                    normalized = f"{val:.1f}"
                except ValueError:
                    continue  # Not a coordinate directory

                if d == normalized:
                    continue  # Already normalized

                # 3. Rename/Merge logic
                old_path = Path(root) / d
                new_path = Path(root) / normalized

                if dry_run:
                    console.print(
                        f"[yellow]Would move: {old_path} -> {new_path}[/yellow]"
                    )
                    cleaned_count += 1
                else:
                    if new_path.exists():
                        # Merge logic: if normalized directory already exists, move contents inside
                        console.print(
                            f"[yellow]Merging {old_path} into existing {new_path}[/yellow]"
                        )
                        for item in os.listdir(old_path):
                            shutil.move(str(old_path / item), str(new_path / item))
                        os.rmdir(old_path)
                    else:
                        shutil.move(str(old_path), str(new_path))
                    cleaned_count += 1

    console.print(
        f"[green]Cleanup complete. {cleaned_count} directories processed.[/green]"
    )
