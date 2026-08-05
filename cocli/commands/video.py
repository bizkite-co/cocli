"""Video processing commands for cocli."""

import platform
import re
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
from cocli.core.video.job_runs import (
    save_video_job_run,
    write_last_normalize_pointer,
    write_last_package_pointer,
    write_last_upload_pointer,
)
from cocli.core.video.display_paths import print_accessible_path
from cocli.core.video.transcript_to_vtt import convert_transcript_to_vtt
from cocli.core.video import auth as video_auth
from cocli.core.text_utils import slugdotify
from cocli.models.campaigns.video_job_run import (
    KIND_TRANSCRIBE,
    VideoJobRun,
    VideoSttSettings,
)

app = typer.Typer(no_args_is_help=True)
console = Console()

# Windows drive path: D:\Video\file.mp4 or D:/Video/file.mp4
_WIN_DRIVE_PATH_RE = re.compile(r"^([A-Za-z]):[/\\](.*)$")

_ADD_IMPORT_HELP = """\
Add (import) an external video into the campaign raw queue.

Path forms:
  Linux/WSL:  /path/to/video.mp4  or  /mnt/d/Video/video.mp4
  Windows:    D:\\Video\\video.mp4  or  D:/Video/video.mp4
              On WSL, drive letters map to /mnt/<drive>/...

`import` is an explicit alias of `add`.

With --normalize: runs encode + STT (transcripts, chapters, captions) into
normalized/, then stops. Does not run package/upload; human review of
metadata/screenshots is still required before package.
"""


def resolve_video_path(path_str: str) -> Path:
    """Resolve a user-supplied video path (Linux or Windows/WSL style).

    On non-Windows hosts, ``D:\\Video\\file.mp4`` and ``D:/Video/file.mp4``
    map to ``/mnt/d/Video/file.mp4``.
    """
    cleaned = path_str.strip().strip('"').strip("'")
    match = _WIN_DRIVE_PATH_RE.match(cleaned)
    if match and platform.system() != "Windows":
        drive = match.group(1).lower()
        rest = match.group(2).replace("\\", "/")
        if rest:
            return Path(f"/mnt/{drive}") / rest
        return Path(f"/mnt/{drive}")
    return Path(cleaned)


def _hint_if_unmounted_drive(video_path: Path) -> None:
    """If path is under an empty /mnt/<letter>, suggest mounting the drive."""
    parts = video_path.parts
    if len(parts) < 3 or parts[0] != "/" or parts[1] != "mnt":
        return
    drive = parts[2]
    if len(drive) != 1 or not drive.isalpha():
        return
    mount_root = Path("/mnt") / drive
    if not mount_root.is_dir():
        return
    try:
        empty = not any(mount_root.iterdir())
    except OSError:
        return
    if empty:
        console.print(
            f"[yellow]Hint: /mnt/{drive} looks empty (drive not mounted?). "
            f"Try: sudo mount -t drvfs {drive.upper()}: /mnt/{drive}[/yellow]"
        )


def extract_screenshots_logic(video_path: Path) -> None:
    """Internal logic to extract screenshots."""
    console.print(f"Extracting screenshots from: {video_path.name}")

    # Use evenly spaced timestamps instead of scene detection
    # This is more reliable for longer videos
    duration = get_duration(str(video_path))

    # Get 5 evenly spaced timestamps (avoiding very end)
    num_screenshots = 5
    timestamps = [
        duration * (i + 1) / (num_screenshots + 1) for i in range(num_screenshots)
    ]

    # Extract at each timestamp
    for i, ts in enumerate(timestamps):
        output_file = video_path.parent / f"screenshot_{i + 1:03d}.png"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(ts),
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            str(output_file),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            console.print(
                f"[yellow]Failed to extract screenshot at {ts}s: {e.stderr.decode() if e.stderr else e}[/yellow]"
            )

    # Count how many we got
    existing = list(video_path.parent.glob("screenshot_*.png"))
    if existing:
        console.print(
            f"[green]Extracted {len(existing)} screenshots to {video_path.parent}[/green]"
        )
    else:
        console.print("[yellow]No screenshots extracted[/yellow]")


def get_video_queue_root(campaign_name: str) -> Path:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        raise ValueError(f"Campaign directory not found for: {campaign_name}")
    return campaign_dir / "video"


def _find_normalized_mp4(video_dir: Path) -> Optional[Path]:
    matches = sorted(p for p in video_dir.glob("*.mp4") if p.is_file())
    return matches[0] if matches else None


