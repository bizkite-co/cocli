
import typer

from .commands import enrich
from .commands import query
from rich.console import Console

from .commands import register_commands

from .core import logging_config

console = Console()

logging_config.setup_logging()

app = typer.Typer(no_args_is_help=True)
app.add_typer(enrich.app, name="enrich", help="Commands for enriching company data.")
app.add_typer(query.app, name="query", help="Commands for querying company data.")

from .commands import companies
app.add_typer(companies.app, name="companies", help="Commands for managing companies.")

register_commands(app)



if __name__ == "__main__":
    app()
