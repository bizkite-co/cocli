"""CLI wrapper for cocli.application.lead_export_service.export_enriched_emails.

Query logic lives in that module (single source of truth - see its
docstring for why). This script only owns CLI parsing, console/progress
output, and per-run file logging. Kept as a script (not folded fully into
`cocli data`) because Makefile's `export-emails` target invokes it
directly; `cocli data export-enriched-emails` wraps the same service for
callers that want it as a real subcommand.
"""
from __future__ import annotations

import logging
import typer
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from cocli.core.config import get_campaign
from cocli.application.lead_export_service import export_enriched_emails

app = typer.Typer()
console = Console()


def setup_export_logging(campaign_name: str) -> Path:
    logs_dir = Path(".logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"export_emails_{campaign_name}_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file)],
        force=True,
    )
    for logger_name in ["cocli.models.companies.company", "root"]:
        lgr = logging.getLogger(logger_name)
        lgr.setLevel(logging.ERROR)
        lgr.propagate = False
        lgr.addHandler(logging.FileHandler(log_file))

    return log_file


@app.command()
def main(
    campaign_name: Optional[str] = typer.Argument(None, help="Campaign name. Defaults to current context."),
    keywords: bool = typer.Option(False, "--keywords", help="Only export companies that have found keywords (enriched)."),
    include_all: bool = typer.Option(False, "--all", "-a", help="Include all prospects even if they have no emails.")
) -> None:
    if not campaign_name:
        campaign_name = get_campaign()

    if not campaign_name:
        console.print("[bold red]Error: No campaign specified and no active context.[/bold red]")
        raise typer.Exit(1)

    log_file = setup_export_logging(campaign_name)
    console.print(f"Exporting leads for [bold]{campaign_name}[/bold]")
    console.print(f"Detailed logs: [cyan]{log_file}[/cyan]")

    try:
        result = export_enriched_emails(campaign_name, keywords=keywords, include_all=include_all)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        raise typer.Exit(1)

    console.print("\n[bold green]Success![/bold green]")
    console.print(f"Exported: [bold]{result.exported_count}[/bold] companies")
    if result.skipped_count:
        console.print(f"Skipped: [bold red]{result.skipped_count}[/bold red] records without phone/category/keyword signal (check log)")
    console.print(f"Output: [cyan]{result.output_usv}[/cyan]")
    console.print(f"Output: [cyan]{result.output_csv}[/cyan]")

    # Upload both artifacts to S3. The CSV is the one the dashboard download
    # button and on-page prospect fetch consume, so it needs a proper
    # text/csv content-type and an attachment disposition or the browser
    # won't offer a real "Save As" download for it.
    from cocli.core.reporting import get_boto3_session, load_campaign_config
    config = load_campaign_config(campaign_name)
    s3_config = config.get("aws", {})
    bucket_name = s3_config.get("cocli_web_bucket_name") or "cocli-web-assets-turboheat-net"

    try:
        session = get_boto3_session(config)
        s3 = session.client("s3")
        s3.upload_file(str(result.output_usv), bucket_name, f"exports/{campaign_name}-emails.usv")
        s3.upload_file(
            str(result.output_csv),
            bucket_name,
            f"exports/{campaign_name}-emails.csv",
            ExtraArgs={
                "ContentType": "text/csv",
                "ContentDisposition": f'attachment; filename="{campaign_name}-emails.csv"',
                "CacheControl": "no-cache, must-revalidate",
            },
        )
        console.print("[bold green]Successfully uploaded USV and CSV exports to S3.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to upload to S3: {e}[/bold red]")

if __name__ == "__main__":
    app()
