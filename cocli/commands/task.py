import typer
from pathlib import Path
from typing import Optional, Set
from rich.console import Console
from rich.table import Table
from rich.markdown import Markdown
from rich.rule import Rule
from rich.tree import Tree

from ..application.services import ServiceContainer
from ..core.tasks import TaskStatus

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
    services = ServiceContainer()
    changes = services.task_service.sync_index()
    console.print(f"[green]Index synced. {changes} changes detected.[/green]")

@app.command(name="list")
def list_tasks() -> None:
    """List all tasks from the mission index."""
    services = ServiceContainer()
    tasks = services.task_service.get_all_tasks()
    if not tasks:
        console.print("[yellow]Index is empty. Run 'cocli task sync' to discover tasks.[/yellow]")
        return

    table = Table(title="Mission Task Index")
    table.add_column("Pri", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Slug")
    table.add_column("Title")
    table.add_column("Deps")
    
    for i, task in enumerate(tasks):
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
    """Show the current objective from the top of the mission index."""
    services = ServiceContainer()
    next_task = services.task_service.get_next_task()
    if next_task:
        task_file = services.task_service.resolve_file(next_task.slug)
        if task_file:
            render_markdown_with_links(task_file)
        else:
            console.print(f"[red]Requirement file for '{next_task.slug}' not found![/red]")
    else:
        console.print("[green]No pending or active tasks found in index![/green]")

@app.command(name="prioritize")
def prioritize_task(slug: str, position: int) -> None:
    """Update the ordinal position of a task in the mission index."""
    services = ServiceContainer()
    if services.task_service.prioritize_task(slug, position):
        console.print(f"[green]Task '{slug}' moved to position {position}.[/green]")
    else:
        console.print(f"[red]Task '{slug}' not found.[/red]")

@app.command(name="tree")
def show_tree() -> None:
    """Show a visual dependency tree of tasks."""
    services = ServiceContainer()
    tasks = services.task_service.get_all_tasks()
    root = Tree("[bold blue]Development Roadmap[/bold blue]")
    
    # Active/Pending with dependencies
    for task in tasks:
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
def start_task(slug: Optional[str] = typer.Argument(None)) -> None:
    """Move a task to ACTIVE. Defaults to the first PENDING task."""
    services = ServiceContainer()
    res = services.task_service.start_task(slug)
    if res["success"]:
        console.print(f"[green]Task '{res['slug']}' is now ACTIVE.[/green]")
    else:
        console.print(f"[red]{res['error']}[/red]")

@app.command(name="done")
def complete_task(
    slug: Optional[str] = typer.Argument(None),
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Git commit message subject."),
    body: Optional[str] = typer.Option(None, "--body", "-b", help="Git commit message body.")
) -> None:
    """Move a task to COMPLETED and create a Git commit."""
    services = ServiceContainer()
    task_slug = slug
    if not task_slug:
        # Default to ACTIVE task
        for t in services.task_service.get_all_tasks():
            if t.status == TaskStatus.ACTIVE:
                task_slug = t.slug
                break

    if not task_slug:
        console.print("[red]No active task to complete.[/red]")
        return

    # Prompt for commit message if not provided
    if not message:
        message = typer.prompt("Commit message subject")
        if not body:
            body = typer.prompt("Commit message body (optional)", default="")
    
    if body is None:
        body = ""

    def run_git_commit(msg: str, bdy: Optional[str]) -> None:
        import subprocess
        console.print("[yellow]Staging changes and running pre-commit tests...[/yellow]")
        subprocess.run(["git", "add", "."], check=True)
        commit_cmd = ["git", "commit", "-m", msg]
        if bdy:
            commit_cmd.extend(["-m", bdy])
        subprocess.run(commit_cmd, check=True)
        console.print("[green]Changes committed to git successfully.[/green]")

    res = services.task_service.complete_task(
        slug=task_slug,
        commit_message=message,
        commit_body=body,
        commit_fn=run_git_commit,
    )

    if res["success"]:
        console.print(f"[green]Task '{res['slug']}' marked as COMPLETED and removed from index.[/green]")
    else:
        console.print(f"[red]{res['error']}[/red]")
        if "Commit failed" in res["error"]:
            console.print("[red]Git commit failed (tests or lint likely failed). Task remains ACTIVE.[/red]")
            raise typer.Exit(1)


@app.command(name="create", no_args_is_help=True)
def create_task(
    title: str = typer.Argument(..., help="The title of the new task."),
    slug: Optional[str] = typer.Option(None, "--slug", "-s", help="The slug for the new task. If not provided, it will be generated from the title."),
    body: Optional[str] = typer.Option(None, "--body", "-b", help="The initial description for the task file."),
    draft: bool = typer.Option(False, "--draft", help="Create the task as a DRAFT instead of PENDING."),
    depends_on: Optional[str] = typer.Option(None, "--depends-on", "-d", help="Comma-separated list of existing task slugs this task depends on.")
) -> None:
    """Create a new task in the mission queue."""
    services = ServiceContainer()
    res = services.task_service.create_task(
        title=title,
        slug=slug,
        body=body,
        draft=draft,
        depends_on=depends_on,
    )

    if res["success"]:
        for warning in res["warnings"]:
            console.print(f"[yellow]Warning: {warning}[/yellow]")
        console.print(f"[green]Created {res['status']} task '{res['slug']}' at {res['task_file']}[/green]")
    else:
        console.print(f"[red]Error: {res['error']}[/red]")
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
