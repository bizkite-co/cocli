import json
import subprocess
import re
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Tuple, Callable, Dict

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from cocli.models.campaigns.video_job_run import VideoJobRun


def _nvenc_is_usable() -> Tuple[bool, Optional[str]]:
    """Return (usable, failure_reason) for h264_nvenc runtime probe."""
    probe = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "nullsrc=s=256x256:d=0.1",
            "-frames:v",
            "1",
            "-c:v",
            "h264_nvenc",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        err = (probe.stderr or probe.stdout or "").strip()
        reason = err[-300:] if err else f"exit={probe.returncode}"
        logger.warning(
            "h264_nvenc is listed but unusable; falling back to libx264. %s",
            reason,
        )
        return False, reason
    return True, None


def select_h264_encoder() -> Tuple[str, Optional[str], Optional[str]]:
    """
    Choose H.264 encoder.

    Returns:
        (encoder, encoder_requested, fallback_reason)
        encoder_requested is set when nvenc was preferred but unusable.
    """
    try:
        result = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
        if "h264_nvenc" in result.stdout:
            usable, reason = _nvenc_is_usable()
            if usable:
                return "h264_nvenc", None, None
            return "libx264", "h264_nvenc", reason
        return "libx264", None, None
    except Exception as e:
        return "libx264", None, str(e)


def get_h264_encoder() -> str:
    """Detect a usable H.264 encoder (prefer nvenc only if it actually works)."""
    encoder, _requested, _reason = select_h264_encoder()
    return encoder


def probe_video_identity(input_file: str | Path) -> Dict[str, Any]:
    """Best-effort duration/size/dimensions for job-run receipts."""
    path = Path(input_file)
    identity: Dict[str, Any] = {"path": str(path.resolve()) if path.exists() else str(path)}
    if path.exists():
        identity["bytes"] = path.stat().st_size
    try:
        identity["duration_seconds"] = get_duration(path)
    except Exception as e:
        logger.debug("duration probe failed for %s: %s", path, e)

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        raw = (result.stdout or "").strip()
        if result.returncode == 0 and raw:
            # width,height or width,height, with trailing comma variants
            parts = [p for p in raw.replace("\n", ",").split(",") if p]
            if len(parts) >= 2:
                identity["width"] = int(float(parts[0]))
                identity["height"] = int(float(parts[1]))
    except Exception as e:
        logger.debug("stream probe failed for %s: %s", path, e)
    return identity


