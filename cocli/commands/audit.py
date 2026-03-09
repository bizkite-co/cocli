import typer
from typing import Optional, Any
from pathlib import Path

from rich.console import Console

app = typer.Typer(help="Auditing tools for the cocli system structure and integrity.", no_args_is_help=True)
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

@app.command(name="fs")
def audit_fs(
    campaign: Optional[str] = typer.Option(None, "--campaign", "-c", help="Specific campaign to audit."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path.")
) -> None:
    """
    Audits the filesystem for OMAP compliance and Screaming Architecture.
    """
    from ..core.audit.fs_auditor import FsAuditor, AuditNode, AuditStatus, dump_audit_tree
    from ..core.paths import paths
    from io import StringIO
    
    auditor = FsAuditor()
    
    # 1. Audit Root (top level components)
    root_node = AuditNode(name="data_root", path=paths.root, is_dir=True, status=AuditStatus.VALID)
    root_node.children.append(auditor.audit_campaigns(campaign))
    root_node.children.append(auditor.audit_queues())
    
    # Add indexes and companies as placeholders for now
    root_node.children.append(AuditNode(
        name="indexes", path=paths.root / "indexes", is_dir=True,
        status=AuditStatus.VALID if (paths.root / "indexes").exists() else AuditStatus.MISSING
    ))
    root_node.children.append(AuditNode(
        name="companies", path=paths.root / "companies", is_dir=True,
        status=AuditStatus.VALID if (paths.root / "companies").exists() else AuditStatus.MISSING
    ))
    
    tree = dump_audit_tree(root_node)
    
    if output:
        # For file output, we'll use a plain text version
        out = StringIO()
        file_console = Console(file=out, force_terminal=False, color_system=None)
        file_console.print(tree)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(out.getvalue(), encoding="utf-8")
        console.print(f"[green]Filesystem audit dumped to {output}[/green]")
    else:
        console.print(tree)

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
