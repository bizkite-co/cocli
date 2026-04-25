#!/usr/bin/env python3
"""
WAL Compactor for gm-list companies.

Manages the Write-Ahead Log (WAL) and shard-index lifecycle:
1. Write phase: Add file-per-record to WAL directory
2. Compact phase: Merge WAL into shard-index USV files
3. Cleanup phase: Remove WAL files after successful compaction

Usage:
    # Stage 1: Write to WAL (file-per-record)
    python scripts/compact_gm_list_wal.py --write

    # Stage 2: Compact WAL to shard-index
    python scripts/compact_gm_list_wal.py --compact

    # Stage 3: Cleanup WAL files
    python scripts/compact_gm_list_wal.py --cleanup

    # Or run full cycle
    python scripts/compact_gm_list_wal.py --full
"""

import argparse
import hashlib
import json
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
WAL_DIR = SHARDS_DIR / "wal"
WORKER_JSON = SHARDS_DIR / "worker.json"

sys.path.insert(0, str(REPO_DIR))
from cocli.core.sharding import get_place_id_shard

USV_DELIM = "\x1f"


def compute_self_hash() -> str:
    """Compute SHA256 hash of this worker script."""
    content = Path(__file__).read_bytes()
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def validate_worker() -> bool:
    """Validate this worker against worker.json in data directory."""
    if not WORKER_JSON.exists():
        logger.warning(f"worker.json not found at {WORKER_JSON}")
        return False
    
    with open(WORKER_JSON) as f:
        worker_config = json.load(f)
    
    expected_hash = worker_config.get("hash", "")
    actual_hash = compute_self_hash()
    
    if expected_hash != actual_hash:
        logger.error(f"Worker hash mismatch! Expected {expected_hash}, got {actual_hash}")
        return False
    
    logger.info(f"Worker validated: {actual_hash}")
    return True


def get_shard_index_path(shard_char: str) -> Path:
    """Get path to shard-index USV file."""
    return SHARDS_DIR / f"{shard_char}.usv"


def extract_place_id(line: str) -> str | None:
    """Extract place_id from USV line (first field)."""
    if not line or line.isspace():
        return None
    fields = line.split(USV_DELIM)
    if not fields:
        return None
    place_id = fields[0]
    if not place_id.startswith("ChIJ"):
        return None
    return place_id


def ensure_wal_dir() -> None:
    """Ensure WAL directory exists."""
    WAL_DIR.mkdir(parents=True, exist_ok=True)


