from pathlib import Path
from cocli.core.video.thumbnailer import process_thumbnail

# Paths
video_dir = Path(
    "data/campaigns/bizkite/video/normalized/2026-04-10 115954-intro-to-task-agent"
)
output_dir = Path(
    "data/campaigns/bizkite/video/packaged/2026-04-10 115954-intro-to-task-agent"
)
output_dir.mkdir(parents=True, exist_ok=True)

process_thumbnail(video_dir, output_dir)
print("Thumbnail processed.")
