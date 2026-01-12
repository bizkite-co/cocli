import typer
from cocli.commands.campaign import mgmt, workflow, planning, viz, prospecting, enrichment
from cocli.commands import prospects, exclude

# Re-export core functions for backward compatibility and testing
from cocli.core.config import get_campaign as get_campaign, get_campaign_dir as get_campaign_dir, get_cocli_base_dir as get_cocli_base_dir, get_editor_command as get_editor_command
from cocli.core.utils import run_fzf as run_fzf
from cocli.commands.campaign.workflow import next_step as next_step

app = typer.Typer(no_args_is_help=True, help="Manage campaigns.")

# Merge all commands into the main campaign app
app.add_typer(mgmt.app, name="", help="Campaign management")
app.add_typer(workflow.app, name="", help="Workflow management")
app.add_typer(planning.app, name="", help="Planning and importing")
app.add_typer(viz.app, name="", help="Visualization")
app.add_typer(prospecting.app, name="", help="Prospecting and scraping")
app.add_typer(enrichment.app, name="", help="Website Enrichment")

# Add the prospects sub-typer
app.add_typer(prospects.app, name="prospects", help="Manage prospects within a campaign")
app.add_typer(exclude.app, name="exclude", help="Manage campaign-specific exclusions")
