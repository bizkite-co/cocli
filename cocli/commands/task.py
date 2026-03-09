import typer
from pathlib import Path
from typing import Optional, Set
from rich.console import Console
from rich.table import Table
from rich.markdown import Markdown
from rich.rule import Rule
from rich.tree import Tree

from ..core.tasks import TaskIndexManager, TaskStatus

app = typer.Typer(help="Manage development tasks and architectural issues.", no_args_is_help=True)
console = Console()

ISSUES_ROOT = Path("docs/issues")

def render_markdown_with_links(path: Path, seen: Optional[Set[Path]] = None) -> None:
    """Renders a markdown file and recursively renders any local .md links found within it."""
    if seen is None:
        seen = set()
    
    abs_path = path.resolve()
    if abs_path in seen or not path.exists():
        return
    
    seen.add(abs_path)
    
    content = path.read_text(encoding="utf-8")
    console.print(Rule(f"File: {path.name}", style="bold blue"))
    console.print(Markdown(content))
    
    # Extract local markdown links: [text](path/to/file.md)
    import re
    links = re.findall(r'\[(?:[^\]]+)\]\(([^)]+\.md)\)', content)
    
    for link in links:
        # Resolve relative to the current file's directory
        link_path = (path.parent / link).resolve()
        if link_path.exists():
            render_markdown_with_links(link_path, seen)

@app.command(name="sync")
def sync_index() -> None:
    """Sync the task index with the filesystem."""
    manager = TaskIndexManager()
    changes = manager.sync()
    console.print(f"[green]Index synced. {changes} changes detected.[/green]")

@app.command(name="list")
def list_tasks() -> None:
    """List all tasks from the mission index."""
    manager = TaskIndexManager()
    if not manager.tasks:
        console.print("[yellow]Index is empty. Run 'cocli task sync' to discover tasks.[/yellow]")
        return

    table = Table(title="Mission Task Index")
    table.add_column("Pri", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Slug")
    table.add_column("Title")
    table.add_column("Deps")
    
    for i, task in enumerate(manager.tasks):
        status_color = "white"
        if task.status == TaskStatus.ACTIVE:
            status_color = "bold yellow"
        elif task.status == TaskStatus.COMPLETED:
            status_color = "green"
        elif task.status == TaskStatus.BLOCKED:
            status_color = "red"
        
        deps_str = ";".join(task.dependencies) if task.dependencies else "-"
        table.add_row(
            str(i + 1),
            f"[{status_color}]{task.status}[/]",
            task.slug,
            task.title,
            deps_str
        )
        
    console.print(table)

@app.command(name="next")
def show_next() -> None:
    """Show the current objective and follow links."""
    # 1. Authoritative Pointer
    task_ptr = Path("task.md")
    if task_ptr.exists():
        render_markdown_with_links(task_ptr)
        return

    # 2. Index Lookup
    manager = TaskIndexManager()
    next_task = manager.get_next_task()
    if next_task:
        render_markdown_with_links(ISSUES_ROOT / next_task.file_path)
    else:
        console.print("[green]No pending or active tasks found in index![/green]")

@app.command(name="prioritize")
def prioritize_task(slug: str, position: int) -> None:
    """Update the ordinal position of a task."""
    manager = TaskIndexManager()
    if manager.prioritize(slug, position):
        console.print(f"[green]Task '{slug}' moved to position {position}.[/green]")
    else:
        console.print(f"[red]Task '{slug}' not found.[/red]")

@app.command(name="tree")
def show_tree() -> None:
    """Show a visual dependency tree of tasks."""
    manager = TaskIndexManager()
    root = Tree("[bold blue]Development Roadmap[/bold blue]")
    
    # Simple dependency tree (only 1 level deep for now)
    added = set()
    
    # 1. Add Completed tasks as foundation
    completed = root.add("[green]Completed[/green]")
    for task in manager.tasks:
        if task.status == TaskStatus.COMPLETED:
            completed.add(f"[dim]{task.slug}[/dim]")
            added.add(task.slug)
            
    # 2. Add Active/Pending with dependencies
    for task in manager.tasks:
        if task.slug in added:
            continue
        
        label = task.slug
        if task.status == TaskStatus.ACTIVE:
            label = f"[bold yellow]{label} (ACTIVE)[/bold yellow]"
        elif task.status == TaskStatus.BLOCKED:
            label = f"[red]{label} (BLOCKED by {';'.join(task.dependencies)})[/red]"
        
        root.add(label)
        
    console.print(root)

@app.command(name="start")
def start_task(slug: str) -> None:
    """Move a task to ACTIVE in the index and on disk."""
    manager = TaskIndexManager()
    
    # Find by slug or priority
    task = None
    for i, t in enumerate(manager.tasks):
        if t.slug == slug or str(i + 1) == slug:
            task = t
            break
            
    if not task:
        console.print(f"[red]Task '{slug}' not found.[/red]")
        return

    if task.status == TaskStatus.BLOCKED:
        console.print(f"[red]Task '{task.slug}' is BLOCKED by {';'.join(task.dependencies)}[/red]")
        return

    # Move file on disk
    old_path = ISSUES_ROOT / task.file_path
    new_rel_name = old_path.name
    if "pending" in task.file_path and "_" in old_path.name:
        new_rel_name = old_path.name.split("_", 1)[1]
        
    new_rel_path = f"active/{new_rel_name}"
    new_path = ISSUES_ROOT / new_rel_path
    new_path.parent.mkdir(parents=True, exist_ok=True)
    
    old_path.rename(new_path)
    
    # Update index
    task.status = TaskStatus.ACTIVE
    task.file_path = new_rel_path
    manager.save()
    console.print(f"[green]Task '{task.slug}' is now ACTIVE.[/green]")

@app.command(name="done")
def complete_task(slug: str) -> None:
    """Move a task to COMPLETED."""
    manager = TaskIndexManager()
    
    # Find by slug or priority
    task = None
    for i, t in enumerate(manager.tasks):
        if t.slug == slug or str(i + 1) == slug:
            task = t
            break
            
    if not task:
        console.print(f"[red]Task '{slug}' not found.[/red]")
        return

    old_path = ISSUES_ROOT / task.file_path
    new_rel_path = f"completed/2026/{old_path.name}"
    new_path = ISSUES_ROOT / new_rel_path
    new_path.parent.mkdir(parents=True, exist_ok=True)
    
    old_path.rename(new_path)
    
    task.status = TaskStatus.COMPLETED
    task.file_path = new_rel_path
    
    # Update blocked states of others
    manager.update_blocked_states()
    manager.save()
    console.print(f"[green]Task '{task.slug}' marked as COMPLETED.[/green]")

if __name__ == "__main__":
    app()
