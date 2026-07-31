"""Bulk-validates a compacted prospects checkpoint against GoogleMapsProspect.

Complements audit_prospect_quality.py (which measures field *completeness*):
this instead runs every row through the real Pydantic model - catching
schema/value-level misalignment (e.g. a column-shift landing an out-of-range
average_rating, or a malformed phone/place_id) that a completeness count
would silently pass through as "present".
"""

import argparse
import logging
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from cocli.core.paths import paths
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.utils.usv_utils import USVDictReader

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("prospects_validator")


def validate_checkpoint(checkpoint_path: Path, sample_errors: int = 15) -> None:
    if not checkpoint_path.exists():
        logger.error("Checkpoint not found: %s", checkpoint_path)
        return

    field_names = GoogleMapsProspect.usv_field_names()
    valid = 0
    invalid = 0
    failure_counts: Counter[str] = Counter()
    samples: list[tuple[str, str]] = []

    with open(checkpoint_path, "r", encoding="utf-8") as f:
        reader = USVDictReader(f, fieldnames=field_names)
        for row in reader:
            try:
                GoogleMapsProspect.model_validate(row)
                valid += 1
            except ValidationError as e:
                invalid += 1
                for err in e.errors():
                    loc = ".".join(str(p) for p in err["loc"])
                    failure_counts[f"{loc}: {err['type']}"] += 1
                if len(samples) < sample_errors:
                    samples.append((row.get("place_id", "?"), str(e)))

    total = valid + invalid
    print("\n--- PROSPECTS CHECKPOINT VALIDATION ---")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Total rows:   {total}")
    print(f"Valid:        {valid} ({valid * 100 / total:.2f}%)" if total else "Valid: 0")
    print(f"Invalid:      {invalid} ({invalid * 100 / total:.2f}%)" if total else "Invalid: 0")

    if failure_counts:
        print("\nFailure breakdown (field: error type -> count):")
        for label, count in failure_counts.most_common():
            print(f"  {label}: {count}")

    if samples:
        print(f"\nFirst {len(samples)} invalid rows (place_id: error):")
        for place_id, err in samples:
            print(f"  {place_id}: {err.splitlines()[0]}")
    print("-" * 40)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", nargs="?", default="turboship")
    parser.add_argument(
        "--index", default="google_maps_prospects", help="Index name"
    )
    args = parser.parse_args()

    idx_paths = paths.campaign(args.campaign).index(args.index)
    validate_checkpoint(idx_paths.checkpoint)
