# POLICY: frictionless-data-policy-enforcement
import json
import logging
from enum import Enum
from datetime import datetime
from pathlib import Path
from typing import (
    List,
    Dict,
    Any,
    Type,
    TypeVar,
    Optional,
    Tuple,
    Protocol,
    runtime_checkable,
    ClassVar,
)

from pydantic import BaseModel, ValidationError

from ..core.constants import UNIT_SEP, RECORD_SEP

logger = logging.getLogger(__name__)


class ResourcePathPolicy(Enum):
    RECURSIVE = "**/*.usv"  # Default
    SPECIFIC = "specific"  # Override


class SchemaConflictError(Exception):
    """Raised when a Pydantic model change would break existing USV data positioning."""

    def __init__(self, message: str, diff: List[str]):
        super().__init__(message)
        self.diff = diff


@runtime_checkable
class SchemaGenerator(Protocol):
    """
    Protocol enforcing canonical datapackage.json generation.

    Any model that generates datapackage.json files MUST implement this Protocol.
    This ensures consistent schema management and prevents schema drift.

    Usage:
        def save_derived_file(path: Path, model: type[SchemaGenerator]):
            # Model must implement SchemaGenerator to be used here
            model.save_datapackage(path.parent, "resource", path.name)
    """

    SCHEMA_UPDATED_AT: ClassVar[str]

    @classmethod
    def get_schema_hash(cls) -> str: ...

    @classmethod
    def get_datapackage_fields(cls) -> List[Dict[str, Any]]: ...

    @classmethod
    def get_datapackage(
        cls, resource_name: str, resource_path: str | None = None
    ) -> Dict[str, Any]: ...

    @classmethod
    def save_datapackage(
        cls,
        path: Path,
        resource_name: str,
        resource_path: str,
        force: bool = False,
        wasi_hash: str | None = None,
    ) -> None: ...


T = TypeVar("T", bound="BaseUsvModel")


