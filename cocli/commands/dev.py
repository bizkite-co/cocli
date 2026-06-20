"""
Development utilities for testing and debugging pipeline stages.
"""

import typer
import logging
from typing import Optional, List, Annotated
from pathlib import Path
from rich.console import Console
from rich.table import Table

from cocli.core.paths import paths
from cocli.core.config import get_campaign, get_campaign_dir
from cocli.models.campaigns.mission import MissionTask
from cocli.models.campaigns.tiles import TileRecord

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(no_args_is_help=True)


def validate_usv_against_schema(usv_path: Path, model_class) -> tuple[bool, int, List[str]]:
    """
    Validate a USV file against a Pydantic model schema.
    Returns: (is_valid, record_count, errors)
    """
    errors = []
    record_count = 0

    if not usv_path.exists():
        return False, 0, [f"File not found: {usv_path}"]

    try:
        with open(usv_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                record_count += 1
                if line.strip():
                    try:
                        model_class.from_usv(line)
                    except Exception as e:
                        errors.append(f"Line {line_num}: {str(e)}")
                        if len(errors) > 5:  # Limit error output
                            errors.append("... (truncated)")
                            break
    except Exception as e:
        return False, 0, [f"Failed to read file: {str(e)}"]

    return len(errors) == 0, record_count, errors


@app.command(name="run-discovery-pipeline")
def run_discovery_pipeline(
    campaign_name: Annotated[
        Optional[str],
        typer.Argument(help="Campaign name. Defaults to current context."),
    ] = None,
    stage: Annotated[
        Optional[int],
        typer.Option("--stage", "-s", help="Run only a specific stage (1-4). Default: all stages."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without writing files."),
    ] = False,
) -> None:
    """
    Run the discovery-gen pipeline end-to-end with incremental validation.

    Stages:
      1. Generate tiles from target locations
      2. Expand tiles × phrases → mission.usv
      3. Filter frontier by ScrapeIndex TTL
      4. Create batches from frontier

    Each stage validates output against Frictionless Data schema.

    Example:
      cocli dev run-discovery-pipeline roadmap --stage=1  # Test Stage 1 only
      cocli dev run-discovery-pipeline roadmap             # Run all stages
    """
    if campaign_name is None:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found: {campaign_name}[/red]")
        raise typer.Exit(1)

    dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
    console.print(f"[bold blue]Discovery-Gen Pipeline Test[/bold blue]")
    console.print(f"  Campaign: {campaign_name}")
    console.print(f"  Queue: {dg_queue.path}\n")

    # ===== STAGE 1: Generate Tiles =====
    if stage is None or stage == 1:
        console.print("[bold cyan]Stage 1: Generate Tiles[/bold cyan]")
        tiles_path = dg_queue.path / "tiles" / "tiles.usv"
        if tiles_path.exists():
            is_valid, count, errors = validate_usv_against_schema(tiles_path, TileRecord)
            status = "[green]✓[/green]" if is_valid else "[red]✗[/red]"
            console.print(f"  {status} tiles/tiles.usv: {count} tiles")
            if errors:
                for error in errors[:3]:
                    console.print(f"    [red]{error}[/red]")
        else:
            console.print(f"  [yellow]⚠[/yellow] tiles/tiles.usv not found: {tiles_path}")
        console.print()

    # ===== STAGE 2: Expand Phrases (Mission) =====
    if stage is None or stage == 2:
        console.print("[bold cyan]Stage 2: Expand Phrases → Mission[/bold cyan]")
        mission_path = dg_queue.master
        if mission_path.exists():
            is_valid, count, errors = validate_usv_against_schema(mission_path, MissionTask)
            status = "[green]✓[/green]" if is_valid else "[red]✗[/red]"
            console.print(f"  {status} mission.usv: {count} records")
            if errors:
                for error in errors[:3]:
                    console.print(f"    [red]{error}[/red]")
                if len(errors) > 3:
                    console.print(f"    [dim]... and {len(errors) - 3} more[/dim]")
        else:
            console.print(f"  [yellow]⚠[/yellow] mission.usv not found: {mission_path}")
        console.print()

    # ===== STAGE 3: Filter Frontier =====
    if stage is None or stage == 3:
        console.print("[bold cyan]Stage 3: Filter Frontier (ScrapeIndex TTL)[/bold cyan]")
        frontier_path = dg_queue.pending / "frontier.usv"
        if frontier_path.exists():
            is_valid, count, errors = validate_usv_against_schema(frontier_path, MissionTask)
            status = "[green]✓[/green]" if is_valid else "[red]✗[/red]"
            console.print(f"  {status} frontier.usv: {count} pending tasks")
            if errors:
                for error in errors[:3]:
                    console.print(f"    [red]{error}[/red]")
        else:
            console.print(f"  [yellow]⚠[/yellow] frontier.usv not found: {frontier_path}")
        console.print()

    # ===== STAGE 4: Create Batches =====
    if stage is None or stage == 4:
        console.print("[bold cyan]Stage 4: Create Batches[/bold cyan]")
        batch_dir = dg_queue.pending / "batches"
        if batch_dir.exists():
            batch_files = list(batch_dir.glob("*.usv"))
            console.print(f"  Found {len(batch_files)} batch files:")
            for batch_file in sorted(batch_files)[:5]:
                is_valid, count, _ = validate_usv_against_schema(batch_file, MissionTask)
                status = "[green]✓[/green]" if is_valid else "[red]✗[/red]"
                console.print(f"    {status} {batch_file.name}: {count} items")
            if len(batch_files) > 5:
                console.print(f"    [dim]... and {len(batch_files) - 5} more[/dim]")
        else:
            console.print(f"  [yellow]⚠[/yellow] No batches directory yet")
        console.print()

    # ===== Summary =====
    console.print("[bold green]Pipeline validation complete![/bold green]")


@app.command(name="run-discovery-gen-stages")
def run_discovery_gen_stages(
    campaign_name: Annotated[
        Optional[str],
        typer.Argument(help="Campaign name. Defaults to current context."),
    ] = None,
    stage: Annotated[
        Optional[int],
        typer.Option("--stage", "-s", help="Run only a specific stage (1-3). Default: all stages."),
    ] = None,
    skip_validation: Annotated[
        bool,
        typer.Option("--skip-validation", help="Skip schema validation after running."),
    ] = False,
) -> None:
    """
    Run the extracted discovery-gen pipeline stages end-to-end.

    This orchestrates the decomposed stage functions:
      Stage 1: generate_tiles() → tiles.usv
      Stage 2: expand_phrases() → mission.usv
      Stage 3: filter_frontier() → pending/frontier.usv

    Each stage validates its output against Frictionless Data schema.
    Schema versioning (cocli:schema_hash) protects against conflicts.

    Example:
      cocli dev run-discovery-gen-stages turboship               # Run all stages
      cocli dev run-discovery-gen-stages turboship --stage=1     # Run Stage 1 only
      cocli dev run-discovery-gen-stages turboship --stage=2     # Run Stage 2 only
    """
    from cocli.commands.campaign.discovery_gen_stages import (
        generate_tiles,
        expand_phrases,
        filter_frontier,
    )

    if campaign_name is None:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found: {campaign_name}[/red]")
        raise typer.Exit(1)

    dg_queue = paths.campaign(campaign_name).queue("discovery-gen")
    console.print(f"[bold blue]Discovery-Gen Pipeline Execution[/bold blue]")
    console.print(f"  Campaign: {campaign_name}")
    console.print(f"  Queue: {dg_queue.path}\n")

    artifacts_created = []

    try:
        # ===== STAGE 1 =====
        if stage is None or stage == 1:
            console.print("[bold cyan]Stage 1: Generate Tiles[/bold cyan]")
            tiles = generate_tiles(campaign_name, save_output=True)
            console.print(f"  ✓ Generated {len(tiles)} tiles")
            artifacts_created.append(f"tiles.usv ({len(tiles)} records)")
            artifacts_created.append("tiles datapackage.json")
            console.print()

        # ===== STAGE 2 =====
        if stage is None or stage == 2:
            console.print("[bold cyan]Stage 2: Expand Phrases → Mission[/bold cyan]")
            mission = expand_phrases(campaign_name, save_output=True)
            console.print(f"  ✓ Generated {len(mission)} mission tasks")
            artifacts_created.append(f"mission.usv ({len(mission)} records)")
            artifacts_created.append("mission datapackage.json")
            console.print()

        # ===== STAGE 3 =====
        if stage is None or stage == 3:
            console.print("[bold cyan]Stage 3: Filter Frontier (ScrapeIndex TTL)[/bold cyan]")
            frontier = filter_frontier(campaign_name, save_output=True)
            console.print(f"  ✓ Filtered {len(frontier)} pending tasks")
            artifacts_created.append(f"pending/frontier.usv ({len(frontier)} records)")
            artifacts_created.append("pending/frontier datapackage.json")
            console.print()

        # ===== Validation =====
        if not skip_validation:
            console.print("[bold cyan]Validation[/bold cyan]")
            run_discovery_pipeline(campaign_name, stage, dry_run=False)

        # ===== Summary =====
        console.print("[bold green]Pipeline execution complete![/bold green]")
        console.print(f"\nArtifacts created ({len(artifacts_created)}):")
        for artifact in artifacts_created:
            console.print(f"  ✓ {artifact}")

    except Exception as e:
        console.print(f"[red]Error during pipeline execution: {e}[/red]")
        logger.exception("Pipeline execution failed")
        raise typer.Exit(1)
