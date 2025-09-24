import typer
from rich.console import Console

from cocli.compilers.enrichment_compiler import EnrichmentCompiler

app = typer.Typer()
console = Console()

@app.command()
def compile_enrichment():
    """
    Compiles enrichment data from various sources into the main company _index.md files.
    """
    compiler = EnrichmentCompiler()
    compiler.run()
    console.print("[bold green]Enrichment compilation complete.[/bold green]")