def _existing_transcripts(video_dir: Path) -> dict[str, str]:
    """Load any transcript_*.md already written in the normalized package."""
    return chapters.load_transcripts_from_dir(video_dir)


def transcribe_normalized_dir(
    campaign_name: str,
    video_dir: Path,
    *,
    job_run: Optional[VideoJobRun] = None,
    force: bool = False,
) -> dict[str, str]:
    """
    Run STT (+ chapters + captions) for a normalized video directory.

    This is the single transcription implementation used by normalize (always)
    and by package only when transcripts are missing (recovery / legacy).

    Returns the map of provider -> transcript markdown (including granular keys).
    """
    video_file = _find_normalized_mp4(video_dir)
    if video_file is None:
        raise FileNotFoundError(f"No .mp4 found in {video_dir}")

    if not force:
        existing = _existing_transcripts(video_dir)
        # Prefer reusing when we already have at least one primary transcript
        # (not only granular sidecar).
        primary = {
            k: v
            for k, v in existing.items()
            if not k.endswith("_granular")
        }
        if primary:
            console.print(
                f"[dim]Transcripts already present in {video_dir.name}; "
                f"skipping STT (use force to re-run).[/dim]"
            )
            return existing

    console.print(f"Transcribing {video_file.name}...")
    if job_run is not None:
        job_run.start_phase("transcribe")

    camp_cfg = load_campaign_config(campaign_name)
    provider = (
        camp_cfg.get("video", {})
        .get("transcription", {})
        .get("provider", "gemini")
    )
    transcriber_engine = transcriber.TranscriptionFactory.get_transcriber(provider)
    try:
        transcripts = transcriber_engine.transcribe(video_file, campaign_name)
    except Exception:
        if job_run is not None:
            job_run.end_phase("transcribe")
        raise

    if job_run is not None:
        # Record Whisper device when STT used Whisper (or dual).
        whisper_device = getattr(transcriber.WhisperTranscriber, "last_device", None)
        whisper_compute = getattr(
            transcriber.WhisperTranscriber, "last_compute_type", None
        )
        whisper_model = getattr(
            transcriber.WhisperTranscriber, "last_model_size", None
        )
        if whisper_device or provider in ("whisper", "both"):
            job_run.stt = VideoSttSettings(
                provider=provider,
                model=whisper_model,
                device=whisper_device,
                compute_type=whisper_compute,
            )
        else:
            job_run.stt = VideoSttSettings(provider=provider)

    for provider_name, transcript_text in transcripts.items():
        transcript_path = video_dir / f"transcript_{provider_name}.md"
        transcript_path.write_text(transcript_text, encoding="utf-8")
        console.print(f"[green]Saved transcript to {transcript_path.name}[/green]")

    if job_run is not None:
        job_run.end_phase("transcribe")

    picked = chapters.pick_primary_transcript(transcripts)
    if picked is not None:
        _provider_key, first_transcript = picked
        console.print("Generating chapters...")
        if job_run is not None:
            job_run.start_phase("chapters")
        try:
            chapters_path = chapters.write_chapters_for_dir(
                video_dir,
                campaign_name,
                transcripts=transcripts,
            )
            console.print(f"[green]Saved chapters to {chapters_path.name}[/green]")
        except Exception as e:
            console.print(f"[yellow]Chapter generation failed: {e}[/yellow]")
            if job_run is not None:
                job_run.add_error(f"Chapter generation failed: {e}")
        finally:
            if job_run is not None:
                job_run.end_phase("chapters")

        console.print("Generating VTT closed captions...")
        if job_run is not None:
            job_run.start_phase("captions")
        try:
            vtt_path = video_dir / "captions.vtt"
            convert_transcript_to_vtt(first_transcript, vtt_path)
            console.print(f"[green]Saved captions to {vtt_path.name}[/green]")
        except Exception as e:
            console.print(f"[yellow]VTT generation failed: {e}[/yellow]")
            if job_run is not None:
                job_run.add_error(f"VTT generation failed: {e}")
        finally:
            if job_run is not None:
                job_run.end_phase("captions")

    return transcripts


