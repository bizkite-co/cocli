import typer
from . import mgmt, workflow, planning, viz, prospecting
from .. import prospects

app = typer.Typer(no_args_is_help=True, help="Manage campaigns.")

# Merge all commands into the main campaign app
app.add_typer(mgmt.app, name="", help="Campaign management")
app.add_typer(workflow.app, name="", help="Workflow management")
app.add_typer(planning.app, name="", help="Planning and importing")
app.add_typer(viz.app, name="", help="Visualization")
app.add_typer(prospecting.app, name="", help="Prospecting and scraping")

# Add the prospects sub-typer
app.add_typer(prospects.app, name="prospects", help="Manage prospects within a campaign")