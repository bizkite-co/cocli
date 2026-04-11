"""Video processing commands for cocli."""

import shutil
import subprocess
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)

from cocli.core.config import (
    get_campaign,
    get_campaign_dir,
    load_campaign_config,
)
from cocli.core.video import (
    YouTubeUploader,
    transcriber,
    thumbnailer,
    get_duration,
    normalize_video,
)

app = typer.Typer(help="Commands for video processing.", no_args_is_help=True)
console = Console()


def extract_thumbnails_logic(video_path: Path) -> None:
    """Internal logic to extract thumbnails."""
    console.print(f"Extracting thumbnails from: {video_path.name}")

    # Use ffmpeg scene detection to get 5 frames
    cmd = [
        "ffmpeg",
        "-i",
        str(video_path),
        "-vf",
        "select='gt(scene,0.3)',scale=640:-1,showinfo",
        "-vsync",
        "0",
        "-frames:v",
        "5",
        "-q:v",
        "2",
        str(video_path.parent / "thumb_%03d.png"),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        console.print(f"[green]Thumbnails extracted to {video_path.parent}[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to extract thumbnails: {e.stderr.decode()}[/red]")


def get_video_queue_root(campaign_name: str) -> Path:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        raise ValueError(f"Campaign directory not found for: {campaign_name}")
    return campaign_dir / "video"


@app.command()
def add(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    video: str = typer.Argument(..., help="Path to video file"),
) -> None:
    """Add a video to the raw queue."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    try:
        raw_dir = get_video_queue_root(campaign_name) / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        video_path = Path(video)
        if not video_path.exists():
            console.print(f"[red]File not found: {video}[/red]")
            raise typer.Exit(1)

        dest = raw_dir / video_path.name
        shutil.copy2(video_path, dest)
        console.print(f"[green]Added {video_path.name} to raw queue.[/green]")
    except Exception:
        import traceback

        console.print("[red]Error adding video:[/red]")
        console.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command()
def normalize(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
) -> None:
    """Normalize videos in the raw queue."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    try:
        queue_root = get_video_queue_root(campaign_name)
        raw_dir = queue_root / "raw"

        if not raw_dir.exists():
            console.print(f"[yellow]Raw directory not found: {raw_dir}[/yellow]")
            return

        norm_dir = queue_root / "normalized"
        norm_dir.mkdir(parents=True, exist_ok=True)

        files = list(raw_dir.glob("*.mp4"))
        if not files:
            console.print(f"[yellow]No videos found in {raw_dir}[/yellow]")
            return

        for video_file in files:
            console.print(f"Processing: {video_file.name}")

            # Create normalized subdir
            video_dir = norm_dir / video_file.stem
            video_dir.mkdir(parents=True, exist_ok=True)

            # Define output path
            output_path = video_dir / f"{video_file.name}"
            console.print(f"Normalizing {video_file.name} to {output_path.name}...")

            # Get duration for progress bar
            duration = get_duration(str(video_file))

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"Normalizing {video_file.name}", total=duration
                )

                def callback(current_sec: float, total_sec: float) -> None:
                    progress.update(task, completed=current_sec)

                # We call the existing normalization logic, keeping input in raw/
                camp_cfg = load_campaign_config(campaign_name)
                loudness_cfg = camp_cfg.get("video", {}).get("loudness", {})
                denoise_cfg = camp_cfg.get("video", {}).get("denoise", {})
                result, stats = normalize_video(
                    video_file,
                    output_path,
                    callback=callback,
                    loudness_config=loudness_cfg,
                    denoise_config=denoise_cfg,
                )

            if not result:
                console.print(f"[red]Failed to normalize {video_file.name}[/red]")
                continue

            # Remove original from raw/ ONLY after success
            video_file.unlink()

            # Create metadata file
            md_file = video_dir / f"{video_file.stem}.md"
            with open(md_file, "w") as f:
                f.write("---\n")
                f.write('thumbnail-text: ""\n')
                f.write('thumbnail-style: ""\n')
                f.write("draft: true\n")
                f.write("---\n\n")

            console.print(f"[green]Normalized: {video_file.stem}[/green]")

    except Exception:
        import traceback

        console.print("[red]Error during normalization:[/red]")
        console.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command()
def package(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing packaged data"
    ),
) -> None:
    """Package videos from the normalized queue."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    try:
        queue_root = get_video_queue_root(campaign_name)
        norm_dir = queue_root / "normalized"
        pack_dir = queue_root / "packaged"
        pack_dir.mkdir(parents=True, exist_ok=True)

        # Iterate through normalized subdirs
        for video_dir in norm_dir.iterdir():
            if not video_dir.is_dir():
                continue

            # Check if already packaged
            if (pack_dir / video_dir.name).exists() and not force:
                console.print(
                    f"[yellow]Skipping: {video_dir.name} already packaged. Use --force to overwrite.[/yellow]"
                )
                continue

            if force and (pack_dir / video_dir.name).exists():
                console.print(f"[blue]Overwriting: {video_dir.name}[/blue]")
                shutil.rmtree(pack_dir / video_dir.name)

            console.print(f"Packaging: {video_dir.name}")

            # 1. Identify video file
            video_file = next(video_dir.glob("*.mp4"))

            # 2. Extract Thumbnails
            extract_thumbnails_logic(video_file)

            # 3. Transcribe
            console.print(f"Transcribing {video_file.name}...")

            camp_cfg = load_campaign_config(campaign_name)
            provider = (
                camp_cfg.get("video", {})
                .get("transcription", {})
                .get("provider", "gemini")
            )
            transcriber_engine = transcriber.TranscriptionFactory.get_transcriber(
                provider
            )
            transcripts = transcriber_engine.transcribe(video_file, campaign_name)

            # 4. Save transcripts
            for provider_name, transcript_text in transcripts.items():
                transcript_path = video_dir / f"transcript_{provider_name}.md"
                with open(transcript_path, "w") as f:
                    f.write(transcript_text)
                console.print(
                    f"[green]Saved transcript to {transcript_path.name}[/green]"
                )

            # 5. Copy to packaged
            shutil.copytree(video_dir, pack_dir / video_dir.name)

            # 6. Process Thumbnail
            thumbnailer.process_thumbnail(video_dir, pack_dir / video_dir.name)

            console.print(f"[green]Packaged: {video_dir.name}[/green]")

    except Exception:
        import traceback

        console.print("[red]Error during packaging:[/red]")
        console.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command()
def extract_thumbnails(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    video: str = typer.Argument(..., help="Video file name (in raw/ or normalized/)"),
) -> None:
    """Extract candidate thumbnails from a video."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    queue_root = get_video_queue_root(campaign_name)
    # Search in raw or normalized
    video_path = None
    for folder in ["raw", "normalized"]:
        search_path = queue_root / folder
        if search_path.exists():
            # Get only files
            matches = [
                p
                for p in search_path.rglob(f"*{video}*")
                if p.is_file() and p.suffix == ".mp4"
            ]
            if matches:
                video_path = matches[0]
                break

    if not video_path:
        console.print(f"[red]Video file not found: {video}[/red]")
        raise typer.Exit(1)

    extract_thumbnails_logic(video_path)


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
) -> None:
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
