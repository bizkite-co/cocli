# POLICY: frictionless-data-policy-enforcement
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Type, TypeVar, Optional
from pydantic import BaseModel

from ..core.constants import UNIT_SEP

logger = logging.getLogger(__name__)

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
        
        return UNIT_SEP.join(values) + "\n"

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
    def save_datapackage(cls, path: Path, resource_name: str, resource_path: str) -> None:
        """Saves the datapackage.json to the specified directory."""
        path.mkdir(parents=True, exist_ok=True)
        schema = cls.get_datapackage(resource_name, resource_path)
        with open(path / "datapackage.json", "w") as f:
            json.dump(schema, f, indent=2)

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
