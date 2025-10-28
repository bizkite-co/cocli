import typer
import subprocess
from pathlib import Path

app = typer.Typer()

@app.command()
def sync(
    ctx: typer.Context,
    message: str = typer.Option(..., "--message", "-m", help="Commit message for the data folder changes."),
) -> None:
    """
    Performs a git sync and push of the data folder.
    """
    data_folder = Path("data")
    if not data_folder.is_dir():
        typer.echo("Error: 'data' folder not found. Please ensure you are in the project root directory.")
        raise typer.Exit(code=1)

    typer.echo("Staging changes in 'data' folder...")
    try:
        subprocess.run(["git", "add", str(data_folder)], check=True)
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error staging changes: {e}")
        raise typer.Exit(code=1)

    typer.echo(f"Committing changes with message: '{message}'...")
    try:
        subprocess.run(["git", "commit", "-m", message], check=True)
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error committing changes: {e}")
        raise typer.Exit(code=1)

    typer.echo("Pulling latest changes from remote...")
    try:
        subprocess.run(["git", "pull", "--rebase"], check=True)
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error pulling changes: {e}")
        raise typer.Exit(code=1)

    typer.echo("Pushing changes to remote...")
    try:
        subprocess.run(["git", "push"], check=True)
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error pushing changes: {e}")
        raise typer.Exit(code=1)

    typer.echo("Git sync and push of 'data' folder completed successfully.")
