import typer
from typing import Optional, Any
from pathlib import Path

from rich.console import Console

app = typer.Typer(help="Auditing tools for the cocli system structure and integrity.")
console = Console()

def dump_cli_tree(command: Any, out: Any, indent: int = 0) -> None:
    name = command.name or "cocli"
    help_text = f" - {command.help.splitlines()[0]}" if command.help else ""
    out.write(" " * indent + f"{name}{help_text}\n")
    
    for param in command.params:
        if getattr(param, "hidden", False):
            continue
        # Typer adds these by default
        if param.name in ["install_completion", "show_completion"]:
            continue
            
        param_name = "/".join(param.opts) if param.opts else param.name
        param_type = f" ({param.type.name})" if hasattr(param.type, 'name') else ""
        required = " [required]" if param.required else ""
        out.write(" " * (indent + 4) + f"{param_name}{param_type}{required}\n")

    if hasattr(command, 'commands'):
        for sub_name, sub_command in sorted(command.commands.items()):
            dump_cli_tree(sub_command, out, indent + 4)

@app.command(name="cli")
def audit_cli(
    ctx: typer.Context,
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path.")
) -> None:
    """
    Dumps the CLI command hierarchy.
    """
    from typer.main import get_command
    from io import StringIO
    
    # Late import main_app to avoid circular dependency
    from ..main import app as main_app
    
    click_command = get_command(main_app)
    
    out = StringIO()
    dump_cli_tree(click_command, out)
    
    report = out.getvalue()
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        console.print(f"[green]CLI structure dumped to {output}[/green]")
    else:
        console.print(report)

@app.command(name="tui")
def audit_tui(
    output: Optional[Path] = typer.Option(
        Path("docs/tui/screen/actual_tree.txt"), "--output", "-o", help="Output file path."
    )
) -> None:
    """
    Dumps the TUI widget hierarchy.
    """
    # This just wraps the existing functionality
    # But cocli tui --dump-tree already does this.
    console.print(f"To dump TUI tree, use: [bold]cocli tui --dump-tree {output}[/bold]")
