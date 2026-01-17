import typer
from rich.console import Console

from cocli.compilers.enrichment_compiler import EnrichmentCompiler

from typing import Optional

app = typer.Typer()
console = Console()

@app.command()
def compile_enrichment(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name to filter by")
) -> None:
    """
    Compiles enrichment data from various sources into the main company _index.md files.
    """
    compiler = EnrichmentCompiler()
    compiler.run(campaign_name=campaign)
    console.print("[bold green]Enrichment compilation complete.[/bold green]")
