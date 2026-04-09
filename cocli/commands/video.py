"""Video processing commands for cocli."""

from pathlib import Path
from typing import Optional
import typer
from rich.console import Console

from cocli.core.config import get_campaign
from cocli.core.video import normalize_video, YouTubeUploader, youtube as video_module

app = typer.Typer()
console = Console()


@app.command()
def auth(
    platform: str = typer.Argument("youtube", help="Platform: youtube"),
    refresh: bool = typer.Option(False, "--refresh", help="Force token refresh"),
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
):
    """Authenticate to video platform via 1Password."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print(
            "[red]No campaign selected. Please specify --campaign or set a campaign context.[/red]"
        )
        raise typer.Exit(1)

    if platform == "youtube":
        try:
            client_id, client_secret, oauth_token, refresh_token = (
                video_module.get_secrets(campaign_name)
            )
            console.print("[green]YouTube credentials loaded from 1Password[/green]")
            console.print(f"  client_id: {client_id[:20]}...")
            console.print(f"  oauth_token: {'*' * 20}")
            console.print(f"  refresh_token: {'*' * 20}")

            if refresh:
                console.print(
                    "[yellow]Token refresh requested - will use OAuth flow[/yellow]"
                )
                # TODO: Implement OAuth refresh flow
        except Exception as e:
            console.print(f"[red]Error loading credentials: {e}[/red]")
            raise typer.Exit(1)
    else:
        console.print(f"[red]Unknown platform: {platform}[/red]")
        raise typer.Exit(1)


@app.command()
def normalize(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    input: str = typer.Option(..., "-i", "--input", help="Input video file"),
    output: Optional[str] = typer.Option(
        None, "-o", "--output", help="Output video file"
    ),
):
    """Normalize video audio for social media."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print(
            "[red]No campaign selected. Please specify --campaign or set a campaign context.[/red]"
        )
        raise typer.Exit(1)

    input_path = Path(input)
    if not input_path.exists():
        console.print(f"[red]Input file not found: {input}[/red]")
        raise typer.Exit(1)

    output_path = (
        Path(output)
        if output
        else (input_path.parent / f"{input_path.stem}_normalized{input_path.suffix}")
    )

    console.print(f"Normalizing: {input_path.name}")
    result, stats = normalize_video(input_path, output_path)

    if result:
        console.print(f"[green]Success: {result}[/green]")
    else:
        console.print("[red]Failed to normalize video[/red]")
        raise typer.Exit(1)


@app.command()
def upload(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    video: str = typer.Option(..., "-v", "--video", help="Video file to upload"),
    title: str = typer.Option(..., "-t", "--title", help="Video title"),
    description: str = typer.Option(
        "", "-d", "--description", help="Video description"
    ),
    privacy: str = typer.Option(
        "unlisted", "-p", "--privacy", help="Privacy: public, unlisted, private"
    ),
    tags: str = typer.Option("automation", "-g", "--tags", help="Comma-separated tags"),
):
    """Upload video to YouTube."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print(
            "[red]No campaign selected. Please specify --campaign or set a campaign context.[/red]"
        )
        raise typer.Exit(1)

    video_path = Path(video)
    if not video_path.exists():
        console.print(f"[red]Video file not found: {video}[/red]")
        raise typer.Exit(1)

    tag_list = [t.strip() for t in tags.split(",")]
    uploader = YouTubeUploader(campaign=campaign_name)

    console.print(f"Uploading: {title}")
    result = uploader.upload(
        video_path,
        title,
        description=description,
        tags=tag_list,
        privacy=privacy,
    )

    if result:
        console.print("[green]Success![/green]")
        console.print(f"  Video ID: {result['id']}")
        console.print(f"  URL: {result['url']}")
    else:
        console.print("[red]Upload failed[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
