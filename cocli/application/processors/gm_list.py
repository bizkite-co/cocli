# POLICY: frictionless-data-policy-enforcement
import logging
import json
from datetime import datetime, UTC
from cocli.core.geo_types import LatScale1, LonScale1
from typing import Any, List, Optional, Dict

from ...models.campaigns.queues.gm_list import ScrapeTask
from ...models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
from ...core.paths import paths
from ...core.sharding import get_geo_shard, get_grid_tile_id
from ...core.text_utils import slugify

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
        logger.info(
            f"!!! DEBUG: GmListProcessor.process_results called with metadata: {metadata is not None}"
        )
        try:
            lat_shard = get_geo_shard(float(task.latitude))
            grid_id = get_grid_tile_id(float(task.latitude), float(task.longitude))
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

                    # MANDATE: Save individual HTML witness for EACH item
                    if item.html:
                        # Save to raw/gm-list/ instead of queues/ to keep queue sync fast
                        raw_list_dir = (
                            paths.campaign(task.campaign_name).path
                            / "raw"
                            / "gm-list"
                            / lat_shard
                            / lat_tile
                            / lon_tile
                        )
                        raw_list_dir.mkdir(parents=True, exist_ok=True)

                        html_path = raw_list_dir / f"{item.place_id}.html"
                        with open(html_path, "w", encoding="utf-8") as hf:
                            hf.write(item.html)

                        # Mirror HTML to S3
                        if s3_client and self.bucket_name:
                            s3_raw_prefix = f"campaigns/{task.campaign_name}/raw/gm-list/{lat_shard}/{lat_tile}/{lon_tile}"
                            s3_client.upload_file(
                                str(html_path),
                                self.bucket_name,
                                f"{s3_raw_prefix}/{item.place_id}.html",
                            )

            # Save Datapackage for the results (Frictionless Mandate)
            # NOTE: Datapackage is now created at results/ level with glob pattern
            # GoogleMapsListItem.save_datapackage(results_dir, f"gm-list-{phrase_slug}", f"{phrase_slug}.usv")

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
