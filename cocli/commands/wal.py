"""Entity field journal compaction.

``cocli wal compact`` is the timer hook. Run it from cron on one machine.
It rewrites entity files from datagrams newer than those files, then uploads
the files it rewrote. A segment that still holds an older fact stays in
``wal/`` so read-time fold can keep using it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

import typer
from rich.console import Console

from cocli.application.entity_field_sync import compact_and_upload_entity_fields

logger = logging.getLogger(__name__)
console = Console()
app = typer.Typer(
    no_args_is_help=True,
    help="Fold the entity field journal into entity files.",
)


@app.command("compact")
def compact_entity_journal(
    campaign_name: Optional[str] = typer.Option(
        None, "--campaign", "-c", help="Campaign whose data bucket receives the rewritten files."
    ),
    no_upload: bool = typer.Option(
        False,
        "--no-upload",
        help="Rewrite local entity files and skip S3.",
    ),
) -> None:
    """Rewrite entity files from the field journal and upload the files that changed."""
    from cocli.core.config import get_campaign, load_campaign_config
    from cocli.core.reporting import get_boto3_session, get_data_bucket_name, get_s3_client

    upload: Optional[Callable[[Path, str], None]] = None
    if not no_upload:
        campaign_name = campaign_name or get_campaign()
        if not campaign_name:
            logger.error("wal compact needs a campaign so it can choose the data bucket")
            console.print("[bold red]No campaign specified.[/bold red]")
            raise typer.Exit(1)
        config = load_campaign_config(campaign_name)
        bucket = get_data_bucket_name(config, campaign_name)
        session = get_boto3_session(config)
        client = get_s3_client(session)
        upload = _s3_upload(client, bucket)

    did, n_rec, n_ent, keys = compact_and_upload_entity_fields(upload)
    logger.info(
        "wal compact did_work=%s records=%s entities=%s uploaded=%s",
        did,
        n_rec,
        n_ent,
        len(keys),
    )
    console.print(
        f"Compacted {n_rec} journal rows into {n_ent} entity files"
        + (f"; uploaded {len(keys)}." if not no_upload else ".")
    )


def _s3_upload(client: Any, bucket: str) -> Callable[[Path, str], None]:
    def upload(path: Path, key: str) -> None:
        client.upload_file(str(path), bucket, key)
        logger.info("uploaded entity file s3://%s/%s", bucket, key)

    return upload
