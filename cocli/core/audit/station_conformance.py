"""Index-station conformance audit (decision 0010).

Reports where the live index tree disagrees with its ``StationDecl`` instead
of raising. Queues can afford a raising validator because every queue family
the code touches is declared; only three of the ten index families on disk
are, so a raising ``IndexPaths`` would break working code before it told
anyone anything.

Read-only: this never creates, moves, or deletes a path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from stations.segments import collect_phases

from cocli.core.paths import paths
from cocli.station_defs.campaigns.indexes import station_for_index

_SAMPLE_LIMIT = 5


class FindingKind(str, Enum):
    UNDECLARED_FAMILY = "undeclared-family"
    UNDECLARED_CHILD = "undeclared-child"
    DECLARED_PHASE_ABSENT = "declared-phase-absent"
    NAKED_FILE = "naked-file"


@dataclass(frozen=True)
class Finding:
    kind: FindingKind
    campaign: str
    index_name: str
    detail: str
    path: Path


def audit_index_stations(
    campaigns_root: Optional[Path] = None,
    campaign: Optional[str] = None,
) -> list[Finding]:
    """Compare every campaign's indexes/ tree against its station decls."""
    root = campaigns_root if campaigns_root is not None else paths.campaigns
    findings: list[Finding] = []
    if not root.is_dir():
        return findings

    for campaign_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if campaign and campaign_dir.name != campaign:
            continue
        indexes_dir = campaign_dir / "indexes"
        if not indexes_dir.is_dir():
            continue
        for entry in sorted(indexes_dir.iterdir()):
            if entry.is_dir():
                findings.extend(_audit_family(campaign_dir.name, entry))
            else:
                findings.append(
                    Finding(
                        kind=FindingKind.NAKED_FILE,
                        campaign=campaign_dir.name,
                        index_name=entry.name,
                        detail="file in the indexes/ root; every index is a directory",
                        path=entry,
                    )
                )
    return findings


def _audit_family(campaign: str, family_dir: Path) -> list[Finding]:
    name = family_dir.name
    station = station_for_index(name)
    if station is None:
        return [
            Finding(
                kind=FindingKind.UNDECLARED_FAMILY,
                campaign=campaign,
                index_name=name,
                detail=(
                    "no StationDecl; declare it under "
                    "cocli/station_defs/campaigns/indexes/ or park it deliberately"
                ),
                path=family_dir,
            )
        ]

    phases = collect_phases(station.segments)
    declared: set[str] = set(phases.names) if phases is not None else set()
    on_disk = {p.name for p in family_dir.iterdir() if p.is_dir()}

    findings: list[Finding] = []
    extras = sorted(on_disk - declared)
    if extras:
        sample = ", ".join(extras[:_SAMPLE_LIMIT])
        more = (
            f" (+{len(extras) - _SAMPLE_LIMIT} more)"
            if len(extras) > _SAMPLE_LIMIT
            else ""
        )
        findings.append(
            Finding(
                kind=FindingKind.UNDECLARED_CHILD,
                campaign=campaign,
                index_name=name,
                detail=(
                    f"{len(extras)} director(ies) under this index are not phases of "
                    f"station {station.name!r} (declares {sorted(declared)}): "
                    f"{sample}{more}"
                ),
                path=family_dir,
            )
        )

    # Declared-but-absent is informational: which directories exist is a
    # runtime value question, not a declaration error (stations PHYSICAL).
    for missing in sorted(declared - on_disk):
        findings.append(
            Finding(
                kind=FindingKind.DECLARED_PHASE_ABSENT,
                campaign=campaign,
                index_name=name,
                detail=f"station {station.name!r} declares {missing}/ but it does not exist",
                path=family_dir / missing,
            )
        )
    return findings
