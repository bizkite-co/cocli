import os
import sys
import json
import shutil
import logging
import argparse
from pathlib import Path
from datetime import datetime, UTC, timedelta

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from cocli.core.config import get_campaign_dir
from cocli.core.sharding import get_geo_shard
from cocli.core.text_utils import slugify

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def is_non_conforming(name: str) -> bool:
    """Checks if a directory name looks like a coordinate with > 1 decimal place."""
    try:
        if "." in name:
            parts = name.split(".")
            # If it's a coordinate-like name and has > 1 decimal digit
            if parts[0].replace("-", "").isdigit() and len(parts[1]) > 1:
                return True
    except Exception:
        pass
    return False


def _lease_is_expired(lease_path: Path, now: datetime) -> bool:
    """True if the lease at lease_path is expired right now. False if the
    file no longer exists (already reclaimed or purged by someone else) -
    that's "nothing to do" for a caller, not "junk"."""
    try:
        with open(lease_path, 'r') as f:
            data = json.load(f)
        expires_at_str = data.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            return now > expires_at
        # Fallback: check file mtime (if lease has no expiry info)
        mtime = datetime.fromtimestamp(lease_path.stat().st_mtime, UTC)
        return now > (mtime + timedelta(minutes=15))
    except FileNotFoundError:
        return False
    except Exception:
        return True  # unreadable/corrupt existing file - treat as junk


def _alert_precision_violation(campaign_name: str, location: str, count: int, samples: list[Path], base: Path) -> None:
    """Precision-named dirs should never occur post-fix - this is a bug
    signal, not routine housekeeping, so it pages instead of just logging."""
    try:
        from cocli.utils.alert_utils import send_alert
        from cocli.models.campaigns.campaign import Campaign

        campaign = Campaign.load(campaign_name)
        ntfy_url = getattr(getattr(campaign, "alerts", None), "ntfy_url", None)
        if ntfy_url:
            os.environ["COCLI_ALERT_NTFY_URL"] = ntfy_url

        sample_txt = "\n".join(str(p.relative_to(base)) for p in samples[:5])
        send_alert(
            message=(
                f"Found {count} high-precision (>1 decimal) directory name(s) "
                f"in {campaign_name}/{location} - this should never happen "
                f"post-fix; investigate the generation code.\n{sample_txt}"
            ),
            title=f"High-precision dirs in {campaign_name}/{location}",
            priority=4,
            tags=["warning", "magnifying_glass_tilted_left"],
            cooldown_key=f"precision_violation_{campaign_name}_{location}",
        )
    except Exception as e:
        logger.error(f"Failed to send precision-violation alert: {e}")

