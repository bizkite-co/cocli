"""Video processing commands for cocli."""

import shutil
import subprocess
from pathlib import Path
from typing import Optional
import typer
import yaml
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
    chapters,
)
from cocli.core.video.transcript_to_vtt import convert_transcript_to_vtt
from cocli.core.video import auth as video_auth
from cocli.core.text_utils import slugdotify

app = typer.Typer(no_args_is_help=True)
console = Console()


def extract_screenshots_logic(video_path: Path) -> None:
    """Internal logic to extract screenshots."""
    console.print(f"Extracting screenshots from: {video_path.name}")

    # Use ffmpeg scene detection to get 5 frames
    # Lowered threshold to 0.1 for better sensitivity
    cmd = [
        "ffmpeg",
        "-i",
        str(video_path),
        "-vf",
        "select='gt(scene,0.1)',scale=640:-1,showinfo",
        "-vsync",
        "0",
        "-frames:v",
        "5",
        "-q:v",
        "2",
        str(video_path.parent / "screenshot_%03d.png"),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        console.print(f"[green]Screenshots extracted to {video_path.parent}[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to extract screenshots: {e.stderr.decode()}[/red]")


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

        # Sanitize filename
        safe_name = slugdotify(video_path.name)
        dest = raw_dir / safe_name

        shutil.copy2(video_path, dest)
        console.print(f"[green]Added {safe_name} to raw queue.[/green]")
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

            # Create metadata file only if it doesn't exist
            md_file = video_dir / f"{video_file.stem}.md"
            if not md_file.exists():
                with open(md_file, "w") as f:
                    f.write("---\n")
                    f.write('title: ""\n')
                    f.write('thumbnail-text: ""\n')
                    f.write('thumbnail-style: ""\n')
                    f.write("draft: true\n")
                    f.write("---\n\n")

            # Extract screenshots here
            extract_screenshots_logic(video_file)

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

            # Target directory for THIS video
            target_video_dir = pack_dir / video_dir.name
            target_video_dir.mkdir(parents=True, exist_ok=True)

            # Target directory for THIS video
            target_video_dir = pack_dir / video_dir.name
            target_video_dir.mkdir(parents=True, exist_ok=True)

            console.print(f"Packaging: {video_dir.name}")
            console.print(f"[dim]Source: {video_dir}[/dim]")
            console.print(f"[dim]Destination: {target_video_dir}[/dim]")

            # 1. Identify video file
            video_file = next(video_dir.glob("*.mp4"))

            # 2. Transcribe
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

            # 3. Save transcripts
            for provider_name, transcript_text in transcripts.items():
                transcript_path = video_dir / f"transcript_{provider_name}.md"
                with open(transcript_path, "w") as f:
                    f.write(transcript_text)
                console.print(
                    f"[green]Saved transcript to {transcript_path.name}[/green]"
                )

            # 3.5. Generate chapters from the first transcript
            first_transcript = next(iter(transcripts.values()), "")
            if first_transcript:
                console.print("Generating chapters...")
                try:
                    chapter_text = chapters.create_chapters(
                        first_transcript, campaign_name
                    )
                    chapters_path = video_dir / "chapters.md"
                    with open(chapters_path, "w") as f:
                        f.write(chapter_text)
                    console.print(
                        f"[green]Saved chapters to {chapters_path.name}[/green]"
                    )
                except Exception as e:
                    console.print(f"[yellow]Chapter generation failed: {e}[/yellow]")

            # 4. Generate VTT (closed captions) from first transcript
            if first_transcript:
                console.print("Generating VTT closed captions...")
                try:
                    vtt_path = video_dir / "captions.vtt"
                    convert_transcript_to_vtt(first_transcript, vtt_path)
                    console.print(f"[green]Saved captions to {vtt_path.name}[/green]")
                except Exception as e:
                    console.print(f"[yellow]VTT generation failed: {e}[/yellow]")

            # 4. Copy to packaged
            for item in video_dir.iterdir():
                if item.is_dir():
                    shutil.copytree(
                        item, target_video_dir / item.name, dirs_exist_ok=True
                    )
                else:
                    shutil.copy2(item, target_video_dir / item.name)

            # 5. Process Thumbnail
            thumbnailer.process_thumbnail(video_dir, target_video_dir)

            console.print(f"[green]Packaged: {video_dir.name}[/green]")

    except Exception:
        import traceback

        console.print("[red]Error during packaging:[/red]")
        console.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command()
def create_thumbnail(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    video_slug: str = typer.Argument(
        ..., help="Video slug (directory name in normalized/)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing thumbnail"
    ),
) -> None:
    """Create a thumbnail for a video using metadata."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    queue_root = get_video_queue_root(campaign_name)
    norm_dir = queue_root / "normalized" / video_slug
    pack_dir = queue_root / "packaged" / video_slug

    if not norm_dir.exists():
        console.print(f"[red]Normalized video directory not found: {norm_dir}[/red]")
        raise typer.Exit(1)

    pack_dir.mkdir(parents=True, exist_ok=True)

    # Process thumbnail
    thumbnailer.process_thumbnail(norm_dir, pack_dir)
    console.print(f"[green]Thumbnail created for {video_slug}[/green]")


@app.command()
def extract_screenshots(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    video: str = typer.Argument(..., help="Video file name or path"),
) -> None:
    """Extract candidate screenshots from a video."""

    video_path: Optional[Path] = None
    # 2. If not a direct path, fallback to campaign search
    if not Path(video).exists():
        campaign_name = campaign or get_campaign()
        if not campaign_name:
            console.print("[red]Video file not found and no campaign specified.[/red]")
            raise typer.Exit(1)

        queue_root = get_video_queue_root(campaign_name)
        # Search in raw or normalized
        found_path: Optional[Path] = None
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
                    found_path = matches[0]
                    break
        video_path = found_path if found_path else Path("invalid_path")

    if video_path is None or not video_path.exists():
        console.print(f"[red]Video file not found: {video}[/red]")
        raise typer.Exit(1)

    extract_screenshots_logic(video_path)


@app.command()
def upload(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    video_slug: Optional[str] = typer.Option(
        None, "-v", "--video", help="Video slug to upload (from normalized/)"
    ),
    privacy: str = typer.Option(
        "unlisted", "-p", "--privacy", help="Privacy: public, unlisted, private"
    ),
    force_privacy: bool = typer.Option(
        False,
        "--force-privacy",
        help="Override metadata draft setting with CLI privacy",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without uploading"),
) -> None:
    """Upload a video to YouTube using metadata from normalized queue."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print(
            "[red]No campaign selected. Please specify --campaign or set a campaign context.[/red]"
        )
        raise typer.Exit(1)

    queue_root = get_video_queue_root(campaign_name)
    norm_dir = queue_root / "normalized"
    pack_dir = queue_root / "packaged"
    upload_dir = queue_root / "uploaded"

    if video_slug:
        video_dirs = [norm_dir / video_slug]
    else:
        video_dirs = [d for d in norm_dir.iterdir() if d.is_dir()]

    for video_dir in video_dirs:
        slug = video_dir.name
        console.print(f"\n[cyan]Processing: {slug}[/cyan]")

        md_file = video_dir / f"{slug}.md"
        if not md_file.exists():
            console.print(f"[red]Metadata file not found: {md_file}[/red]")
            continue

        with open(md_file) as f:
            content = f.read()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                metadata = yaml.safe_load(parts[1]) or {}
                description_body = parts[2].strip()
            else:
                metadata = {}
                description_body = content
        else:
            metadata = {}
            description_body = content

        title = metadata.get("title", slug)
        if not title:
            title = slug.replace("-", " ").replace("_", " ").title()

        is_draft = metadata.get("draft", True)
        final_privacy = (
            privacy if force_privacy else ("private" if is_draft else "public")
        )
        console.print(f"  Privacy: {final_privacy}")

        playlist_id = metadata.get("playlist")
        if playlist_id:
            console.print(f"  Playlist: {playlist_id}")

        chapters_path = video_dir / "chapters.md"
        description = description_body
        if chapters_path.exists():
            description += "\n\n" + chapters_path.read_text()

        video_file_path = video_dir / f"{slug}.mp4"
        video_file: Optional[Path] = None
        if video_file_path.exists():
            video_file = video_file_path
        else:
            video_file = next(video_dir.glob("*.mp4"), None)
        if not video_file:
            console.print(f"[red]Video file not found in {video_dir}[/red]")
            continue

        thumbnail_filename = metadata.get("thumbnail-screenshot", "thumbnail.png")
        thumbnail_path: Path = pack_dir / slug / thumbnail_filename
        if not thumbnail_path.exists():
            thumbnail_path = video_dir / thumbnail_filename
        if not thumbnail_path.exists():
            thumbnail_path = video_dir / "thumbnail.png"

        console.print(f"  Title: {title}")
        console.print(f"  Description: {description[:100]}...")
        console.print(f"  Video: {video_file.name}")
        console.print(
            f"  Thumbnail: {thumbnail_path.name if thumbnail_path.exists() else 'not found'}"
        )

        if dry_run:
            console.print("[yellow]DRY RUN: Skipping actual upload[/yellow]")
            continue

        uploader = YouTubeUploader(campaign=campaign_name)

        console.print("[cyan]Uploading video...[/cyan]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Uploading", total=100)

            def update_progress(p: int) -> None:
                progress.update(task, completed=p)

            result = uploader.upload(
                video_file,
                title,
                description=description,
                privacy=final_privacy,
                playlist_id=playlist_id,
                progress_callback=update_progress,
            )

        if not result:
            console.print("[red]Video upload failed[/red]")
            continue

        video_id = result["id"]
        console.print(f"[green]Video uploaded: {result['url']}[/green]")

        if thumbnail_path.exists():
            console.print("[cyan]Uploading thumbnail...[/cyan]")
            if uploader.upload_thumbnail(video_id, thumbnail_path):
                console.print("[green]Thumbnail uploaded[/green]")
            else:
                console.print("[yellow]Thumbnail upload failed (continuing)[/yellow]")
        else:
            console.print("[yellow]No thumbnail found, skipping[/yellow]")

        captions_path = video_dir / "captions.vtt"
        if not captions_path.exists():
            captions_path = pack_dir / slug / "captions.vtt"
        if captions_path.exists():
            console.print("[cyan]Uploading captions...[/cyan]")
            if uploader.upload_captions(video_id, captions_path):
                console.print("[green]Captions uploaded[/green]")
            else:
                console.print("[yellow]Captions upload failed (continuing)[/yellow]")
        else:
            console.print("[yellow]No captions found, skipping[/yellow]")

        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / slug
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(video_dir), str(target))
        console.print(f"[green]Moved to uploaded: {slug}[/green]")
        console.print(f"[green]Upload complete: {result['url']}[/green]")


@app.command()
def auth(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
) -> None:
    """Authenticate with YouTube using OAuth Device Code Flow."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print(
            "[red]No campaign selected. Please specify --campaign or set a campaign context.[/red]"
        )
        raise typer.Exit(1)

    console.print(
        f"[cyan]Starting OAuth authentication for campaign: {campaign_name}[/cyan]"
    )
    authenticator = video_auth.DeviceCodeAuth()

    try:
        success = authenticator.authenticate(campaign_name)
        if success:
            console.print(
                "[green]Authentication complete! You can now upload videos.[/green]"
            )
        else:
            console.print("[red]Authentication failed. Please try again.[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error during authentication: {e}[/red]")
        raise typer.Exit(1)