def write_to_wal(dry_run: bool = True) -> dict:
    """Write results to WAL (file-per-record)."""
    stats = {"processed": 0, "skipped": 0, "errors": 0}

    if not RESULTS_DIR.exists():
        logger.warning(f"Results directory not found: {RESULTS_DIR}")
        return stats

    ensure_wal_dir()

    result_files = list(RESULTS_DIR.rglob("*.usv"))
    logger.info(f"Found {len(result_files)} result files to process")

    for usv_path in result_files:
        with open(usv_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                place_id = extract_place_id(line.strip())
                if not place_id:
                    continue

                wal_file = WAL_DIR / f"{place_id}.usv"

                if dry_run:
                    logger.info(f"[DRY-RUN] Would write WAL {place_id} -> {wal_file}")
                    stats["processed"] += 1
                else:
                    try:
                        if wal_file.exists():
                            stats["skipped"] += 1
                            continue
                        wal_file.write_text(line.strip() + "\n", encoding="utf-8")
                        stats["processed"] += 1
                    except Exception as e:
                        logger.error(f"Error writing {place_id}: {e}")
                        stats["errors"] += 1

    return stats


def compact_wal_to_shard_index(dry_run: bool = True) -> dict:
    """Compact WAL files into shard-index USV files."""
    stats = {"processed": 0, "errors": 0}

    if not WAL_DIR.exists() or not list(WAL_DIR.glob("*.usv")):
        logger.info("No WAL files to compact")
        return stats

    logger.info(f"Compacting WAL files from {WAL_DIR}")

    shard_records: dict[str, dict[str, str]] = {}

    wal_files = list(WAL_DIR.glob("*.usv"))
    logger.info(f"Reading {len(wal_files)} WAL files")

    for wal_file in wal_files:
        place_id = wal_file.stem
        content = wal_file.read_text().strip()

        shard_char = get_place_id_shard(place_id)
        if shard_char not in shard_records:
            shard_records[shard_char] = {}
        shard_records[shard_char][place_id] = content

    for shard_char, records in shard_records.items():
        sorted_records = sorted(records.items(), key=lambda x: x[0])
        combined = "\n".join(rec[1] for rec in sorted_records)
        shard_path = get_shard_index_path(shard_char)

        existing = ""
        if shard_path.exists():
            existing = shard_path.read_text().strip()
            if existing:
                combined = existing + "\n" + combined

        if dry_run:
            logger.info(
                f"[DRY-RUN] Would write shard-index {shard_path} with {len(sorted_records)} records"
            )
            stats["processed"] += len(sorted_records)
        else:
            try:
                combined = "\n".join(
                    sorted(combined.split("\n"), key=lambda x: x.split(USV_DELIM)[0])
                )
                shard_path.write_text(combined + "\n", encoding="utf-8")
                logger.info(
                    f"Wrote shard-index {shard_path} with {len(sorted_records)} records"
                )
                stats["processed"] += len(sorted_records)
            except Exception as e:
                logger.error(f"Error writing shard {shard_char}: {e}")
                stats["errors"] += 1

    return stats


def cleanup_wal(dry_run: bool = True) -> dict:
    """Remove WAL files after successful compaction."""
    stats = {"deleted": 0, "errors": 0}

    if not WAL_DIR.exists():
        logger.info("No WAL directory to clean")
        return stats

    wal_files = list(WAL_DIR.glob("*.usv"))
    logger.info(f"Found {len(wal_files)} WAL files to cleanup")

    for wal_file in wal_files:
        if dry_run:
            logger.info(f"[DRY-RUN] Would delete {wal_file}")
            stats["deleted"] += 1
        else:
            try:
                wal_file.unlink()
                stats["deleted"] += 1
            except Exception as e:
                logger.error(f"Error deleting {wal_file}: {e}")
                stats["errors"] += 1

    if not dry_run and WAL_DIR.exists() and not list(WAL_DIR.glob("*.usv")):
        try:
            WAL_DIR.rmdir()
            logger.info("Removed empty WAL directory")
        except Exception:
            pass

    return stats


def main():
    parser = argparse.ArgumentParser(description="gm-list WAL Compactor")
    parser.add_argument("--write", action="store_true", help="Write results to WAL")
    parser.add_argument(
        "--compact", action="store_true", help="Compact WAL to shard-index"
    )
    parser.add_argument("--cleanup", action="store_true", help="Cleanup WAL files")
    parser.add_argument(
        "--full", action="store_true", help="Run full cycle (write + compact + cleanup)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True, help="Dry run (default)"
    )
    parser.add_argument(
        "--no-dry-run", action="store_false", dest="dry_run", help="Actually execute"
    )

    args = parser.parse_args()

    if not validate_worker():
        logger.error("Worker validation failed! Aborting.")
        sys.exit(1)

    if args.write or args.full:
        logger.info("=== Stage 1: Write to WAL ===")
        stats = write_to_wal(dry_run=args.dry_run)
        logger.info(
            f"Written: {stats['processed']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}"
        )

    if args.compact or args.full:
        logger.info("=== Stage 2: Compact to shard-index ===")
        stats = compact_wal_to_shard_index(dry_run=args.dry_run)
        logger.info(f"Compacted: {stats['processed']}, Errors: {stats['errors']}")

    if args.cleanup or args.full:
        logger.info("=== Stage 3: Cleanup WAL ===")
        stats = cleanup_wal(dry_run=args.dry_run)
        logger.info(f"Deleted: {stats['deleted']}, Errors: {stats['errors']}")

    if not (args.write or args.compact or args.cleanup or args.full):
        parser.print_help()


if __name__ == "__main__":
    main()