def cleanup_pending_queue(campaign_name: str, dry_run: bool = True) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return

    pending_dir = campaign_dir / "queues" / "gm-list" / "pending"
    if not pending_dir.exists():
        logger.warning(f"No pending queue found at {pending_dir}")
        return

    logger.info(f"--- Deep Pending Queue Sanitization: {campaign_name} (Dry Run: {dry_run}) ---")
    
    moved = 0
    deleted_leases = 0
    removed_dirs = 0
    now = datetime.now(UTC)

    # 1. Recursive Scan for non-conforming directories
    non_conforming: list[Path] = []
    for root_dir, dirs, files in os.walk(pending_dir, topdown=False):
        for d_name in dirs:
            if is_non_conforming(d_name):
                non_conforming.append(Path(root_dir) / d_name)

    logger.info(f"Found {len(non_conforming)} non-conforming directories in pending queue.")
    if non_conforming:
        _alert_precision_violation(campaign_name, "gm-list/pending", len(non_conforming), non_conforming, pending_dir)

    if not dry_run:
        purged_count = 0
        for d_item in non_conforming:
            try:
                shutil.rmtree(d_item)
                purged_count += 1
            except Exception as e:
                logger.error(f"Failed to purge {d_item}: {e}")
        logger.info(f"Purged {purged_count} non-conforming directories.")
    else:
        for d_item in non_conforming[:10]:
            print(f"  [STALE] {d_item.relative_to(pending_dir)}")
        if len(non_conforming) > 10:
            print(f"  ... and {len(non_conforming) - 10} more")

    # 2. Find and handle leases/tasks in conforming but expired paths
    all_leases = list(pending_dir.rglob("lease.json"))
    expired_at_scan = sum(1 for lp in all_leases if _lease_is_expired(lp, now))
    logger.info(
        f"Lease GC: {len(all_leases)} lease(s) found, "
        f"{expired_at_scan} expired as of scan time (before purge)."
    )

    for lease_path in all_leases:
        try:
            # Path is: pending/{shard}/{lat}/{lon}/{phrase}.[csv|usv]/lease.json
            parts = lease_path.relative_to(pending_dir).parts
            if len(parts) < 4:
                logger.debug(f"Skipping non-standard lease path: {lease_path}")
                continue
            
            # Extract metadata from path
            # parts[-2] is "{phrase}.csv" or "{phrase}.usv"
            # parts[-3] is lon
            # parts[-4] is lat
            phrase_part = parts[-2]
            lon_str = parts[-3]
            lat_str = parts[-4]
            
            try:
                lat = float(lat_str)
                lon = float(lon_str)
            except ValueError:
                logger.warning(f"Invalid coordinate in path: {lease_path}")
                continue
                
            phrase_slug = slugify(phrase_part.replace(".csv", "").replace(".usv", ""))
            
            # Normalize to 1 decimal place
            lat_norm = round(lat, 1)
            lon_norm = round(lon, 1)
            
            # Calculate New Gold Standard Path
            shard = get_geo_shard(lat_norm)
            # Standard: {shard}/{lat}/{lon}/{phrase}.csv/lease.json
            new_lease_dir = pending_dir / shard / f"{lat_norm}" / f"{lon_norm}" / f"{phrase_slug}.csv"
            new_lease_path = new_lease_dir / "lease.json"
            
            is_expired = _lease_is_expired(lease_path, now)

            if is_expired:
                logger.info(f"Purging EXPIRED lease: {lease_path.relative_to(pending_dir)}")
                if not dry_run:
                    # Re-verify right at delete time - a worker's poll() can
                    # legitimately CAS-reclaim this exact lease (stations
                    # acquire_lease) between our scan above and this delete.
                    # This script's read-then-unlink isn't atomic like that
                    # path, so we close the window by re-checking immediately
                    # before acting instead of trusting the earlier scan.
                    if _lease_is_expired(lease_path, datetime.now(UTC)):
                        try:
                            lease_path.unlink()
                            deleted_leases += 1
                        except FileNotFoundError:
                            logger.info(f"  Already gone (raced with reclaim or another sweep): {lease_path.relative_to(pending_dir)}")
                    else:
                        logger.info(f"  Reclaimed since scan, skipping delete: {lease_path.relative_to(pending_dir)}")
                else:
                    deleted_leases += 1
            else:
                # Active lease: Move to new standard path
                if lease_path.resolve() != new_lease_path.resolve():
                    logger.info(f"Normalizing ACTIVE lease: {lease_path.relative_to(pending_dir)} -> {new_lease_path.relative_to(pending_dir)}")
                    if not dry_run:
                        new_lease_dir.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(lease_path), str(new_lease_path))
                        
                        # Also move task.json if it exists
                        old_task = lease_path.parent / "task.json"
                        if old_task.exists():
                            shutil.move(str(old_task), str(new_lease_dir / "task.json"))
                    moved += 1
                
        except Exception as e:
            logger.error(f"Error processing lease {lease_path}: {e}")

    # 2. Cleanup empty directories
    if not dry_run:
        logger.info("Cleaning up empty directories...")
        for root, dirs, files in os.walk(pending_dir, topdown=False):
            for d in dirs:
                dir_path = Path(root) / d
                try:
                    # Only remove if truly empty (no hidden files)
                    if not any(dir_path.iterdir()):
                        dir_path.rmdir()
                        removed_dirs += 1
                except OSError:
                    pass

    logger.info(f"Done. Active Leases Normalized: {moved}, Expired Leases Purged: {deleted_leases}")
    if not dry_run:
        logger.info(f"Empty directories removed: {removed_dirs}")

if __name__ == "__main__":
    from cocli.core.config import get_campaign
    parser = argparse.ArgumentParser(description="Normalize gm-list pending queue and purge expired leases.")
    parser.add_argument("campaign", nargs="?", default=get_campaign(), help="Campaign name (defaults to active campaign)")
    parser.add_argument("--execute", action="store_true", help="Actually perform the moves and deletes")
    
    args = parser.parse_args()
    cleanup_pending_queue(args.campaign, dry_run=not args.execute)