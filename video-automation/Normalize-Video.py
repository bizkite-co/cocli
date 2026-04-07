import subprocess
import json
import sys
import os
import re


def get_duration(input_file):
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


def progress_bar(current, total, bar_length=40):
    percent = min(1.0, current / total)
    arrow = "=" * int(round(percent * bar_length) - 1) + ">"
    spaces = " " * (bar_length - len(arrow))
    sys.stdout.write(f"\rProgress: [{arrow}{spaces}] {int(percent * 100)}%")
    sys.stdout.flush()


def process_video_for_youtube(input_file, output_file=None):
    if not output_file:
        name, ext = os.path.splitext(input_file)
        output_file = f"{name}_youtube.mp4"

    duration = get_duration(input_file)
    sys.stderr.write(f"--- Phase 1: Analyzing {os.path.basename(input_file)} ---\n")
    analyze_cmd = [
        "ffmpeg",
        "-i",
        input_file,
        "-af",
        "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(
        analyze_cmd, capture_output=True, text=True, encoding="utf-8"
    )

    try:
        lines = result.stderr.split("\n")
        json_start = next(i for i, line in enumerate(lines) if "{" in line)
        stats = json.loads("\n".join(lines[json_start:]))
    except (StopIteration, json.JSONDecodeError):
        sys.stderr.write("Error: Could not parse loudness statistics.\n")
        return None

    sys.stderr.write("--- Phase 2: Normalizing and Compressing ---\n")
    af = (
        f"loudnorm=I=-14:TP=-1.5:LRA=11:linear=true:"
        f"measured_I={stats['input_i']}:measured_LRA={stats['input_lra']}:"
        f"measured_tp={stats['input_tp']}:measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}"
    )

    compress_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_file,
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
        output_file,
    ]

    process = subprocess.Popen(
        compress_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
    )
    time_regex = re.compile(r"out_time_ms=(\d+)")

    while True:
        line = process.stdout.readline()
        if not line:
            if process.poll() is not None:
                break
            continue

        match = time_regex.search(line)
        if match:
            current_sec = int(match.group(1)) / 1000000.0
            progress_bar(current_sec, duration)

    sys.stderr.write(f"\nDone! Saved to: {output_file}\n")
    return output_file


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python Normalize-Video.py <input_video>\n")
    else:
        new_path = process_video_for_youtube(sys.argv[1])
        if new_path:
            print(new_path)  # Output ONLY the path to stdout for composition
