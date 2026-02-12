from pydantic import Field
from typing import Optional, List, Dict, Any, ClassVar
from datetime import datetime, UTC
from .domain import Domain
from .email_address import EmailAddress
from .phone import OptionalPhone
from .base_index import BaseIndexModel

class WebsiteDomainCsv(BaseIndexModel):
    INDEX_NAME: ClassVar[str] = "domains"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def get_header(cls) -> str:
        """Returns the USV header line."""
        return "\x1f".join(cls.model_fields.keys())

    def to_usv(self) -> str:
        """Serializes the model to a single-line unit-separated string."""
        values = []
        dump = self.model_dump()
        for field in self.__class__.model_fields.keys():
            val = dump.get(field)
            if val is None:
                values.append("")
            elif isinstance(val, (list, tuple)):
                # Use a semicolon as a secondary separator for lists within a field
                sanitized_list = [str(v).replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>") for v in val]
                values.append(";".join(sanitized_list))
            elif isinstance(val, datetime):
                values.append(val.isoformat())
            else:
                values.append(str(val).replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>"))
        return "\x1f".join(values) + "\n"

    @classmethod
    def from_usv(cls, usv_str: str) -> "WebsiteDomainCsv":
        """Parses a unit-separated line into a WebsiteDomainCsv object."""
        # Strip both Record Separator and Newline
        line = usv_str.strip("\x1e\n")
        if not line:
            raise ValueError("Empty USV line")
            
        parts = line.split("\x1f")
        fields = list(cls.model_fields.keys())
        
        data: Dict[str, Any] = {}
        for i, field_name in enumerate(fields):
            if i < len(parts):
                val = parts[i]
                if val == "":
                    # Defaults for nullable vs non-nullable
                    if field_name == "tags":
                        data[field_name] = []
                    elif field_name == "is_email_provider":
                        data[field_name] = False
                    elif field_name in ["created_at", "updated_at"]:
                        data[field_name] = datetime.now(UTC)
                    else:
                        data[field_name] = None
                else:
                    if field_name == "tags":
                        data[field_name] = [t.strip() for t in val.split(";") if t.strip()]
                    elif field_name == "is_email_provider":
                        data[field_name] = val.lower() == "true"
                    elif field_name == "scraper_version":
                        try:
                            data[field_name] = int(val)
                        except (ValueError, TypeError):
                            data[field_name] = 1
                    elif field_name in ["created_at", "updated_at"]:
                        try:
                            data[field_name] = datetime.fromisoformat(val)
                        except ValueError:
                            data[field_name] = datetime.now(UTC)
                    else:
                        data[field_name] = val
            else:
                # Schema drift: part missing in older file
                if field_name == "tags":
                    data[field_name] = []
                elif field_name == "is_email_provider":
                    data[field_name] = False
                elif field_name in ["created_at", "updated_at"]:
                    data[field_name] = datetime.now(UTC)
                else:
                    data[field_name] = None
        
        return cls.model_validate(data)