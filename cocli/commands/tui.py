import typer
import logging

from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(no_args_is_help=True, invoke_without_command=True)

@app.callback(invoke_without_command=True)
def tui(
    ctx: typer.Context,
) -> None:
    """
    Launches the Textual TUI for cocli.
    """
    if ctx.invoked_subcommand is not None:
        return

    from ..tui.app import CocliApp
    app = CocliApp()
    app.run()