def normalize_one_video(
    campaign_name: str,
    video_file: Path,
    *,
    encode_profile: Optional[str] = None,
) -> bool:
    """Normalize a single raw video into the normalized queue.

    On success, removes ``video_file`` from raw/. Returns True on success.
    Writes a job-run receipt under ``video/job_runs/{YYYYMMDD}/{run_id}.json``
    and mirrors it to ``normalized/{slug}/last-normalize-run.json`` on success.
    """
    queue_root = get_video_queue_root(campaign_name)
    norm_dir = queue_root / "normalized"
    norm_dir.mkdir(parents=True, exist_ok=True)

    slug = video_file.stem
    job_run = VideoJobRun.start_normalize(campaign_name, slug)
    receipt_path = save_video_job_run(queue_root, job_run)
    console.print(f"[dim]Job run: {receipt_path}[/dim]")

    console.print(f"Processing: {video_file.name}")

    video_dir = norm_dir / slug
    video_dir.mkdir(parents=True, exist_ok=True)

    output_path = video_dir / f"{video_file.name}"
    console.print(f"Normalizing {video_file.name} to {output_path.name}...")

    try:
        duration = get_duration(str(video_file))
    except Exception as e:
        job_run.mark_failed(str(e))
        save_video_job_run(queue_root, job_run)
        console.print(f"[red]Failed to probe duration: {e}[/red]")
        return False

    result: Optional[Path] = None
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Normalizing {video_file.name}", total=duration)

            def callback(current_sec: float, total_sec: float) -> None:
                progress.update(task, completed=current_sec)

            camp_cfg = load_campaign_config(campaign_name)
            video_cfg = camp_cfg.get("video", {}) or {}
            loudness_cfg = video_cfg.get("loudness", {})
            denoise_cfg = video_cfg.get("denoise", {})
            result, _stats = normalize_video(
                video_file,
                output_path,
                callback=callback,
                loudness_config=loudness_cfg,
                denoise_config=denoise_cfg,
                job_run=job_run,
                encode_profile=encode_profile,
                video_config=video_cfg if isinstance(video_cfg, dict) else None,
            )
            # Persist mid-run phase updates after encode returns
            save_video_job_run(queue_root, job_run)
    except Exception as e:
        job_run.mark_failed(str(e))
        receipt_path = save_video_job_run(queue_root, job_run)
        console.print(f"[red]Failed to normalize {video_file.name}: {e}[/red]")
        console.print(f"[dim]Job run: {receipt_path}[/dim]")
        return False

    if not result:
        job_run.mark_failed(job_run.errors[-1] if job_run.errors else "normalize failed")
        receipt_path = save_video_job_run(queue_root, job_run)
        console.print(f"[red]Failed to normalize {video_file.name}[/red]")
        console.print(f"[dim]Job run: {receipt_path}[/dim]")
        return False

    # Remove original from raw/ ONLY after success
    video_file.unlink()

    md_file = video_dir / f"{slug}.md"
    if not md_file.exists():
        with open(md_file, "w") as f:
            f.write("---\n")
            f.write('title: ""\n')
            f.write('thumbnail-text: ""\n')
            f.write('thumbnail-style: ""\n')
            f.write("draft: true\n")
            f.write("---\n\n")

    try:
        job_run.start_phase("screenshots")
        extract_screenshots_logic(result)
        job_run.end_phase("screenshots")
    except Exception as e:
        # Encode already succeeded; do not fail the whole job for screenshots.
        job_run.end_phase("screenshots")
        job_run.add_error(f"Screenshot extraction failed: {e}")
        console.print(f"[yellow]Screenshot extraction failed: {e}[/yellow]")

    # STT is part of normalize (single pipeline with encode).
    try:
        transcribe_normalized_dir(
            campaign_name, video_dir, job_run=job_run, force=False
        )
        save_video_job_run(queue_root, job_run)
    except Exception as e:
        job_run.mark_failed(f"Transcription failed: {e}")
        receipt_path = save_video_job_run(queue_root, job_run)
        console.print(f"[red]Transcription failed: {e}[/red]")
        console.print(
            "[yellow]Encoded video was kept in normalized/; re-run STT with:[/yellow]"
        )
        console.print(
            f"  cocli video transcribe {slug} -c {campaign_name}"
        )
        print_accessible_path(console, "Folder:", video_dir)
        print_accessible_path(console, "Receipt:", receipt_path, style="dim")
        return False

    job_run.mark_completed()
    receipt_path = save_video_job_run(queue_root, job_run)
    write_last_normalize_pointer(
        video_dir, job_run, receipt_path=receipt_path
    )

    console.print(f"[green]Normalized (+ STT): {slug}[/green]")
    if job_run.duration_seconds is not None:
        console.print(f"[dim]Elapsed: {job_run.duration_seconds:.1f}s[/dim]")
    # Prefer Windows/UNC form for Explorer + VLC on a Windows host (WSL).
    print_accessible_path(console, "Video:", result)
    print_accessible_path(console, "Folder:", video_dir)
    print_accessible_path(console, "Receipt:", receipt_path, style="dim")
    return True


