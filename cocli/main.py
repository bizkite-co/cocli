import subprocess
import re
from pathlib import Path

import typer
from typing_extensions import Annotated
from typing import Optional, List, Any
import sys

from .commands import enrich
from .commands import query
from rich.console import Console
from rich.prompt import Prompt
from rich.markdown import Markdown
from .scrapers import google_maps
import datetime
import subprocess
from fuzzywuzzy import process # type: ignore # Added for fuzzy search
import shutil
from .core.config import get_companies_dir, get_people_dir

from .core.utils import slugify, _format_entity_for_fzf
from .models.company import Company
from .models.person import Person
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
