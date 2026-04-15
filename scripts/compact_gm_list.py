#!/usr/bin/env python3
"""
Compacts gm-list results into sharded directories.

Usage:
    python scripts/compact_gm_list.py [--limit N] [--dry-run]
"""

import argparse
import logging
import shutil
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_DIR = SCRIPT_DIR.parent
DATA_DIR = REPO_DIR / "data"
RESULTS_DIR = (
    DATA_DIR / "campaigns" / "roadmap" / "queues" / "gm-list" / "completed" / "results"
)
SHARDS_DIR = (
    DATA_DIR / "campaigns" / "roadmap" / "queues" / "gm-list" / "completed" / "shards"
)


def get_shard_path(lat: float, lon: float) -> Path:
    """Calculate shard path from lat/lon."""
    lat_shard = int(lat) // 10 * 10
    return SHARDS_DIR / str(lat_shard) / f"{lat:.1f}" / f"{lon:.1f}"


def parse_coordinates_from_path(path: Path, base: Path) -> tuple[float, float] | None:
    """Extract lat/lon from directory path.

    Patterns (relative to DATA_DIR):
    - campaigns/roadmap/queues/gm-list/completed/results/2/29.0/-95.5/pacific-life.usv
    - campaigns/roadmap/queues/gm-list/completed/results/2/29.0/-95.5/-95.5/financial.usv

    Expected: lat=29.0, lon=-95.5
    """
    try:
        rel_parts = path.relative_to(base).parts
        if len(rel_parts) >= 8:
            lat = float(rel_parts[-3])
            lon = float(rel_parts[-2])
            return lat, lon
        return None
    except (ValueError, IndexError):
        return None


def collect_usv_files(limit: int | None = None) -> list[tuple[Path, float, float]]:
    """Find all USV files in results directory."""
    files = []
    if not RESULTS_DIR.exists():
        logger.warning(f"Results directory not found: {RESULTS_DIR}")
        return files

    for usv_path in RESULTS_DIR.rglob("*.usv"):
        coords = parse_coordinates_from_path(usv_path, DATA_DIR)
        if coords:
            files.append((usv_path, coords[0], coords[1]))

    files.sort(key=lambda x: (x[1], x[2]))
    if limit:
        files = files[:limit]
    return files


def compact_files(files: list[tuple[Path, float, float]], dry_run: bool = True) -> None:
    """Move files to sharded directory structure."""
    processed = 0
    skipped = 0

    for usv_path, lat, lon in files:
        shard_path = get_shard_path(lat, lon)

        if dry_run:
            logger.info(f"[DRY-RUN] Would move {usv_path} -> {shard_path}")
        else:
            shard_path.mkdir(parents=True, exist_ok=True)
            dest = shard_path / usv_path.name

            if dest.exists():
                logger.warning(
                    f"Skipping (duplicate): {usv_path.name} exists at {shard_path}"
                )
                skipped += 1
                continue

            try:
                shutil.move(str(usv_path), str(dest))
                logger.info(f"Moved {usv_path} -> {shard_path}")
                processed += 1
            except Exception as e:
                logger.error(f"Failed to move {usv_path}: {e}")
                skipped += 1

    if dry_run:
        logger.info(f"[DRY-RUN] Would process {len(files)} files")
    else:
        logger.info(f"Processed: {processed}, Skipped: {skipped}")


def main():
    parser = argparse.ArgumentParser(description="Compact gm-list results into shards.")
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of files to process"
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True, help="Dry run mode (default)"
    )
    parser.add_argument(
        "--no-dry-run", action="store_false", dest="dry_run", help="Actually move files"
    )

    args = parser.parse_args()

    logger.info(f"Looking for USV files in: {RESULTS_DIR}")

    files = collect_usv_files(limit=args.limit)
    logger.info(f"Found {len(files)} files to process")

    if args.limit:
        logger.info(f"Limited to {args.limit} files")

    for i, (path, lat, lon) in enumerate(files):
        logger.info(f"  {i + 1}: {path.relative_to(DATA_DIR)} -> lat={lat}, lon={lon}")

    if files:
        compact_files(files, dry_run=args.dry_run)
    else:
        logger.info("No files to process")


if __name__ == "__main__":
    main()
