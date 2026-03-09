import os
import sys
from typing import Any

# Ensure cocli is in the path
sys.path.append(os.getcwd())

from typer.main import get_command
from cocli.main import app as main_app

def dump_cli_tree(command: Any, indent: int = 0) -> None:
    """
    Recursively dumps the click command/group hierarchy.
    """
    name = command.name or "root"
    help_text = f" - {command.help}" if command.help else ""
    print(" " * indent + f"{name}{help_text}")
    
    # Dump params (options/arguments)
    for param in command.params:
        param_name = "/".join(param.opts) if param.opts else param.name
        param_type = f" ({param.type.name})" if hasattr(param.type, 'name') else ""
        required = " [required]" if param.required else ""
        print(" " * (indent + 4) + f"{param_name}{param_type}{required}")

    # Recurse into subcommands if it's a group
    if hasattr(command, 'commands'):
        for sub_name, sub_command in sorted(command.commands.items()):
            dump_cli_tree(sub_command, indent + 4)

if __name__ == "__main__":
    # Typer apps need to be "built" into click objects
    click_command = get_command(main_app)
    dump_cli_tree(click_command)
