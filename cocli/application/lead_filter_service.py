"""Materializes a campaign's lead-filter verdicts to indexes/lead-filter/,
keeping the algorithmic filter and the human call-log disposition converged
on one campaign-wide invalid set instead of two disconnected lists.

The filter *criteria* (what counts as off-topic for a given campaign's
vertical) stay campaign-specific and out of this module - only the
materialization (write in.usv/out.usv + datapackage.json, sync with
ExclusionManager) is shared.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..core.exclusions import ExclusionManager
from ..models.campaigns.indexes.lead_filter import LeadFilterEntry


def write_lead_filter_entries(
    campaign: str, entries: Iterable[LeadFilterEntry]
) -> tuple[Path, Path]:
    """Writes entries to indexes/lead-filter/{in,out}.usv and reconciles
    with ExclusionManager in both directions:

    - Feed-backward: a company already marked invalid (e.g. via the call
      log's Wrong Trade / No Fit disposition) is forced to "out" here even
      if the algorithmic criteria would have kept it - a human verdict
      always wins.
    - Feed-forward: every algorithmic "out" verdict becomes a durable,
      campaign-wide exclusion too, so a filtered-out company doesn't
      quietly resurface in to-call compilation or any other exclusion
      check that already consults ExclusionManager.

    Returns (in_path, out_path).
    """
    excl = ExclusionManager(campaign)

    resolved: list[LeadFilterEntry] = []
    for entry in entries:
        existing = excl.get_exclusion(domain=entry.domain, slug=entry.slug)
        if entry.verdict != "out" and existing is not None:
            entry = entry.model_copy(
                update={
                    "verdict": "out",
                    "reason": entry.reason or existing.reason or "marked invalid (Wrong Trade / No Fit)",
                }
            )
        resolved.append(entry)

    in_entries = [e for e in resolved if e.verdict != "out"]
    out_entries = [e for e in resolved if e.verdict == "out"]

    index_dir = LeadFilterEntry.get_index_dir(campaign)
    index_dir.mkdir(parents=True, exist_ok=True)

    in_path = index_dir / "in.usv"
    out_path = index_dir / "out.usv"
    in_path.write_text("".join(e.to_usv() for e in in_entries), encoding="utf-8")
    out_path.write_text("".join(e.to_usv() for e in out_entries), encoding="utf-8")

    # append_resource_to_datapackage (not write_datapackage) because in.usv
    # and out.usv are two resources sharing one datapackage.json in the same
    # directory - write_datapackage would have each call clobber the other.
    LeadFilterEntry.append_resource_to_datapackage(index_dir, "lead_filter_in", "in.usv")
    LeadFilterEntry.append_resource_to_datapackage(index_dir, "lead_filter_out", "out.usv")

    for e in out_entries:
        if not excl.is_excluded(domain=e.domain, slug=e.slug):
            excl.add_exclusion(slug=e.slug, domain=e.domain, reason=e.reason or "lead-filter: out")

    return in_path, out_path
