"""Domain-wide record: facts shared across every company (branch,
broker, franchisee) that happens to use the same domain, instead of
each company duplicating them separately.

Lives at domains/<domain>/_index.md (e.g. domains/higginbotham.com/,
not domains/higginbotham-com/ - the folder name is the domain itself,
slugdotify()'d so only characters that are actually unsafe in a path
get replaced; the dot in "higginbotham.com" stays a literal dot, so
there's no dash<->dot translation needed anywhere this is used).

Scope, deliberately minimal for now (Mark, 2026-10-02): just a place to
record a domain-wide reference URL (e.g. an employee directory page) so
there's one obvious place to look when hunting for a person's contact
info - not a scraper, not a structured contact extraction pipeline.
Screenshot/other domain-level enrichment artifact dedup is a separate,
not-yet-built follow-up.
"""

from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from .domain import Domain, to_lowercase_domain
from ..core.paths import paths
from ..core.text_utils import slugdotify


class DomainRecord(BaseModel):
    domain: Domain
    employee_directory_url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def slug_for(domain: str) -> str:
        """The one place that decides how a domain maps to a folder
        name - always slugdotify(), never the dash-only slugify(), and
        always normalized the same way the `domain` field itself is
        (strip a leading "www.", protocol, port, trailing slash) so
        get("www.higginbotham.com") and get("higginbotham.com") resolve
        to the same folder as what save() actually wrote to."""
        return slugdotify(to_lowercase_domain(domain))

    @classmethod
    def _index_path(cls, domain: str) -> Path:
        return paths.domains.entry(cls.slug_for(domain)).index

    @classmethod
    def get(cls, domain: str) -> Optional["DomainRecord"]:
        index_path = cls._index_path(domain)
        if not index_path.exists():
            return None
        content = index_path.read_text(encoding="utf-8")
        if not (content.startswith("---") and "---" in content[3:]):
            return None
        parts = content.split("---", 2)
        try:
            data: dict[str, Any] = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return None
        try:
            return cls(**data)
        except Exception:
            return None

    @classmethod
    def get_or_create(cls, domain: str) -> "DomainRecord":
        return cls.get(domain) or cls(domain=domain)

    def save(self) -> Path:
        self.updated_at = datetime.now(UTC)
        entry = paths.domains.entry(self.slug_for(self.domain), ensure=True)
        index_path = entry.index
        frontmatter_data = self.model_dump(mode="json")
        frontmatter = yaml.dump(
            frontmatter_data, sort_keys=False, default_flow_style=False, allow_unicode=True
        )
        index_path.write_text(f"---\n{frontmatter}---\n", encoding="utf-8")
        return index_path
