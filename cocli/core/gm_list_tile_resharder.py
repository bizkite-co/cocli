# POLICY: frictionless-data-policy-enforcement
import logging
import shutil
from pathlib import Path
from typing import Set
from cocli.core.config import get_campaigns_dir
from cocli.core.sharding import get_grid_tile_id, get_geo_shard
from cocli.core.constants import UNIT_SEP

logger = logging.getLogger(__name__)


def reshard_google_maps_list_item_tiles(campaign_name: str) -> int:
    """Relocates GoogleMapsListItem USVs filed under non-standard-precision
    lat/lon paths to the correct 0.1-degree tile path. Same model in, same
    model out - a repair of gm-list's own result sharding, not a transform."""
    campaign_dir = get_campaigns_dir() / campaign_name
    results_dir = campaign_dir / "queues" / "gm-list" / "completed" / "results"

    if not results_dir.exists():
        return 0

    all_files = list(results_dir.rglob("*.*"))
    merged_count = 0

    for file_path in all_files:
        rel_path = file_path.relative_to(results_dir)
        parts = rel_path.parts
        if len(parts) < 4:
            continue

        lat_str, lon_str, filename = parts[1], parts[2], parts[3]

        try:
            lat, lon = float(lat_str), float(lon_str)
            is_standard = ('.' in lat_str and len(lat_str.split('.')[-1]) == 1) and \
                          ('.' in lon_str and len(lon_str.split('.')[-1]) == 1)

            if not is_standard:
                correct_tile = get_grid_tile_id(lat, lon)
                c_lat, c_lon = correct_tile.split("_")
                c_shard = get_geo_shard(lat)
                target_path = results_dir / c_shard / c_lat / c_lon / filename

                target_path.parent.mkdir(parents=True, exist_ok=True)

                if file_path.suffix.lower() == ".usv":
                    _merge_usv(file_path, target_path)
                else:
                    if not target_path.exists():
                        shutil.copy2(str(file_path), str(target_path))
                merged_count += 1
        except ValueError:
            continue

    _cleanup_empty_dirs(results_dir)
    return merged_count


def _merge_usv(src: Path, dest: Path) -> None:
    existing_pids: Set[str] = set()
    if dest.exists():
        for line in dest.read_text().splitlines():
            if line.strip():
                existing_pids.add(line.split(UNIT_SEP)[0])

    new_rows = []
    for line in src.read_text().splitlines():
        if line.strip():
            pid = line.split(UNIT_SEP)[0]
            if pid not in existing_pids:
                new_rows.append(line)
                existing_pids.add(pid)

    if new_rows:
        with open(dest, "a", encoding="utf-8") as df:
            for row in new_rows:
                df.write(row + "\n")


def _cleanup_empty_dirs(root: Path) -> None:
    dirs = sorted([d for d in root.rglob("*") if d.is_dir()], key=lambda x: len(x.parts), reverse=True)
    for d in dirs:
        try:
            if not any(d.iterdir()):
                d.rmdir()
        except Exception:
            pass
