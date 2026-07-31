"""
Repairs turboship-style legacy CompactProspect-shaped rows in a prospects
checkpoint by writing corrected GoogleMapsProspect records to WAL.

Rows written positionally into the current column layout by an old
migration/recovery script only ever populated place_id/name/phone/
street_address/domain/reviews_count/average_rating/gmb_url/category,
leaving slug/created_at/updated_at/version/company_hash blank - which
fails GoogleMapsProspect's own validation. This does NOT edit the
checkpoint directly: it writes backfilled rows to WAL with a fresh
updated_at, so the next `cocli index compact` folds them in via the
normal LWW-by-place_id/updated_at path, naturally superseding the old
invalid row for the same place_id.

Usage:
    uv run python scripts/backfill_legacy_compact_prospects.py turboship
"""

import argparse
import logging

from pydantic import ValidationError

from cocli.core.paths import paths
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.core.transformers.compact_prospect_to_google_maps_prospect import (
    transform_compact_prospect_to_google_maps_prospect,
)
from cocli.models.campaigns.indexes.compact_prospect import CompactProspect
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.utils.usv_utils import USVDictReader

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backfill_legacy_compact_prospects")


def backfill(campaign_name: str) -> None:
    checkpoint_path = paths.campaign(campaign_name).index("google_maps_prospects").checkpoint
    if not checkpoint_path.exists():
        logger.error("Checkpoint not found: %s", checkpoint_path)
        return

    field_names = GoogleMapsProspect.usv_field_names()
    manager = ProspectsIndexManager(campaign_name)

    repaired = 0
    still_invalid = 0
    already_valid = 0

    with open(checkpoint_path, "r", encoding="utf-8") as f:
        reader = USVDictReader(f, fieldnames=field_names)
        for row in reader:
            try:
                GoogleMapsProspect.model_validate(row)
                already_valid += 1
                continue
            except ValidationError:
                pass

            try:
                legacy = CompactProspect.model_validate(row)
            except ValidationError:
                still_invalid += 1
                continue

            prospect = transform_compact_prospect_to_google_maps_prospect(legacy)
            manager.add_to_wal(prospect)
            repaired += 1

    logger.info("Already valid:  %d", already_valid)
    logger.info("Repaired to WAL: %d", repaired)
    logger.info("Still invalid:   %d (not this legacy shape)", still_invalid)
    if repaired:
        logger.info(
            "Run `cocli index compact --campaign %s` to fold repaired rows into the checkpoint.",
            campaign_name,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", nargs="?", default="turboship")
    args = parser.parse_args()
    backfill(args.campaign)
