from pydantic import BaseModel
from typing import List


class CliCommandMatch(BaseModel):
    """One command/subcommand found by `cocli help <phrase>`. See
    application.audit_service.search_cli_tree."""

    path: str
    description: str
    options: List[str] = []
