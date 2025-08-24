import subprocess
import re
from pathlib import Path

import typer
from typing_extensions import Annotated
from typing import Optional, List, Any
import sys

from rich.console import Console
from rich.prompt import Prompt
from rich.markdown import Markdown
from .scrapers import google_maps
import datetime
import subprocess
from fuzzywuzzy import process # Added for fuzzy search
import shutil
from .core.config import get_companies_dir, get_people_dir
from .core.utils import slugify, _format_entity_for_fzf, _get_all_searchable_items
from .core.models import Company, Person
from .commands import register_commands

console = Console()

app = typer.Typer(no_args_is_help=True)

register_commands(app)



if __name__ == "__main__":
    app()
