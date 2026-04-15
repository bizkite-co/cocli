"""Convert transcript to VTT format for YouTube closed captions."""

import re
from pathlib import Path
from typing import Optional


def parse_timestamp(ts: str) -> float:
    """Parse timestamp like [00:00] or [00:00:00] to seconds."""
    ts = ts.strip("[]")
    parts = ts.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    elif len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return 0.0


def format_vtt_time(seconds: float) -> str:
    """Format seconds to VTT timestamp format HH:MM:SS.mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:06.3f}"


def convert_transcript_to_vtt(
    transcript: str, output_path: Optional[Path] = None
) -> str:
    """Convert transcript text to VTT format.

    Expected transcript format:
    [00:00]  text here
    [00:09]  more text

    Returns VTT string and optionally writes to file.
    """
    lines = transcript.strip().split("\n")
    cues = []
    current_cue = None
    current_start = None

    timestamp_pattern = re.compile(r"^\[(\d{2}:\d{2}(?::\d{2})?)\]\s*(.*)$")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = timestamp_pattern.match(line)
        if match:
            timestamp_str = match.group(1)
            text = match.group(2).strip()

            if current_cue is not None and current_start is not None:
                cues.append((current_start, timestamp_str, current_cue))

            current_start = parse_timestamp(timestamp_str)
            current_cue = text
        else:
            if current_cue is not None:
                current_cue += " " + line

    if current_cue is not None and current_start is not None:
        cues.append((current_start, timestamp_str, current_cue))

    vtt_lines = ["WEBVTT", ""]

    for i, (start_sec, end_ts, text) in enumerate(cues):
        end_sec = parse_timestamp(end_ts)

        if i + 1 < len(cues):
            next_start = cues[i + 1][0]
            end_sec = min(end_sec, next_start - 0.1)

        if end_sec <= start_sec:
            end_sec = start_sec + 2.0

        vtt_lines.append(f"{format_vtt_time(start_sec)} --> {format_vtt_time(end_sec)}")
        vtt_lines.append(text)
        vtt_lines.append("")

    vtt_content = "\n".join(vtt_lines)

    if output_path:
        output_path.write_text(vtt_content)

    return vtt_content
