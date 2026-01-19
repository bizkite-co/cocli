from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from .domain import Domain
from .email_address import EmailAddress
from .phone import OptionalPhone

class WebsiteDomainCsv(BaseModel):
    domain: Domain
    company_name: Optional[str] = None
    phone: OptionalPhone = None
    email: Optional[EmailAddress] = None
    ip_address: Optional[str] = None
    facebook_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None
    address: Optional[str] = None
    about_us_url: Optional[str] = None
    contact_url: Optional[str] = None
    services_url: Optional[str] = None
    products_url: Optional[str] = None
    tags: List[str] = []
    scraper_version: Optional[int] = 1
    associated_company_folder: Optional[str] = None
    is_email_provider: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def get_header(cls) -> str:
        """Returns the USV header line."""
        return "\x1f".join(cls.model_fields.keys())

    def to_usv(self) -> str:
        """Serializes the model to a single-line USV string."""
        values = []
        dump = self.model_dump()
        for field in self.model_fields.keys():
            val = dump.get(field)
            if val is None:
                values.append("")
            elif isinstance(val, (list, tuple)):
                # Use a semicolon as a secondary separator for lists within a field
                # Replace internal newlines with <br> to preserve data but keep it single-line
                sanitized_list = [str(v).replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>") for v in val]
                values.append(";".join(sanitized_list))
            elif isinstance(val, datetime):
                values.append(val.isoformat())
            else:
                # Replace internal newlines with <br> to preserve data but keep it single-line
                values.append(str(val).replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>"))
        return "\x1f".join(values)

    @classmethod
    def from_usv(cls, usv_str: str) -> "WebsiteDomainCsv":
        """Parses a USV string into a WebsiteDomainCsv object with schema-drift support."""
        parts = usv_str.strip("\x1e\n").split("\x1f")
        fields = list(cls.model_fields.keys())
        
        data: Dict[str, Any] = {}
        for i, field_name in enumerate(fields):
            if i < len(parts):
                val = parts[i]
                if val == "":
                    # If field is non-optional, we need a default
                    if field_name == "tags":
                        data[field_name] = []
                    elif field_name == "is_email_provider":
                        data[field_name] = False
                    elif field_name in ["created_at", "updated_at"]:
                        data[field_name] = datetime.utcnow()
                    else:
                        data[field_name] = None
                else:
                    # Type-specific conversions
                    if field_name == "tags":
                        data[field_name] = val.split(";") if val else []
                    elif field_name == "is_email_provider":
                        data[field_name] = val.lower() == "true"
                    elif field_name == "scraper_version":
                        data[field_name] = int(val) if val else None
                    elif field_name in ["created_at", "updated_at"]:
                        try:
                            data[field_name] = datetime.fromisoformat(val)
                        except ValueError:
                            data[field_name] = datetime.utcnow()
                    else:
                        data[field_name] = val
            else:
                # Schema drift: part missing in older file
                if field_name == "tags":
                    data[field_name] = []
                elif field_name == "is_email_provider":
                    data[field_name] = False
                elif field_name in ["created_at", "updated_at"]:
                    data[field_name] = datetime.utcnow()
                else:
                    data[field_name] = None
        
        return cls(**data)
