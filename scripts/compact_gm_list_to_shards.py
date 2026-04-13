#!/usr/bin/env python3
"""
Compacts gm-list results into place_id-sharded company directories.

Usage:
    python scripts/compact_gm_list_to_shards.py [--limit N] [--dry-run]

Reads USV files from results/, extracts place_id, shards by get_place_id_shard(),
writes one-line USV files for trivial deduplication.
"""

import argparse
import logging
import sys
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

sys.path.insert(0, str(REPO_DIR))
from cocli.core.sharding import get_place_id_shard

USV_DELIM = "\x1f"


def get_shard_path(place_id: str) -> Path:
    """Calculate shard path from place_id using get_place_id_shard()."""
    shard = get_place_id_shard(place_id)
    return SHARDS_DIR / shard


def extract_place_id(line: str) -> str | None:
    """Extract place_id from USV line (first field).

    Only accepts valid Google Place IDs (start with 'ChIJ').
    """
    if not line or line.isspace():
        return None
    fields = line.split(USV_DELIM)
    if not fields:
        return None
    place_id = fields[0]
    if not place_id.startswith("ChIJ"):
        return None
    return place_id


def process_file(usv_path: Path, dry_run: bool = True) -> dict:
    """Process a single USV file, writing place_id-sharded one-line USVs."""
    stats = {"processed": 0, "skipped": 0, "errors": 0}

    with open(usv_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            place_id = extract_place_id(line.strip())
            if not place_id:
                continue

            shard_path = get_shard_path(place_id)
            dest_file = shard_path / f"{place_id}.usv"

            if dry_run:
                logger.info(f"[DRY-RUN] Would write {place_id} -> {dest_file}")
            else:
                try:
                    shard_path.mkdir(parents=True, exist_ok=True)
                    if dest_file.exists():
                        stats["skipped"] += 1
                        continue
                    dest_file.write_text(line.strip() + "\n", encoding="utf-8")
                    stats["processed"] += 1
                except Exception as e:
                    logger.error(f"Error writing {place_id}: {e}")
                    stats["errors"] += 1

    return stats


def collect_usv_files(limit: int | None = None) -> list[Path]:
    """Find all USV files in results directory."""
    files = []
    if not RESULTS_DIR.exists():
        logger.warning(f"Results directory not found: {RESULTS_DIR}")
        return files

    for usv_path in RESULTS_DIR.rglob("*.usv"):
        files.append(usv_path)

    files.sort()
    if limit:
        files = files[:limit]
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Compact gm-list results into place_id-sharded company files."
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of files to process"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Dry run mode (default)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_false",
        dest="dry_run",
        help="Actually write files",
    )

    args = parser.parse_args()

    logger.info(f"Looking for USV files in: {RESULTS_DIR}")

    files = collect_usv_files(limit=args.limit)
    logger.info(f"Found {len(files)} files to process")

    if args.limit:
        logger.info(f"Limited to {args.limit} files")

    total_stats = {"processed": 0, "skipped": 0, "errors": 0}

    for i, usv_path in enumerate(files):
        logger.info(
            f"Processing {i + 1}/{len(files)}: {usv_path.relative_to(DATA_DIR)}"
        )

        if args.dry_run:
            process_file(usv_path, dry_run=True)
        else:
            stats = process_file(usv_path, dry_run=False)
            total_stats["processed"] += stats["processed"]
            total_stats["skipped"] += stats["skipped"]
            total_stats["errors"] += stats["errors"]

    if args.dry_run:
        logger.info(f"[DRY-RUN] Would process {len(files)} files")
    else:
        logger.info(
            f"Processed: {total_stats['processed']}, "
            f"Skipped (dupes): {total_stats['skipped']}, "
            f"Errors: {total_stats['errors']}"
        )


if __name__ == "__main__":
    main()