def get_duration(input_file: str | Path) -> float:
    """Get video duration using ffprobe.

    Raises:
        RuntimeError: if the file cannot be probed or has no duration.
    """
    path = Path(input_file)
    if not path.exists():
        raise RuntimeError(f"Cannot probe duration; file not found: {path}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"Cannot probe duration; file is empty: {path}")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    raw = (result.stdout or "").strip()
    if result.returncode != 0 or not raw:
        err = (result.stderr or "").strip() or "no duration in ffprobe output"
        raise RuntimeError(f"ffprobe failed for {path}: {err}")
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"ffprobe returned non-numeric duration for {path!s}: {raw!r}"
        ) from exc


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
    job_run: Optional["VideoJobRun"] = None,
) -> Tuple[Optional[Path], Optional[Dict[str, float]]]:
    """
    Normalize video audio and compress for YouTube/Social.

    Args:
        input_path: Source video file
        output_path: Destination (default: {name}_normalized.mp4)
        callback: Progress callback(current, total_seconds) or None
        loudness_config: Optional dict with keys I, TP, LRA
        denoise_config: Optional dict with keys nr (noise reduction dB)
        job_run: Optional VideoJobRun receipt to update with phases/settings

    Returns:
        (output_path, stats) or (None, None) on failure
    """
    from cocli.models.campaigns.video_job_run import (
        VideoFileIdentity,
        VideoNormalizeSettings,
    )

    input_path = Path(input_path)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        if job_run is not None:
            job_run.add_error(f"Input file not found: {input_path}")
        return None, None

    if not output_path:
        output_path = (
            input_path.parent / f"{input_path.stem}_normalized{input_path.suffix}"
        )
    else:
        output_path = Path(output_path)

    if job_run is not None and job_run.input is None:
        job_run.input = VideoFileIdentity(**probe_video_identity(input_path))

    loudness_config = loudness_config or {"I": -14, "TP": -1.5, "LRA": 11}
    target_i = loudness_config.get("I", -14)
    target_tp = loudness_config.get("TP", -1.5)
    target_lra = loudness_config.get("LRA", 11)

    denoise_config = denoise_config or {"nr": 10}
    nr = denoise_config.get("nr", 10)

    # Phase 1: Analyze loudness
    logger.info(f"Analyzing {input_path.name}...")
    if job_run is not None:
        job_run.start_phase("analyze_loudness")
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
    if job_run is not None:
        job_run.end_phase("analyze_loudness")

    stats = parse_loudness_stats(result.stderr)
    if not stats:
        logger.error("Could not parse loudness statistics")
        if job_run is not None:
            job_run.add_error("Could not parse loudness statistics")
        return None, None

    # Phase 2: Normalize and compress
    logger.info("Normalizing and compressing...")

    encoder, encoder_requested, fallback_reason = select_h264_encoder()
    codec_args: list[str] = []
    preset: Optional[str] = None
    crf: Optional[int] = None
    cq: Optional[int] = None
    if encoder == "h264_nvenc":
        preset = "p4"
        cq = 20
        codec_args = ["-c:v", "h264_nvenc", "-preset", preset, "-tune", "hq", "-cq", str(cq)]
    else:
        preset = "slow"
        crf = 18
        codec_args = ["-c:v", "libx264", "-crf", str(crf), "-preset", preset]

    if job_run is not None:
        job_run.settings = VideoNormalizeSettings(
            encoder=encoder,
            encoder_requested=encoder_requested,
            encoder_fallback_reason=fallback_reason,
            preset=preset,
            crf=crf,
            cq=cq,
            audio="aac@192k",
            loudness={
                "I": float(target_i),
                "TP": float(target_tp),
                "LRA": float(target_lra),
            },
            denoise_nr=int(nr) if nr is not None else None,
        )

    af = (
        f"afftdn=nr={nr}:nt=w,loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:linear=true:"
        f"measured_I={stats['input_i']}:measured_LRA={stats['input_lra']}:"
        f"measured_tp={stats['input_tp']}:measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}"
    )

    duration = get_duration(input_path)
    logger.info(f"Using video encoder: {encoder}")

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

    if job_run is not None:
        job_run.start_phase("encode")

    # Capture stderr to a temp file so we can report encode failures (e.g. nvenc
    # CUDA init) without deadlocking on a filled PIPE buffer.
    with tempfile.NamedTemporaryFile(
        mode="w+", prefix="cocli-ffmpeg-", suffix=".log", delete=False
    ) as err_file:
        err_path = Path(err_file.name)
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=err_file, text=True
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

        returncode = process.wait()

    if job_run is not None:
        job_run.end_phase("encode")

    stderr_tail = ""
    try:
        stderr_text = err_path.read_text(errors="replace")
        stderr_tail = stderr_text[-1500:] if stderr_text else ""
    finally:
        err_path.unlink(missing_ok=True)

    output_ok = (
        returncode == 0
        and output_path.exists()
        and output_path.stat().st_size > 0
    )
    if output_ok:
        logger.info(f"Done! Saved to: {output_path} ({output_path.stat().st_size} bytes)")
        if job_run is not None:
            job_run.output = VideoFileIdentity(**probe_video_identity(output_path))
        return output_path, stats

    # Remove zero-byte / partial outputs so a later run does not treat them as success
    if output_path.exists() and output_path.stat().st_size == 0:
        try:
            output_path.unlink()
        except OSError:
            pass

    err_msg = (
        f"FFmpeg normalize failed (exit={returncode}, output={output_path}). "
        f"stderr tail: {stderr_tail or '(empty)'}"
    )
    logger.error("%s", err_msg)
    if job_run is not None:
        job_run.add_error(err_msg)
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