class BaseUsvModel(BaseModel):
    """
    AUTHORITATIVE BASE MODEL for all cocli objects backed by USV files.
    Enforces Frictionless Data Package standards and deterministic serialization.
    """

    def to_usv(self) -> str:
        """
        Serializes the model into a Unit-Separated Value string.
        Follows field definition order strictly.
        Handles datetimes, lists, and special character sanitization.
        """
        field_names = list(self.__class__.model_fields.keys())
        # Use by_alias=False to ensure we use internal field names
        dump = self.model_dump(by_alias=False)

        values = []
        for field in field_names:
            val = dump.get(field)
            if val is None:
                values.append("")
            elif isinstance(val, Enum):
                values.append(str(val.value))
            elif isinstance(val, (list, tuple)):
                # Lists are semicolon-separated within the field
                # Replace newlines and UNIT_SEP to prevent record breakage
                sanitized_list = [
                    str(v)
                    .replace("\r\n", "<br>")
                    .replace("\n", "<br>")
                    .replace("\r", "<br>")
                    .replace(UNIT_SEP, " ")
                    for v in val
                ]
                values.append(";".join(sanitized_list))
            elif isinstance(val, datetime):
                values.append(val.isoformat())
            else:
                # Sanitize all other fields for newlines and separators
                s_val = (
                    str(val)
                    .replace("\r\n", "<br>")
                    .replace("\n", "<br>")
                    .replace("\r", "<br>")
                    .replace(UNIT_SEP, " ")
                )
                values.append(s_val)

        return UNIT_SEP.join(values) + RECORD_SEP + "\n"

    @classmethod
    def validate_record(cls: Type[T], usv_line: str) -> Tuple[bool, Optional[T], str]:
        """
        Validates a single USV record against this model's schema.
        Returns (is_valid, parsed_model, error_message).
        """
        line = usv_line.strip(RECORD_SEP + "\n")
        if not line:
            return False, None, "Empty line"

        parts = line.split(UNIT_SEP)
        # Only consider non-excluded fields for validation
        field_names = [f for f, info in cls.model_fields.items() if not info.exclude]

        if len(parts) < len(field_names):
            parts.extend([""] * (len(field_names) - len(parts)))

        if len(parts) != len(field_names):
            logger.info(
                f"Field count mismatch: expected {len(field_names)}, got {len(parts)}. Parts: {parts}"
            )
            return (
                False,
                None,
                f"Field count mismatch: expected {len(field_names)}, got {len(parts)}",
            )

            return (
                False,
                None,
                f"Field count mismatch: expected {len(field_names)}, got {len(parts)}",
            )

            return (
                False,
                None,
                f"Field count mismatch: expected {len(field_names)}, got {len(parts)}",
            )

        data = {}
        for i, field_name in enumerate(field_names):
            if i < len(parts):
                val = parts[i]
                if val == "":
                    # Skip empty strings, letting Pydantic handle defaults
                    continue

                # Check for list fields (semicolon separated)
                field_info = cls.model_fields[field_name]
                if "List" in str(field_info.annotation):
                    data[field_name] = [t.strip() for t in val.split(";") if t.strip()]
                else:
                    data[field_name] = val  # type: ignore[assignment]

        try:
            model = cls.model_validate(data)
            return True, model, ""
        except ValidationError as e:
            return False, None, f"Validation error: {e}"

    @classmethod
    def validate_file(
        cls: Type[T], usv_path: Path, invalid_path: Optional[Path] = None
    ) -> Dict[str, int]:
        """
        Validates all records in a USV file.
        Writes invalid records to invalid_path if provided.
        Returns metrics dict.
        """
        metrics = {"total": 0, "valid": 0, "invalid": 0}

        if invalid_path:
            invalid_path.parent.mkdir(parents=True, exist_ok=True)
            f_invalid = open(invalid_path, "w", encoding="utf-8")
        else:
            f_invalid = None

        try:
            with open(usv_path, "r", encoding="utf-8") as f:
                for line in f:
                    metrics["total"] += 1
                    is_valid, _, error = cls.validate_record(line)

                    if is_valid:
                        metrics["valid"] += 1
                    else:
                        metrics["invalid"] += 1
                        if f_invalid:
                            f_invalid.write(f"{line.strip()} | Error: {error}\n")

            return metrics
        finally:
            if f_invalid:
                f_invalid.close()

    @classmethod
    def from_usv(cls: Type[T], usv_str: str) -> T:
        """Parses a Unit-Separated Value string into a model instance."""
        # Strip both Record Separator and Newline
        line = usv_str.strip("\x1e\n")
        if not line:
            raise ValueError(f"Empty or invalid USV line for {cls.__name__}")

        parts = line.split(UNIT_SEP)
        field_names = list(cls.model_fields.keys())

        data: Dict[str, Any] = {}
        for i, field_name in enumerate(field_names):
            if i < len(parts):
                val: Any = parts[i]
                if val == "":
                    # Skip empty strings, letting Pydantic handle defaults
                    continue

                # Check for list fields (semicolon separated)
                field_info = cls.model_fields[field_name]
                if "List" in str(field_info.annotation):
                    data[field_name] = [t.strip() for t in val.split(";") if t.strip()]
                else:
                    data[field_name] = val

        return cls.model_validate(data)

    @classmethod
    def get_schema_hash(cls) -> str:
        """Generate a deterministic hash of the current schema."""
        import hashlib
        import json

        fields = cls.get_datapackage_fields()
        schema_str = json.dumps(fields, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(schema_str.encode()).hexdigest()[:16]

    @classmethod
    def get_datapackage_fields(cls) -> List[Dict[str, Any]]:
        """Generates Frictionless Data field definitions from Pydantic metadata."""
        fields = []
        for name, field in cls.model_fields.items():
            # SKIP excluded fields
            if field.exclude:
                continue

            raw_type = field.annotation
            field_type = "string"

            type_str = str(raw_type).lower()
            if "int" in type_str:
                field_type = "integer"
            elif "float" in type_str or "decimal" in type_str:
                field_type = "number"
            elif "datetime" in type_str:
                field_type = "datetime"
            elif "bool" in type_str:
                field_type = "boolean"

            field_def = {
                "name": name,
                "type": field_type,
                "description": field.description or "",
            }

            # Add constraints from Pydantic Field metadata
            constraints = {}
            for meta in field.metadata:
                if hasattr(meta, "min_length") and meta.min_length is not None:
                    constraints["minLength"] = meta.min_length
                if hasattr(meta, "max_length") and meta.max_length is not None:
                    constraints["maxLength"] = meta.max_length
                if hasattr(meta, "ge") and meta.ge is not None:
                    constraints["minimum"] = meta.ge
                if hasattr(meta, "le") and meta.le is not None:
                    constraints["maximum"] = meta.le

            if constraints:
                field_def["constraints"] = constraints  # type: ignore[assignment]

            fields.append(field_def)
        return fields

    @classmethod
    def get_datapackage(
        cls, resource_name: str, resource_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Returns a Frictionless Data Package schema with path strategy."""

        # Determine the path pattern: explicit override or model-level policy
        if resource_path:
            pattern = resource_path
        elif hasattr(cls, "RESOURCE_PATH_PATTERN"):
            pattern = cls.RESOURCE_PATH_PATTERN.value
        else:
            pattern = ResourcePathPolicy.RECURSIVE.value

        return {
            "profile": "tabular-data-package",
            "name": resource_name,
            "resources": [
                {
                    "name": resource_name,
                    "path": pattern,
                    "format": "usv",
                    "dialect": {"delimiter": UNIT_SEP, "header": False},
                    "schema": {"fields": cls.get_datapackage_fields()},
                }
            ],
        }

    @classmethod
    def save_datapackage(
        cls,
        path: Path,
        resource_name: str,
        resource_path: str,
        force: bool = False,
        wasi_hash: Optional[str] = None,
    ) -> None:
        """
        Saves the datapackage.json to the specified directory.
        Enforces strict schema compliance (Append-Only) unless force=True.

        Auto-Validation:
        - If existing datapackage.json has NO schema_hash, it's an old schema
          (from before ledger system). Auto-regenerate with new hash.
        - If existing datapackage.json HAS schema_hash, validate it matches model.
        - Mismatches raise SchemaConflictError unless force=True.
        """
        path.mkdir(parents=True, exist_ok=True)
        new_schema = cls.get_datapackage(resource_name, resource_path)

        # 1. Update Schema Info
        if hasattr(cls, "SCHEMA_UPDATED_AT"):
            new_schema["cocli:schema_updated_at"] = cls.SCHEMA_UPDATED_AT
        else:
            # Fallback for models without explicit updated timestamp
            from datetime import datetime, timezone

            new_schema["cocli:generated_at"] = datetime.now(timezone.utc).isoformat()

        current_hash = cls.get_schema_hash()
        new_schema["cocli:schema_hash"] = current_hash

        # 2. Add WASI sentinel if provided
        if wasi_hash:
            new_schema["cocli:wasi_hash"] = wasi_hash

        # 3. Update Ledger
        ledger_path = Path("schema_ledger.json")
        ledger = {}
        if ledger_path.exists():
            with open(ledger_path, "r") as f:
                ledger = json.load(f)

        if resource_name not in ledger:
            ledger[resource_name] = {"current_hash": "", "history": []}

        if ledger[resource_name]["current_hash"] != current_hash:
            timestamp = new_schema.get("cocli:schema_updated_at") or new_schema.get(
                "cocli:generated_at"
            )
            ledger[resource_name]["history"].append(
                {"hash": current_hash, "timestamp": timestamp}
            )
            ledger[resource_name]["current_hash"] = current_hash

            with open(ledger_path, "w") as f:
                json.dump(ledger, f, indent=2)

        new_fields = new_schema["resources"][0]["schema"]["fields"]

        sentinel_path = path / "datapackage.json"

        # Check existing datapackage.json
        if sentinel_path.exists() and not force:
            try:
                with open(sentinel_path, "r") as f:
                    old_schema = json.load(f)

                # AUTO-VALIDATION: Check for old schema without hash
                existing_hash = old_schema.get("cocli:schema_hash")

                if existing_hash is None:
                    # OLD SCHEMA DETECTED - Auto-regenerate with new hash
                    logger.warning(
                        f"Old datapackage.json without schema_hash detected for {resource_name}. "
                        f"Auto-regenerating with current model hash ({current_hash[:8]}...)."
                    )
                    # Skip validation, allow overwrite
                else:
                    # Has hash - validate matches model
                    if existing_hash != current_hash:
                        old_fields = old_schema["resources"][0]["schema"]["fields"]
                        old_field_names = ", ".join([f["name"] for f in old_fields])
                        new_field_names = ", ".join([f["name"] for f in new_fields])

                        # Check if this is an append-only change (new fields added at end)
                        is_append_only = True
                        if len(new_fields) < len(old_fields):
                            is_append_only = False  # Field count decreased
                        else:
                            # Check that existing fields haven't changed
                            for i, old_f in enumerate(old_fields):
                                if i >= len(new_fields):
                                    break
                                new_f = new_fields[i]
                                if (
                                    old_f["name"] != new_f["name"]
                                    or old_f["type"] != new_f["type"]
                                ):
                                    is_append_only = False
                                    break

                        if not is_append_only:
                            raise SchemaConflictError(
                                f"Model: {cls.__name__} | Schema hash mismatch! Model: {current_hash[:8]}, File: {existing_hash[:8]}. "
                                f"Old fields: {old_field_names} | New fields: {new_field_names}",
                                [
                                    f"Hash changed: {existing_hash[:8]} -> {current_hash[:8]}"
                                ],
                            )

                    # Hash matches or append-only change - validate field structure (Append-Only)
                    old_fields = old_schema["resources"][0]["schema"]["fields"]

                    # 1. Compare field count
                    if len(new_fields) < len(old_fields):
                        old_field_names = ", ".join([f["name"] for f in old_fields])
                        new_field_names = ", ".join([f["name"] for f in new_fields])
                        raise SchemaConflictError(
                            f"Model: {cls.__name__} | Field count decreased ({len(old_fields)} -> {len(new_fields)}). This will break existing USV records. | Old fields: {old_field_names} | New fields: {new_field_names}",
                            [f"- {f['name']}" for f in old_fields[len(new_fields) :]],
                        )

                    # 2. Compare existing field order and types
                    diff = []
                    for i, old_f in enumerate(old_fields):
                        if i >= len(new_fields):
                            break
                        new_f = new_fields[i]
                        if old_f["name"] != new_f["name"]:
                            diff.append(
                                f"Position {i}: Expected '{old_f['name']}', found '{new_f['name']}'"
                            )
                        elif old_f["type"] != new_f["type"]:
                            diff.append(
                                f"Position {i} ({old_f['name']}): Expected type '{old_f['type']}', found '{new_f['type']}'"
                            )

                    if diff:
                        raise SchemaConflictError(
                            "Schema change detected in existing columns. USV data is positional; you must only APPEND new fields.",
                            diff,
                        )

            except (KeyError, IndexError) as e:
                logger.warning(
                    f"Existing datapackage.json is malformed or incompatible: {e}. Overwriting."
                )
            except SchemaConflictError:
                raise
            except Exception as e:
                logger.error(f"Error validating schema against {sentinel_path}: {e}")

        with open(sentinel_path, "w") as f:
            json.dump(new_schema, f, indent=2)

    @classmethod
    def save_usv_with_datapackage(
        cls: Type[T],
        items: List[T],
        output_path: Path,
        resource_name: Optional[str] = None,
    ) -> None:
        """
        Saves a list of models as a headerless USV file and ensures a co-located
        datapackage.json is present.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(item.to_usv())

        # Save datapackage.json in the same directory
        res_name = resource_name or output_path.stem
        cls.save_datapackage(output_path.parent, res_name, output_path.name)

    def save_usv(self, path: Path) -> None:
        """Saves this single instance as a USV record to the specified path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_usv())
