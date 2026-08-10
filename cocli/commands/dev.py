"""
Development utilities for testing and debugging pipeline stages.
"""

import typer
import logging
from typing import Optional, List, Annotated, Any
from pathlib import Path
from rich.console import Console

from cocli.core.paths import paths
from cocli.core.config import get_campaign, get_campaign_dir
from cocli.core.frictionless_validation import validate_stage_outputs

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(no_args_is_help=True)


def validate_usv_against_schema(usv_path: Path, model_class: type[Any]) -> tuple[bool, int, List[str]]:
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
    console.print("[bold blue]Discovery-Gen Pipeline Validation[/bold blue]")
    console.print(f"  Campaign: {campaign_name}")
    console.print(f"  Queue: {dg_queue.path}\n")

    # Use Frictionless validation utility
    results = validate_stage_outputs(campaign_name, dg_queue, stage)

    for stage_num in sorted(results.keys()):
        result = results[stage_num]
        status = "[green]✓[/green]" if result["valid"] else "[red]✗[/red]"
        console.print(f"{status} [bold cyan]Stage {stage_num}: {result['name']}[/bold cyan]")

        # Check if file exists
        file_path = Path(result["file"])
        if not file_path.exists():
            console.print(f"    [yellow]⚠[/yellow] File not found: {file_path.name}")
            console.print()
            continue

        # Show record count
        console.print(f"    Records: {result['record_count']}")

        # Show schema path
        schema_path = Path(result["schema"])
        if schema_path.exists():
            console.print(f"    Schema: ✓ {schema_path.name}")
        else:
            console.print(f"    Schema: [yellow]⚠[/yellow] {schema_path.name} not found")

        # Show errors if any
        if result["errors"]:
            console.print(f"    [red]Errors ({len(result['errors'])}):[/red]")
            for error in result["errors"][:3]:
                console.print(f"      {error}")
            if len(result["errors"]) > 3:
                console.print(f"      [dim]... and {len(result['errors']) - 3} more[/dim]")
        console.print()

    # ===== Summary =====
    all_valid = all(r["valid"] for r in results.values())
    if all_valid:
        console.print("[bold green]✓ All stages validated successfully![/bold green]")
    else:
        console.print("[bold yellow]⚠ Some stages have validation errors[/bold yellow]")


@app.command(name="run-discovery-gen-stages")
def run_discovery_gen_stages(
    campaign_name: Annotated[
        Optional[str],
        typer.Argument(help="Campaign name. Defaults to current context."),
    ] = None,
    stage: Annotated[
        Optional[int],
        typer.Option("--stage", "-s", help="Run only a specific stage (1, 2, or 4). Default: all stages."),
    ] = None,
    skip_validation: Annotated[
        bool,
        typer.Option("--skip-validation", help="Skip schema validation after running."),
    ] = False,
) -> None:
    """
    Execute the discovery-gen pipeline: locations → tiles → mission → map-tile.

    This runs the refactored decomposed stages end-to-end with validation:
      Stage 1: generate_tiles()
        Input: target_locations from config
        Output: tiles/tiles.usv (geographic grid)

      Stage 2: expand_phrases()
        Input: tiles from Stage 1
        Output: mission.usv (tiles × search phrases)

      Stage 4: populate_tile_queue()
        Input: mission.usv (all tasks, no TTL filtering)
        Output: map-tile/pending/{shard}/{lat}/{lon}/{tile_id}.usv (manifest)

      (Stage 3, filter_frontier(), was removed from this pipeline 2026-08-08:
      Stage 4 always read the full mission.usv directly and never consumed
      frontier.usv, so generating it here was dead work. filter_frontier()
      itself still exists for campaign prepare-mission / create-batch, which
      have their own independent uses for the ScrapeIndex-TTL-filtered
      frontier - only this pipeline's redundant call was removed.)

    Each stage auto-validates output against Frictionless Data schema.
    Schema versioning (cocli:schema_hash) ensures consistency.

    USAGE:
      # Full pipeline (stages 1, 2, 4):
      cocli dev run-discovery-gen-stages turboship

      # Single stage (useful for debugging):
      cocli dev run-discovery-gen-stages turboship --stage=1

      # Then check results without re-running:
      cocli dev run-discovery-pipeline turboship
    """
    from cocli.commands.campaign.discovery_gen_stages import (
        generate_tiles,
        expand_phrases,
        populate_tile_queue,
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
    console.print("[bold blue]Discovery-Gen Pipeline Execution[/bold blue]")
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

        # ===== STAGE 4 =====
        if stage is None or stage == 4:
            console.print("[bold cyan]Stage 4: Populate Map-Tile Manifest[/bold cyan]")
            tiles_count = populate_tile_queue(campaign_name, save_output=True)
            console.print(f"  ✓ Created {tiles_count} sharded tile files")
            artifacts_created.append(f"map-tile/pending/ ({tiles_count} sharded files)")
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


@app.command(name="process-map-tile")
def process_map_tile_cmd(
    campaign_name: Annotated[
        Optional[str],
        typer.Argument(help="Campaign name. Defaults to current context."),
    ] = None,
    max_tiles: Annotated[
        Optional[int],
        typer.Option("--max", "-m", help="Maximum number of tiles to process."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview what would be processed without writing files."),
    ] = False,
) -> None:
    """
    Process map-tile/pending/ → discovery-gen/completed/.

    Reads tiles from map-tile/pending/, converts each tile's phrases to
    individual ScrapeTask work items, writes them to discovery-gen/completed/
    (discovery-gen's own permanent, per-phrase-tile output - a separate copy
    step handles getting these into gm-list/pending/), then moves processed
    tiles to map-tile/completed/. map-tile has no processing phase - use
    --max to bound how many tiles a single run processes.

    USAGE:
      # Process all tiles in pending/:
      cocli dev process-map-tile turboship

      # Process only 10 tiles (for testing, or to batch a run):
      cocli dev process-map-tile turboship --max 10

      # Preview without writing:
      cocli dev process-map-tile turboship --dry-run
    """
    from cocli.services.tile_queue_processor import process_tile_queue

    if campaign_name is None:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        console.print(f"[red]Campaign directory not found: {campaign_name}[/red]")
        raise typer.Exit(1)

    try:
        console.print("[bold blue]Map-Tile Processor[/bold blue]")
        console.print(f"  Campaign: {campaign_name}")
        if dry_run:
            console.print("  Mode: [yellow]DRY RUN[/yellow]")
        if max_tiles:
            console.print(f"  Max tiles: {max_tiles}")
        console.print()

        metrics = process_tile_queue(campaign_name, max_tiles=max_tiles, dry_run=dry_run)

        console.print("[bold green]Processing complete![/bold green]")
        console.print(f"  Tiles processed: {metrics['tiles_processed']}")
        console.print(f"  ScrapeTask records created: {metrics['scrape_tasks_created']}")
        if metrics["errors"] > 0:
            console.print(f"  [yellow]Errors: {metrics['errors']}[/yellow]")

    except Exception as e:
        console.print(f"[red]Error during map-tile processing: {e}[/red]")
        logger.exception("Map-tile processing failed")
        raise typer.Exit(1)
