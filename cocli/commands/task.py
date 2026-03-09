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
    """Sync the task index with the filesystem (discovering active/pending/draft)."""
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
        elif task.status == TaskStatus.DRAFT:
            status_color = "dim white"
        
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
        task_file = manager.resolve_file(next_task.slug)
        if task_file:
            render_markdown_with_links(task_file)
        else:
            console.print(f"[red]Requirement file for '{next_task.slug}' not found![/red]")
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
    
    # Active/Pending with dependencies
    for task in manager.tasks:
        label = task.slug
        if task.status == TaskStatus.ACTIVE:
            label = f"[bold yellow]{label} (ACTIVE)[/bold yellow]"
        elif task.status == TaskStatus.BLOCKED:
            label = f"[red]{label} (BLOCKED by {';'.join(task.dependencies)})[/red]"
        elif task.status == TaskStatus.DRAFT:
            label = f"[dim white]{label} (DRAFT)[/dim white]"
        
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

    # Find file
    old_path = manager.resolve_file(task.slug)
    if not old_path:
        console.print(f"[red]Requirement file for '{task.slug}' not found.[/red]")
        return

    new_rel_name = old_path.name
    # Strip numeric prefix if moving from pending
    if old_path.parent.name == "pending" and "_" in old_path.name:
        new_rel_name = old_path.name.split("_", 1)[1]
        
    new_path = ISSUES_ROOT / "active" / new_rel_name
    new_path.parent.mkdir(parents=True, exist_ok=True)
    
    old_path.rename(new_path)
    
    # Update index
    task.status = TaskStatus.ACTIVE
    manager.save()
    console.print(f"[green]Task '{task.slug}' is now ACTIVE.[/green]")

@app.command(name="done")
def complete_task(slug: str) -> None:
    """Move a task to COMPLETED and remove from index."""
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

    old_path = manager.resolve_file(task.slug)
    if not old_path:
        console.print(f"[red]Requirement file for '{task.slug}' not found.[/red]")
        return

    new_path = ISSUES_ROOT / "completed" / "2026" / old_path.name
    new_path.parent.mkdir(parents=True, exist_ok=True)
    
    old_path.rename(new_path)
    
    # Removing from index happens automatically on save because we filter by status != COMPLETED
    task.status = TaskStatus.COMPLETED
    
    manager.update_blocked_states()
    manager.save()
    console.print(f"[green]Task '{task.slug}' marked as COMPLETED and removed from index.[/green]")

if __name__ == "__main__":
    app()
