import json
import subprocess
import re
import logging
from pathlib import Path
from typing import Optional, Tuple, Callable, Dict

logger = logging.getLogger(__name__)


def get_h264_encoder() -> str:
    """Detects available H.264 encoder."""
    try:
        result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
        if "h264_nvenc" in result.stdout:
            return "h264_nvenc"
        return "libx264"
    except Exception:
        return "libx264"


def get_duration(input_file: str | Path) -> float:
    """Get video duration using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(input_file),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def parse_loudness_stats(stderr_output: str) -> Optional[Dict[str, float]]:
    """Parse loudness statistics from FFmpeg stderr output."""
    try:
        # Find the JSON block - look for "Input" section which contains measured values
        # FFmpeg loudnorm outputs: {"Input": {...}, "Output": {...}}
        start = stderr_output.find('"Input"')
        if start == -1:
            # Try fallback to first brace
            start = stderr_output.find("{")

        if start == -1:
            logger.error("No JSON block found in ffmpeg output")
            return None

        # Find the matching closing brace
        end = stderr_output.rfind("}")
        if end == -1 or end <= start:
            logger.error("Could not find complete JSON block")
            return None

        json_str = stderr_output[start : end + 1]

        # Debug log the raw JSON for troubleshooting
        logger.debug(f"Loudness JSON: {json_str[:500]}...")

        data = json.loads(json_str)

        # Extract only the Input section (measured values before normalization)
        input_data = data.get("Input", data)  # Fallback to whole block if no Input

        # FFmpeg outputs keys like "input_i", "input_lra", "input_tp", "input_thresh"
        # Map to the keys expected by normalize_video
        key_map = {
            "input_i": "input_i",
            "input_lra": "input_lra",
            "input_tp": "input_tp",
            "input_thresh": "input_thresh",
        }

        result = {}
        for ff_key, our_key in key_map.items():
            value = input_data.get(ff_key)
            if value is not None:
                try:
                    result[our_key] = float(value)
                except (ValueError, TypeError):
                    logger.warning(f"Skipping non-numeric value for {ff_key}: {value}")

        # Get target_offset - it may be in Output section or at top level
        output_data = data.get("Output", {})
        if "target_offset" in output_data:
            try:
                result["target_offset"] = float(output_data["target_offset"])
            except (ValueError, TypeError):
                pass
        elif "target_offset" in data:
            try:
                result["target_offset"] = float(data["target_offset"])
            except (ValueError, TypeError):
                pass

        if not result:
            logger.error(
                f"No valid numeric loudness values found in JSON. Keys found: {list(input_data.keys())}"
            )
            return None

        # Log what we found for debugging
        logger.info(f"Parsed loudness stats: {result}")

        return result

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(
            f"Failed to parse loudness stats: {e}. Output snippet: {stderr_output[:500]}..."
        )
        return None


def normalize_video(
    input_path: str | Path,
    output_path: Optional[str | Path] = None,
    callback: Optional[Callable[[float, float], None]] = None,
    loudness_config: Optional[Dict[str, float]] = None,
    denoise_config: Optional[Dict[str, int]] = None,
) -> Tuple[Optional[Path], Optional[Dict[str, float]]]:
    """
    Normalize video audio and compress for YouTube/Social.

    Args:
        input_path: Source video file
        output_path: Destination (default: {name}_normalized.mp4)
        callback: Progress callback(current, total_seconds) or None
        loudness_config: Optional dict with keys I, TP, LRA
        denoise_config: Optional dict with keys nr (noise reduction dB)

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

    loudness_config = loudness_config or {"I": -14, "TP": -1.5, "LRA": 11}
    target_i = loudness_config.get("I", -14)
    target_tp = loudness_config.get("TP", -1.5)
    target_lra = loudness_config.get("LRA", 11)

    denoise_config = denoise_config or {"nr": 10}
    nr = denoise_config.get("nr", 10)

    # Phase 1: Analyze loudness
    logger.info(f"Analyzing {input_path.name}...")
    analyze_cmd = [
        "ffmpeg",
        "-i",
        str(input_path),
        "-af",
        f"afftdn=nr={nr}:nt=w,loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json",
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

    encoder = get_h264_encoder()
    codec_args = []
    if encoder == "h264_nvenc":
        codec_args = ["-c:v", "h264_nvenc", "-preset", "p4", "-tune", "hq", "-cq", "20"]
    else:
        codec_args = ["-c:v", "libx264", "-crf", "18", "-preset", "slow"]

    af = (
        f"afftdn=nr={nr}:nt=w,loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:linear=true:"
        f"measured_I={stats['input_i']}:measured_LRA={stats['input_lra']}:"
        f"measured_tp={stats['input_tp']}:measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}"
    )

    duration = get_duration(input_path)

    cmd = (
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-af",
            af,
        ]
        + codec_args
        + [
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
    )

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    )

    time_regex = re.compile(r"out_time_ms=(\d+)")
    if process.stdout:
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
    ) -> None:
        """Normalize video audio for social media."""
        out_path, stats = normalize_video(input, output)
        if out_path:
            typer.echo(f"Success: {out_path}")
        else:
            raise typer.Exit(1)
