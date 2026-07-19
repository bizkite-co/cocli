"""Thin cocli adapter over the stations library inspector / transform surface.

Normative implementation lives in the stations package (decision 0005/0008).
This module only resolves campaign paths and invokes stations.inspect.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from cocli.core.paths import paths

logger = logging.getLogger(__name__)

app = typer.Typer(
    no_args_is_help=True,
    help="Stations substrate tools (read-only inspect via the stations package).",
)


@app.command("inspect")
def inspect_stations(
    queue: Optional[str] = typer.Argument(
        None,
        help="Queue name under the campaign (e.g. gm-list, to-call). "
        "Omit to inspect all queues for the campaign.",
    ),
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        help="Explicit station root (overrides campaign/queue resolution).",
    ),
    plain: bool = typer.Option(False, "--plain", help="Plain text (no Rich)."),
    no_leases: bool = typer.Option(
        False, "--no-leases", help="Skip lease JSON content parsing."
    ),
) -> None:
    """Render a campaign station root via stations inspect (read-only)."""
    if path is not None:
        root = path.expanduser().resolve()
    else:
        from cocli.core.config import get_campaign

        campaign = get_campaign()
        if not campaign:
            logger.error(
                "no active campaign; pass --campaign or set one with cocli context"
            )
            raise typer.Exit(2)
        campaign_paths = paths.campaign(campaign)
        if queue:
            root = (campaign_paths.queues / queue).resolve()
        else:
            root = campaign_paths.queues

    if not root.exists():
        logger.error("station root does not exist: %s", root)
        raise typer.Exit(2)

    try:
        from stations.inspect import inspect_and_render
    except ImportError as exc:
        logger.error(
            "stations package too old or missing inspect (%s). "
            "Bump with: uv lock --upgrade-package stations "
            "(requires stations >= 0.2.0 / decision 0008).",
            exc,
        )
        raise typer.Exit(1) from exc

    logger.info("inspecting stations root: %s", root)
    inspect_and_render(
        str(root),
        parse_leases=not no_leases,
        plain=plain,
    )
