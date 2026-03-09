# POLICY: frictionless-data-policy-enforcement
import json
import logging
from enum import Enum
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Type, TypeVar, Optional
from pydantic import BaseModel

from ..core.constants import UNIT_SEP

logger = logging.getLogger(__name__)

class SchemaConflictError(Exception):
    """Raised when a Pydantic model change would break existing USV data positioning."""
    def __init__(self, message: str, diff: List[str]):
        super().__init__(message)
        self.diff = diff

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
        from ..core.constants import UNIT_SEP
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
                    str(v).replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>").replace(UNIT_SEP, " ") 
                    for v in val
                ]
                values.append(";".join(sanitized_list))
            elif isinstance(val, datetime):
                values.append(val.isoformat())
            else:
                # Sanitize all other fields for newlines and separators
                s_val = str(val).replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>").replace(UNIT_SEP, " ")
                values.append(s_val)
        
        from ..core.constants import UNIT_SEP, RECORD_SEP
        return UNIT_SEP.join(values) + RECORD_SEP + "\n"

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
                val = parts[i]
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
    def get_datapackage_fields(cls) -> List[Dict[str, str]]:
        """Generates Frictionless Data field definitions from Pydantic metadata."""
        fields = []
        for name, field in cls.model_fields.items():
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
                
            fields.append({
                "name": name,
                "type": field_type,
                "description": field.description or ""
            })
        return fields

    @classmethod
    def get_datapackage(cls, resource_name: str, resource_path: str) -> Dict[str, Any]:
        """Returns a Frictionless Data Package schema."""
        return {
            "profile": "tabular-data-package",
            "name": resource_name,
            "resources": [
                {
                    "name": resource_name,
                    "path": resource_path,
                    "format": "usv",
                    "dialect": {"delimiter": UNIT_SEP, "header": False},
                    "schema": {"fields": cls.get_datapackage_fields()}
                }
            ]
        }

    @classmethod
    def save_datapackage(cls, path: Path, resource_name: str, resource_path: str, force: bool = False, wasi_hash: Optional[str] = None) -> None:
        """
        Saves the datapackage.json to the specified directory.
        Enforces strict schema compliance (Append-Only) unless force=True.
        """
        path.mkdir(parents=True, exist_ok=True)
        new_schema = cls.get_datapackage(resource_name, resource_path)
        
        # Add WASI sentinel if provided
        if wasi_hash:
            new_schema["cocli:wasi_hash"] = wasi_hash
            
        new_fields = new_schema["resources"][0]["schema"]["fields"]
        
        sentinel_path = path / "datapackage.json"
        if sentinel_path.exists() and not force:
            try:
                with open(sentinel_path, "r") as f:
                    old_schema = json.load(f)
                    old_fields = old_schema["resources"][0]["schema"]["fields"]
                    
                # 1. Compare field count
                if len(new_fields) < len(old_fields):
                    raise SchemaConflictError(
                        f"Field count decreased ({len(old_fields)} -> {len(new_fields)}). This will break existing USV records.",
                        [f"- {f['name']}" for f in old_fields[len(new_fields):]]
                    )
                
                # 2. Compare existing field order and types
                diff = []
                for i, old_f in enumerate(old_fields):
                    new_f = new_fields[i]
                    if old_f["name"] != new_f["name"]:
                        diff.append(f"Position {i}: Expected '{old_f['name']}', found '{new_f['name']}'")
                    elif old_f["type"] != new_f["type"]:
                        diff.append(f"Position {i} ({old_f['name']}): Expected type '{old_f['type']}', found '{new_f['type']}'")
                
                if diff:
                    raise SchemaConflictError(
                        "Schema change detected in existing columns. USV data is positional; you must only APPEND new fields.",
                        diff
                    )
                    
            except (KeyError, IndexError) as e:
                logger.warning(f"Existing datapackage.json is malformed or incompatible: {e}. Overwriting.")
            except SchemaConflictError:
                raise
            except Exception as e:
                logger.error(f"Error validating schema against {sentinel_path}: {e}")

        with open(sentinel_path, "w") as f:
            json.dump(new_schema, f, indent=2)

    @classmethod
    def save_usv_with_datapackage(cls: Type[T], items: List[T], output_path: Path, resource_name: Optional[str] = None) -> None:
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