def _add_video_to_raw(
    campaign_name: str,
    video: str,
    *,
    do_normalize: bool,
    encode_profile: Optional[str] = None,
) -> None:
    """Copy an external video into raw/, optionally normalize only that file."""
    raw_dir = get_video_queue_root(campaign_name) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    video_path = resolve_video_path(video)
    if not video_path.exists():
        _hint_if_unmounted_drive(video_path)
        console.print(f"[red]File not found: {video_path}[/red]")
        raise typer.Exit(1)

    safe_name = slugdotify(video_path.name)
    dest = raw_dir / safe_name

    shutil.copy2(video_path, dest)
    console.print(f"[green]Added {safe_name} to raw queue.[/green]")

    if do_normalize:
        if not normalize_one_video(
            campaign_name, dest, encode_profile=encode_profile
        ):
            raise typer.Exit(1)


# Stacked decorators register the same command under both names (import = alias of add).
@app.command("import", no_args_is_help=True, help=_ADD_IMPORT_HELP)
@app.command("add", no_args_is_help=True, help=_ADD_IMPORT_HELP)
def add(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    video: str = typer.Argument(
        ...,
        help=(
            "Path to video file (Linux /path/to/file.mp4 or Windows "
            "D:\\\\Video\\\\file.mp4 / D:/Video/file.mp4)"
        ),
    ),
    do_normalize: bool = typer.Option(
        False,
        "--normalize",
        help=(
            "After adding, normalize + transcribe this video only "
            "(encode, STT, chapters, captions; does not run package)"
        ),
    ),
    encode_profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help=(
            "Encode profile: publish (default, slow/CRF18) or draft "
            "(faster; see docs/pipeline/video-encode-profiles.md)"
        ),
    ),
) -> None:
    """Add (import) an external video into the campaign raw queue."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    try:
        _add_video_to_raw(
            campaign_name,
            video,
            do_normalize=do_normalize,
            encode_profile=encode_profile,
        )
    except typer.Exit:
        raise
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
    encode_profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help=(
            "Encode profile: publish (default, quality for UI/screencasts) or "
            "draft (faster). Campaign video.encode.profile used when omitted."
        ),
    ),
) -> None:
    """Normalize + transcribe videos in the raw queue (encode, STT, chapters, captions)."""
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

        files = list(raw_dir.glob("*.mp4"))
        if not files:
            console.print(f"[yellow]No videos found in {raw_dir}[/yellow]")
            return

        for video_file in files:
            normalize_one_video(
                campaign_name, video_file, encode_profile=encode_profile
            )

    except Exception:
        import traceback

        console.print("[red]Error during normalization:[/red]")
        console.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command("chapters", no_args_is_help=True)
def chapters_cmd(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    video_slug: str = typer.Argument(
        ..., help="Video slug (directory name under normalized/)"
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="Transcript key to use (e.g. whisper). Default: prefer whisper, then others",
    ),
    also_packaged: bool = typer.Option(
        False,
        "--also-packaged",
        help="Also write chapters.md under packaged/{slug} when that dir exists",
    ),
) -> None:
    """
    Regenerate chapters.md from existing transcripts (no Whisper / no encode).

    Recovery when chapter gen failed (e.g. expired Gemini auth) after STT
    already succeeded. Prefer this over ``video transcribe --force``.
    """
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    queue_root = get_video_queue_root(campaign_name)
    video_dir = queue_root / "normalized" / video_slug
    if not video_dir.is_dir():
        console.print(f"[red]Normalized directory not found: {video_dir}[/red]")
        raise typer.Exit(1)

    try:
        console.print(
            f"Generating chapters for {video_slug} (from existing transcripts)..."
        )
        chapters_path = chapters.write_chapters_for_dir(
            video_dir, campaign_name, provider=provider
        )
        console.print(f"[green]Saved chapters to {chapters_path}[/green]")
        print_accessible_path(console, "Chapters:", chapters_path)

        if also_packaged:
            pack_dir = queue_root / "packaged" / video_slug
            if pack_dir.is_dir():
                # Prefer reusing normalized transcripts if packaged has none.
                pack_transcripts = chapters.load_transcripts_from_dir(pack_dir)
                if not chapters.pick_primary_transcript(pack_transcripts):
                    pack_transcripts = chapters.load_transcripts_from_dir(video_dir)
                pack_path = chapters.write_chapters_for_dir(
                    pack_dir,
                    campaign_name,
                    provider=provider,
                    transcripts=pack_transcripts,
                )
                console.print(
                    f"[green]Also updated packaged chapters: {pack_path}[/green]"
                )
            else:
                console.print(
                    f"[yellow]Packaged dir not found ({pack_dir}); "
                    f"skipped --also-packaged[/yellow]"
                )
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Chapter generation failed: {e}[/red]")
        raise typer.Exit(1)


@app.command(no_args_is_help=True)
def transcribe(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    video_slug: str = typer.Argument(
        ..., help="Video slug (directory name under normalized/)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Re-run STT even if transcripts already exist"
    ),
) -> None:
    """
    Run STT (+ chapters + captions) on an already-normalized video.

    Recovery path when encode finished without transcription. Prefer letting
    ``normalize`` / ``add --normalize`` do STT in one step for new videos.
    For chapters-only recovery after STT succeeded, use ``video chapters``.
    """
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    queue_root = get_video_queue_root(campaign_name)
    video_dir = queue_root / "normalized" / video_slug
    if not video_dir.is_dir():
        console.print(f"[red]Normalized directory not found: {video_dir}[/red]")
        raise typer.Exit(1)

    job_run = VideoJobRun.start_normalize(campaign_name, video_slug)
    job_run.kind = KIND_TRANSCRIBE
    job_run.notes = "Recovery STT on existing normalized package"
    receipt_path = save_video_job_run(queue_root, job_run)
    console.print(f"[dim]Job run: {receipt_path}[/dim]")

    try:
        transcribe_normalized_dir(
            campaign_name, video_dir, job_run=job_run, force=force
        )
        job_run.mark_completed()
        receipt_path = save_video_job_run(queue_root, job_run)
        write_last_normalize_pointer(
            video_dir, job_run, receipt_path=receipt_path
        )
        console.print(f"[green]Transcribed: {video_slug}[/green]")
        if job_run.duration_seconds is not None:
            console.print(f"[dim]Elapsed: {job_run.duration_seconds:.1f}s[/dim]")
        print_accessible_path(console, "Folder:", video_dir)
        print_accessible_path(console, "Receipt:", receipt_path, style="dim")
    except Exception as e:
        job_run.mark_failed(str(e))
        receipt_path = save_video_job_run(queue_root, job_run)
        console.print(f"[red]Transcription failed: {e}[/red]")
        print_accessible_path(console, "Receipt:", receipt_path, style="dim")
        raise typer.Exit(1)


def package_one_video(
    campaign_name: str,
    video_dir: Path,
    pack_dir: Path,
    *,
    force: bool = False,
) -> bool:
    """
    Package a single normalized video dir into packaged/.

    Writes ``video/job_runs/...`` with kind ``video.package`` and mirrors
    ``last-package-run.json`` next to the packaged product on success.
    STT only runs when transcripts are missing (shared helper).
    """
    queue_root = get_video_queue_root(campaign_name)
    slug = video_dir.name
    target_video_dir = pack_dir / slug

    if target_video_dir.exists() and not force:
        console.print(
            f"[yellow]Skipping: {slug} already packaged. Use --force to overwrite.[/yellow]"
        )
        return False

    job_run = VideoJobRun.start_package(campaign_name, slug)
    receipt_path = save_video_job_run(queue_root, job_run)
    console.print(f"[dim]Job run: {receipt_path}[/dim]")
    console.print(f"Packaging: {slug}")
    console.print(f"[dim]Source: {video_dir}[/dim]")
    console.print(f"[dim]Destination: {target_video_dir}[/dim]")

    if _find_normalized_mp4(video_dir) is None:
        job_run.mark_failed(f"No .mp4 in {video_dir}")
        receipt_path = save_video_job_run(queue_root, job_run)
        console.print(f"[red]No .mp4 in {video_dir}; skipping[/red]")
        console.print(f"[dim]Job run: {receipt_path}[/dim]")
        return False

    target_video_dir.mkdir(parents=True, exist_ok=True)

    # STT if missing (legacy / failed-normalize recovery); shared helper — not a second pipeline
    try:
        transcribe_normalized_dir(
            campaign_name, video_dir, job_run=job_run, force=False
        )
        save_video_job_run(queue_root, job_run)
    except Exception as e:
        job_run.add_error(f"STT failed: {e}")
        save_video_job_run(queue_root, job_run)
        console.print(
            f"[yellow]STT failed for {slug}: {e}; packaging remaining assets[/yellow]"
        )

    try:
        job_run.start_phase("copy_assets")
        for item in video_dir.iterdir():
            if item.is_dir():
                shutil.copytree(
                    item, target_video_dir / item.name, dirs_exist_ok=True
                )
            else:
                shutil.copy2(item, target_video_dir / item.name)
        job_run.end_phase("copy_assets")
    except Exception as e:
        job_run.end_phase("copy_assets")
        job_run.mark_failed(f"Copy assets failed: {e}")
        receipt_path = save_video_job_run(queue_root, job_run)
        console.print(f"[red]Failed to copy assets for {slug}: {e}[/red]")
        console.print(f"[dim]Job run: {receipt_path}[/dim]")
        return False

    try:
        job_run.start_phase("thumbnail")
        thumbnailer.process_thumbnail(video_dir, target_video_dir)
        job_run.end_phase("thumbnail")
    except Exception as e:
        job_run.end_phase("thumbnail")
        job_run.add_error(f"Thumbnail failed: {e}")
        console.print(f"[yellow]Thumbnail failed for {slug}: {e}[/yellow]")

    job_run.mark_completed()
    receipt_path = save_video_job_run(queue_root, job_run)
    write_last_package_pointer(
        target_video_dir, job_run, receipt_path=receipt_path
    )

    console.print(f"[green]Packaged: {slug}[/green]")
    if job_run.duration_seconds is not None:
        console.print(f"[dim]Elapsed: {job_run.duration_seconds:.1f}s[/dim]")
    print_accessible_path(console, "Folder:", target_video_dir)
    print_accessible_path(console, "Receipt:", receipt_path, style="dim")
    return True


@app.command()
def package(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing packaged data"
    ),
) -> None:
    """
    Package videos from the normalized queue.

    Copies normalized assets to packaged/ and builds thumbnails. Transcription
    is expected from normalize; if transcripts are missing, STT is run once
    via the shared helper (not a second pipeline).
    """
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print("[red]No campaign specified.[/red]")
        raise typer.Exit(1)

    try:
        queue_root = get_video_queue_root(campaign_name)
        norm_dir = queue_root / "normalized"
        pack_dir = queue_root / "packaged"
        pack_dir.mkdir(parents=True, exist_ok=True)

        if not norm_dir.exists():
            console.print(f"[yellow]Normalized directory not found: {norm_dir}[/yellow]")
            return

        for video_dir in sorted(norm_dir.iterdir()):
            if not video_dir.is_dir():
                continue
            package_one_video(
                campaign_name, video_dir, pack_dir, force=force
            )

    except Exception:
        import traceback

        console.print("[red]Error during packaging:[/red]")
        console.print(traceback.format_exc())
        raise typer.Exit(1)


@app.command(no_args_is_help=True)
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


@app.command(no_args_is_help=True)
def extract_screenshots(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    video: str = typer.Argument(..., help="Video file name or path"),
) -> None:
    """Extract candidate screenshots from a video."""

    video_path: Optional[Path] = None
    direct = resolve_video_path(video)
    # 2. If not a direct path, fallback to campaign search
    if not direct.exists():
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
    else:
        video_path = direct

    if video_path is None or not video_path.exists():
        console.print(f"[red]Video file not found: {video}[/red]")
        raise typer.Exit(1)

    extract_screenshots_logic(video_path)


def upload_one_video(
    campaign_name: str,
    video_dir: Path,
    pack_dir: Path,
    upload_dir: Path,
    *,
    privacy: str,
    force_privacy: bool,
    dry_run: bool,
) -> bool:
    """
    Upload a single packaged video to YouTube.

    Writes ``video/job_runs/...`` with kind ``video.upload`` and mirrors
    ``last-upload-run.json`` next to the uploaded product on success.
    """
    queue_root = get_video_queue_root(campaign_name)
    slug = video_dir.name
    console.print(f"\n[cyan]Processing: {slug}[/cyan]")

    if not video_dir.is_dir():
        console.print(f"[red]Packaged directory not found: {video_dir}[/red]")
        return False

    job_run = VideoJobRun.start_upload(campaign_name, slug)
    receipt_path = save_video_job_run(queue_root, job_run)
    console.print(f"[dim]Job run: {receipt_path}[/dim]")

    try:
        job_run.start_phase("prepare_metadata")

        md_file = video_dir / "metadata.md"
        if not md_file.exists():
            # Fallback to old naming convention
            md_file = video_dir / f"{slug}.md"
        if not md_file.exists():
            job_run.end_phase("prepare_metadata")
            job_run.mark_failed(f"Metadata file not found: {md_file}")
            receipt_path = save_video_job_run(queue_root, job_run)
            console.print(f"[red]Metadata file not found: {md_file}[/red]")
            console.print(f"[dim]Job run: {receipt_path}[/dim]")
            return False

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
            # Sanitize forbidden characters for YouTube API (no '<' or '>')
            description = description.replace("<", "less than").replace(
                ">", "greater than"
            )
            chapters_text: str = (
                chapters_path.read_text()
                .replace("<", "less than")
                .replace(">", "greater than")
            )

            if len(description) + len(chapters_text) + 2 > 5000:
                allowed_body_len = 5000 - len(chapters_text) - 10

                console.print(
                    f"[yellow]Warning: Video description is too long. "
                    f"Truncating body text to {allowed_body_len} characters "
                    f"to fit chapters.[/yellow]"
                )
                description = description[:allowed_body_len] + "\n..."
            description += "\n\n" + chapters_text
        else:
            description = description.replace("<", "less than").replace(
                ">", "greater than"
            )
            if len(description) > 5000:
                console.print(
                    "[yellow]Warning: Video description is too long. "
                    "Truncating to 5000 characters.[/yellow]"
                )
                description = description[:4997] + "..."

        video_file_path = video_dir / f"{slug}.mp4"
        video_file: Optional[Path] = None
        if video_file_path.exists():
            video_file = video_file_path
        else:
            video_file = next(video_dir.glob("*.mp4"), None)
        if not video_file:
            job_run.end_phase("prepare_metadata")
            job_run.mark_failed(f"Video file not found in {video_dir}")
            receipt_path = save_video_job_run(queue_root, job_run)
            console.print(f"[red]Video file not found in {video_dir}[/red]")
            console.print(f"[dim]Job run: {receipt_path}[/dim]")
            return False

        # Prefer processed overlay thumbnail; screenshot name is only the source art.
        thumbnail_path = pack_dir / slug / "thumbnail.png"
        if not thumbnail_path.exists():
            thumbnail_path = video_dir / "thumbnail.png"
        if not thumbnail_path.exists():
            # Legacy fallback: raw screenshot named in metadata
            screenshot_name = metadata.get("thumbnail-screenshot")
            if screenshot_name:
                candidate = pack_dir / slug / str(screenshot_name)
                if not candidate.exists():
                    candidate = video_dir / str(screenshot_name)
                if candidate.exists():
                    thumbnail_path = candidate

        console.print(f"  Title: {title}")
        console.print(f"  Description: {description[:100]}...")
        console.print(f"  Video: {video_file.name}")
        console.print(
            f"  Thumbnail: {thumbnail_path.name if thumbnail_path.exists() else 'not found'}"
        )
        job_run.end_phase("prepare_metadata")
        save_video_job_run(queue_root, job_run)

        if dry_run:
            job_run.notes = "dry_run — upload skipped"
            job_run.mark_completed()
            receipt_path = save_video_job_run(queue_root, job_run)
            console.print("[yellow]DRY RUN: Skipping actual upload[/yellow]")
            console.print(f"[dim]Job run: {receipt_path}[/dim]")
            return True

        uploader = YouTubeUploader(campaign=campaign_name)

        console.print("[cyan]Uploading video...[/cyan]")
        job_run.start_phase("upload_video")
        try:
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
        except Exception as e:
            job_run.end_phase("upload_video")
            job_run.mark_failed(f"Video upload failed: {e}")
            receipt_path = save_video_job_run(queue_root, job_run)
            console.print(f"[red]Video upload failed: {e}[/red]")
            console.print(f"[dim]Job run: {receipt_path}[/dim]")
            return False

        job_run.end_phase("upload_video")

        if not result:
            job_run.mark_failed("Video upload failed")
            receipt_path = save_video_job_run(queue_root, job_run)
            console.print("[red]Video upload failed[/red]")
            console.print(f"[dim]Job run: {receipt_path}[/dim]")
            return False

        video_id = result["id"]
        console.print(f"[green]Video uploaded: {result['url']}[/green]")
        job_run.notes = f"youtube_id={video_id} url={result.get('url', '')}"
        save_video_job_run(queue_root, job_run)

        if thumbnail_path.exists():
            console.print("[cyan]Uploading thumbnail...[/cyan]")
            job_run.start_phase("upload_thumbnail")
            try:
                if uploader.upload_thumbnail(video_id, thumbnail_path):
                    console.print("[green]Thumbnail uploaded[/green]")
                else:
                    job_run.add_error("Thumbnail upload failed")
                    console.print(
                        "[yellow]Thumbnail upload failed (continuing)[/yellow]"
                    )
            except Exception as e:
                job_run.add_error(f"Thumbnail upload failed: {e}")
                console.print(
                    f"[yellow]Thumbnail upload failed (continuing): {e}[/yellow]"
                )
            finally:
                job_run.end_phase("upload_thumbnail")
        else:
            console.print("[yellow]No thumbnail found, skipping[/yellow]")

        captions_path = video_dir / "captions.vtt"
        if not captions_path.exists():
            captions_path = pack_dir / slug / "captions.vtt"
        if captions_path.exists():
            console.print("[cyan]Uploading captions...[/cyan]")
            job_run.start_phase("upload_captions")
            try:
                if uploader.upload_captions(video_id, captions_path):
                    console.print("[green]Captions uploaded[/green]")
                else:
                    job_run.add_error("Captions upload failed")
                    console.print(
                        "[yellow]Captions upload failed (continuing)[/yellow]"
                    )
            except Exception as e:
                job_run.add_error(f"Captions upload failed: {e}")
                console.print(
                    f"[yellow]Captions upload failed (continuing): {e}[/yellow]"
                )
            finally:
                job_run.end_phase("upload_captions")
        else:
            console.print("[yellow]No captions found, skipping[/yellow]")

        job_run.start_phase("move_to_uploaded")
        try:
            upload_dir.mkdir(parents=True, exist_ok=True)
            target = upload_dir / slug
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(video_dir), str(target))
            job_run.end_phase("move_to_uploaded")
        except Exception as e:
            job_run.end_phase("move_to_uploaded")
            job_run.mark_failed(f"Move to uploaded failed: {e}")
            receipt_path = save_video_job_run(queue_root, job_run)
            console.print(f"[red]Moved to uploaded failed: {e}[/red]")
            console.print(f"[dim]Job run: {receipt_path}[/dim]")
            return False

        job_run.mark_completed()
        receipt_path = save_video_job_run(queue_root, job_run)
        write_last_upload_pointer(target, job_run, receipt_path=receipt_path)

        console.print(f"[green]Moved to uploaded: {slug}[/green]")
        console.print(f"[green]Upload complete: {result['url']}[/green]")
        if job_run.duration_seconds is not None:
            console.print(f"[dim]Elapsed: {job_run.duration_seconds:.1f}s[/dim]")
        print_accessible_path(console, "Folder:", target)
        print_accessible_path(console, "Receipt:", receipt_path, style="dim")
        return True

    except Exception as e:
        # Ensure any open phases are closed and receipt is failed.
        for phase_name, phase in list(job_run.phases.items()):
            if phase.ended_at is None:
                job_run.end_phase(phase_name)
        job_run.mark_failed(str(e))
        receipt_path = save_video_job_run(queue_root, job_run)
        console.print(f"[red]Upload failed for {slug}: {e}[/red]")
        console.print(f"[dim]Job run: {receipt_path}[/dim]")
        return False


@app.command()
def upload(
    campaign: Optional[str] = typer.Option(
        None, "-c", "--campaign", help="Campaign name"
    ),
    video_slug: Optional[str] = typer.Option(
        None, "-v", "--video", help="Video slug to upload (from packaged/)"
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
    """Upload a video to YouTube using metadata from the packaged queue."""
    campaign_name = campaign or get_campaign()
    if not campaign_name:
        console.print(
            "[red]No campaign selected. Please specify --campaign or set a campaign context.[/red]"
        )
        raise typer.Exit(1)

    queue_root = get_video_queue_root(campaign_name)
    pack_dir = queue_root / "packaged"
    upload_dir = queue_root / "uploaded"

    if video_slug:
        video_dirs = [pack_dir / video_slug]
    else:
        if not pack_dir.exists():
            console.print(f"[yellow]Packaged directory not found: {pack_dir}[/yellow]")
            return
        video_dirs = sorted(d for d in pack_dir.iterdir() if d.is_dir())

    for video_dir in video_dirs:
        upload_one_video(
            campaign_name,
            video_dir,
            pack_dir,
            upload_dir,
            privacy=privacy,
            force_privacy=force_privacy,
            dry_run=dry_run,
        )


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
