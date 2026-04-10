# POLICY: frictionless-data-policy-enforcement
import logging
import json
from datetime import datetime, UTC
from typing import Any, List, Optional, Dict

from ...models.campaigns.queues.gm_list import ScrapeTask
from ...models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from ...core.paths import paths
from ...core.sharding import get_geo_shard, get_grid_tile_id
from ...core.text_utils import slugify
from ...core.geo_types import LatScale1, LonScale1

logger = logging.getLogger(__name__)


class GmListProcessor:
    """
    Modular processor for Google Maps List tasks.

    Source: ScrapeTask (Queue)
    Output: USV Trace File + Completion Receipt
    """

    def __init__(
        self, processed_by: str = "local-processor", bucket_name: Optional[str] = None
    ):
        self.processed_by = processed_by
        self.bucket_name = bucket_name

    async def process_results(
        self,
        task: ScrapeTask,
        items: List[GoogleMapsListItem],
        s3_client: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Saves discovery results to the deep-sharded trace path and writes the receipt.

        MANDATE: NEVER delete or unlink trace files.
        """
        try:
            lat_shard = get_geo_shard(task.latitude)
            grid_id = get_grid_tile_id(task.latitude, task.longitude)
            lat_tile, lon_tile = grid_id.split("_")
            phrase_slug = slugify(task.search_phrase)

            # 1. Save USV Trace File
            results_dir = (
                paths.queue(task.campaign_name, "gm-list").completed
                / "results"
                / lat_shard
                / lat_tile
                / lon_tile
            )
            results_dir.mkdir(parents=True, exist_ok=True)

            usv_path = results_dir / f"{phrase_slug}.usv"
            with open(usv_path, "w", encoding="utf-8") as rf:
                for item in items:
                    # Model-based serialization ensures canonical field order
                    rf.write(item.to_usv())

            # 2. Save JSON Receipt
            receipt_path = results_dir / f"{phrase_slug}.json"
            receipt_data = {
                "task_id": task.ack_token,
                "completed_at": datetime.now(UTC).isoformat(),
                "worker_id": self.processed_by,
                "schema_version": 2,
                "search_phrase": task.search_phrase,
                "latitude": float(LatScale1(task.latitude)),
                "longitude": float(LonScale1(task.longitude)),
                "result_count": len(items),
                "status": "success",
                "metadata": metadata or {},
            }
            with open(receipt_path, "w", encoding="utf-8") as jf:
                json.dump(receipt_data, jf, indent=2)

            # 3. S3 Mirror
            if s3_client and self.bucket_name:
                prefix = f"campaigns/{task.campaign_name}/queues/gm-list/completed/results/{lat_shard}/{lat_tile}/{lon_tile}/{phrase_slug}"
                s3_client.upload_file(str(usv_path), self.bucket_name, f"{prefix}.usv")
                s3_client.upload_file(
                    str(receipt_path), self.bucket_name, f"{prefix}.json"
                )

            logger.info(f"Trace & Receipt saved for {task.search_phrase} at {grid_id}")

        except Exception as e:
            logger.error(
                f"GmListProcessor failed for {task.search_phrase}: {e}", exc_info=True
            )
