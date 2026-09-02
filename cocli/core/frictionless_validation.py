"""
Frictionless Data validation utilities for discovery-gen pipeline outputs.

Validates USV files against their datapackage.json schemas and Pydantic models.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def validate_usv_file(
    usv_path: Path,
    schema_path: Optional[Path] = None,
    model_class: Optional[Any] = None,
) -> tuple[bool, int, list[str]]:
    """
    Validate a USV file against its Frictionless Data schema.

    Args:
        usv_path: Path to the .usv file
        schema_path: Optional path to datapackage.json. If None, looks for it
                     in the same directory as usv_path.
        model_class: Optional Pydantic model class for deserialization validation

    Returns:
        Tuple of (is_valid, record_count, error_messages)
    """
    errors: list[str] = []
    record_count = 0

    if not usv_path.exists():
        return False, 0, [f"File not found: {usv_path}"]

    # Determine schema path
    if schema_path is None:
        schema_path = usv_path.parent / "datapackage.json"

    if not schema_path.exists():
        return False, 0, [f"Schema not found: {schema_path}"]

    try:
        # Load and validate schema file
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        # Check schema structure
        if "resources" not in schema or not schema["resources"]:
            return False, 0, [f"No resources defined in schema: {schema_path}"]

        resource = schema["resources"][0]
        if "schema" not in resource:
            return False, 0, ["No field schema defined in resource"]

        field_schema = resource.get("schema", {})
        fields = {f["name"]: f for f in field_schema.get("fields", [])}

        if not fields:
            return False, 0, ["No fields defined in schema"]

        # Validate records using model class if provided
        if model_class:
            try:
                with open(usv_path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        if line.strip():
                            try:
                                model_class.from_usv(line)
                                record_count += 1
                            except Exception as e:
                                errors.append(f"Line {line_num}: {str(e)}")
                                if len(errors) > 10:
                                    errors.append("... (truncated)")
                                    break
            except Exception as e:
                return False, record_count, [f"Failed to read USV file: {str(e)}"]

            # Additional: validate field count
            with open(usv_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    if line.strip():
                        # NOTE: str.strip() treats \x1f (Unit Separator) as
                        # whitespace, so it silently drops a legitimately-
                        # empty trailing optional field before the split.
                        field_count = len(line.rstrip("\r\n").split("\x1f"))
                        # Count non-optional fields in schema
                        required_count = sum(
                            1
                            for f in field_schema.get("fields", [])
                            if f.get("required", True)  # Default to required
                        )
                        if field_count < required_count:
                            errors.append(
                                f"Line {line_num}: Expected at least {required_count} "
                                f"fields, got {field_count}"
                            )
                        break
        else:
            # Simple field count validation
            with open(usv_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        record_count += 1

        return len(errors) == 0, record_count, errors

    except json.JSONDecodeError as e:
        return False, 0, [f"Invalid JSON in schema: {str(e)}"]
    except Exception as e:
        return False, record_count, [f"Validation error: {str(e)}"]


def validate_stage_outputs(
    campaign_name: str, queue_paths: Any, stage: Optional[int] = None
) -> dict[int, dict[str, Any]]:
    """
    Validate all outputs for discovery-gen pipeline stages.

    Args:
        campaign_name: Campaign name
        queue_paths: QueuePaths object for the discovery-gen queue
        stage: Optional specific stage to validate (1-3). If None, validates all.

    Returns:
        Dict mapping stage number → validation results
    """
    from cocli.models.campaigns.tiles import TileRecord
    from cocli.models.campaigns.mission import MissionTask

    results: dict[int, dict[str, Any]] = {}

    # Stage 1: Tiles
    if stage is None or stage == 1:
        tiles_path = queue_paths.path / "tiles" / "tiles.usv"
        schema_path = queue_paths.path / "tiles" / "datapackage.json"
        is_valid, count, errors = validate_usv_file(
            tiles_path, schema_path, model_class=TileRecord
        )
        results[1] = {
            "name": "Generate Tiles",
            "file": str(tiles_path),
            "schema": str(schema_path),
            "valid": is_valid,
            "record_count": count,
            "errors": errors,
        }

    # Stage 2: Mission
    if stage is None or stage == 2:
        mission_path = queue_paths.master
        schema_path = queue_paths.path / "datapackage.json"
        is_valid, count, errors = validate_usv_file(
            mission_path, schema_path, model_class=MissionTask
        )
        results[2] = {
            "name": "Expand Phrases → Mission",
            "file": str(mission_path),
            "schema": str(schema_path),
            "valid": is_valid,
            "record_count": count,
            "errors": errors,
        }

    # Stage 3: Frontier
    if stage is None or stage == 3:
        frontier_path = queue_paths.pending / "frontier.usv"
        schema_path = queue_paths.pending / "datapackage.json"
        is_valid, count, errors = validate_usv_file(
            frontier_path, schema_path, model_class=MissionTask
        )
        results[3] = {
            "name": "Filter Frontier (ScrapeIndex TTL)",
            "file": str(frontier_path),
            "schema": str(schema_path),
            "valid": is_valid,
            "record_count": count,
            "errors": errors,
        }

    return results


def validate_schema_hash(
    datapackage_path: Path, expected_hash: Optional[str] = None
) -> tuple[bool, str]:
    """
    Validate that a datapackage.json has the correct schema_hash.

    Args:
        datapackage_path: Path to datapackage.json
        expected_hash: Optional expected schema hash. If None, just returns actual hash.

    Returns:
        Tuple of (is_valid, actual_hash)
    """
    if not datapackage_path.exists():
        return False, ""

    try:
        with open(datapackage_path, "r", encoding="utf-8") as f:
            package = json.load(f)

        # Get schema hash from metadata (stored as cocli:schema_hash).
        # Canonical form is {resource_name: hash}; legacy sidecars hold a
        # bare string.
        actual_hash = package.get("cocli:schema_hash", "")
        if isinstance(actual_hash, dict):
            resource = str(package.get("name", ""))
            actual_hash = actual_hash.get(resource) or next(
                iter(actual_hash.values()), ""
            )

        if not expected_hash:
            return bool(actual_hash), actual_hash

        is_valid = actual_hash == expected_hash
        return is_valid, actual_hash

    except Exception as e:
        logger.error(f"Failed to validate schema hash: {str(e)}")
        return False, ""
