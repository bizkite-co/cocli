import typer
from pathlib import Path
from typing import List
from rich.console import Console
from rich.table import Table
from rich.markdown import Markdown
from rich.rule import Rule

app = typer.Typer(help="Manage development tasks and architectural issues.", no_args_is_help=True)
console = Console()

ISSUES_ROOT = Path("docs/issues")
PENDING = ISSUES_ROOT / "pending"
ACTIVE = ISSUES_ROOT / "active"
COMPLETED = ISSUES_ROOT / "completed" / "2026"

def get_pending_tasks() -> List[Path]:
    """Returns sorted list of pending task files."""
    if not PENDING.exists():
        return []
    return sorted(list(PENDING.glob("*.md")))

def get_active_tasks() -> List[Path]:
    """Returns list of active task files."""
    if not ACTIVE.exists():
        return []
    return list(ACTIVE.glob("*.md"))

@app.command(name="list")
def list_tasks() -> None:
    """List all pending and active tasks."""
    active = get_active_tasks()
    pending = get_pending_tasks()
    
    table = Table(title="Task Queue")
    table.add_column("Status", justify="center")
    table.add_column("ID/Priority", justify="right")
    table.add_column("Slug")
    
    for task in active:
        table.add_row("[bold yellow]ACTIVE[/]", "-", task.name, style="yellow")
        
    for task in pending:
        parts = task.stem.split("_", 1)
        priority = parts[0] if len(parts) > 1 else "-"
        slug = parts[1] if len(parts) > 1 else task.stem
        table.add_row("[white]PENDING[/]", priority, slug)
        
    console.print(table)

@app.command(name="next")
def show_next() -> None:
    """Show the highest priority pending task."""
    active = get_active_tasks()
    if active:
        console.print("[yellow]Currently Active Task:[/yellow]")
        task_file = active[0]
    else:
        pending = get_pending_tasks()
        if not pending:
            console.print("[green]No pending tasks found![/green]")
            return
        task_file = pending[0]
        
    console.print(Rule(f"Task: {task_file.name}", style="bold blue"))
    console.print(Markdown(task_file.read_text(encoding="utf-8")))

@app.command(name="start")
def start_task(slug_or_priority: str) -> None:
    """Move a task from pending to active."""
    pending = get_pending_tasks()
    target = None
    
    for task in pending:
        if slug_or_priority in task.name:
            target = task
            break
            
    if not target:
        console.print(f"[red]Task not found matching '{slug_or_priority}'[/red]")
        return
        
    ACTIVE.mkdir(parents=True, exist_ok=True)
    # Remove prefix like 01_ for active state
    new_name = target.name
    if "_" in new_name:
        new_name = new_name.split("_", 1)[1]
        
    target.rename(ACTIVE / new_name)
    console.print(f"[green]Task '{new_name}' is now ACTIVE[/green]")

@app.command(name="done")
def complete_task(slug: str) -> None:
    """Move a task from active to completed."""
    active = get_active_tasks()
    target = None
    
    for task in active:
        if slug in task.name:
            target = task
            break
            
    if not target:
        console.print(f"[red]Active task matching '{slug}' not found.[/red]")
        return
        
    COMPLETED.mkdir(parents=True, exist_ok=True)
    target.rename(COMPLETED / target.name)
    console.print(f"[green]Task '{target.name}' marked as COMPLETED[/green]")

if __name__ == "__main__":
    app()
