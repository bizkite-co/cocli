from __future__ import annotations
from typing import ClassVar, Literal, Optional
from .base import BaseIndexModel


class LeadFilterEntry(BaseIndexModel):
    """One row of a campaign's refined-lead-list verdict: is this company
    IN (ship to customer) or OUT (excluded), and why.

    Feeds, and is fed by, ExclusionManager (see
    application.lead_filter_service.write_lead_filter_entries) so an
    algorithmic "out" verdict here and a human's Wrong Trade / No Fit
    call-log disposition converge on the same campaign-wide invalid set,
    instead of being two disconnected "this company is bad" lists.

    All fields but slug are optional so a bare pre-schema slug list (one
    slug per line, no other fields) still parses via from_usv() -
    membership only ever depends on which physical file (in.usv/out.usv)
    a row lives in, not on the verdict field itself.
    """

    INDEX_NAME: ClassVar[str] = "lead-filter"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-09-14T00:00:00+00:00"

    slug: str
    domain: Optional[str] = None
    verdict: Optional[Literal["in", "out"]] = None
    reason: Optional[str] = None
