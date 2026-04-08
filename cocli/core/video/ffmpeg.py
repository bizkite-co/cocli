"""Video normalization using FFmpeg."""

import json
import subprocess
import sys
import os
import re
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def get_duration(input_file: str) -> float:
    """Get video duration using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        input_file,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def parse_loudness_stats(stderr_output: str) -> Optional[dict]:
    """Parse loudness statistics from FFmpeg stderr output."""
    try:
        lines = stderr_output.split("\n")
        json_start = next(i for i, line in enumerate(lines) if "{" in line)
        return json.loads("\n".join(lines[json_start:]))
    except (StopIteration, json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse loudness stats: {e}")
        return None


def normalize_video(
    input_path: str | Path,
    output_path: Optional[str | Path] = None,
    callback: Optional[callable] = None,
) -> Tuple[Optional[Path], Optional[dict]]:
    """
    Normalize video audio and compress for YouTube/Social.

    Args:
        input_path: Source video file
        output_path: Destination (default: {name}_normalized.mp4)
        callback: Progress callback(current, total_seconds) or None

    Returns:
        (output_path, stats) or (None, None) on failure
    """
    input_path = Path(input_path)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return None, None

    if not output_path:
        output_path = (
            input_path.parent / f"{input_path.stem}_normalized{input_path.suffix}"
        )
    else:
        output_path = Path(output_path)

    # Phase 1: Analyze loudness
    logger.info(f"Analyzing {input_path.name}...")
    analyze_cmd = [
        "ffmpeg",
        "-i",
        str(input_path),
        "-af",
        "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(analyze_cmd, capture_output=True, text=True)

    stats = parse_loudness_stats(result.stderr)
    if not stats:
        logger.error("Could not parse loudness statistics")
        return None, None

    # Phase 2: Normalize and compress
    logger.info("Normalizing and compressing...")

    af = (
        f"loudnorm=I=-14:TP=-1.5:LRA=11:linear=true:"
        f"measured_I={stats['input_i']}:measured_LRA={stats['input_lra']}:"
        f"measured_tp={stats['input_tp']}:measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}"
    )

    duration = get_duration(input_path)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-af",
        af,
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "slow",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-progress",
        "pipe:1",
        str(output_path),
    ]

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    )

    time_regex = re.compile(r"out_time_ms=(\d+)")
    while True:
        line = process.stdout.readline()
        if not line:
            if process.poll() is not None:
                break
            continue

        match = time_regex.search(line)
        if match and callback:
            current_sec = int(match.group(1)) / 1000000.0
            callback(current_sec, duration)

    if output_path.exists():
        logger.info(f"Done! Saved to: {output_path}")
        return output_path, stats

    logger.error("Output file not created")
    return None, stats


if __name__ == "__main__":
    import typer

    app = typer.Typer()

    @app.command()
    def normalize(
        input: str = typer.Argument(..., help="Input video file"),
        output: str = typer.Option(None, "-o", "--output", help="Output file"),
    ):
        """Normalize video audio for social media."""
        out_path, stats = normalize_video(input, output)
        if out_path:
            typer.echo(f"Success: {out_path}")
        else:
            raise typer.Exit(1)
