"""QueueLayout: single relative path for local FS and S3 (0010 path migration PR1).

Builds DFQ item paths from a StationDecl's declaration-time segments
(PhaseRef + shard combinator). Local ``Path`` and S3 key suffixes share the
same relative string so they cannot drift.

Does not change on-disk layout. Pre-sharded task ids (e.g. ``2/25.0/-80.0/x``)
are preserved the same way ``FilesystemQueue._get_task_subpath`` did.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

from stations.paths import require_phases
from stations.segments import PhaseRef, Phases, collect_shard
from stations.station import StationDecl


def _strip_known_ext(name: str) -> str:
    for ext in (".usv", ".csv", ".json"):
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


def task_rel_under_phase(
    station: StationDecl[Any],
    phase: Union[str, PhaseRef],
    task_id: str,
    *,
    use_shard: bool = True,
) -> str:
    """Relative path ``{phase}/[{shard}/]{task_id}`` (no leading slash).

    If ``task_id`` already looks sharded (first segment length ≤ 2 and more
    than one path part), do not add another shard — same rule as legacy DFQ.
    """
    ph = require_phases(station)
    ref = ph.require(phase)
    safe_id = task_id.replace("\\", "/")
    parts = [p for p in safe_id.split("/") if p]
    if len(parts) > 1 and len(parts[0]) <= 2:
        last = _strip_known_ext(parts[-1])
        parts = parts[:-1] + [last]
        return "/".join([ref.name] + parts)

    key = _strip_known_ext(safe_id)
    if not use_shard:
        return f"{ref.name}/{key}"

    sh = collect_shard(station.segments)
    if sh is None:
        return f"{ref.name}/{key}"
    shard = sh.shard_for(key)
    return f"{ref.name}/{shard}/{key}"


@dataclass(frozen=True)
class QueueLayout:
    """Layout binder: station decl + campaign/queue identity + local root."""

    station: StationDecl[Any]
    campaign_name: str
    queue_name: str
    local_root: Path

    @property
    def phases(self) -> Phases:
        return require_phases(self.station)

    def relative_item(
        self,
        phase: Union[str, PhaseRef],
        task_id: str,
        *,
        use_shard: bool = True,
    ) -> str:
        """Shared relative path under the queue root (local and S3)."""
        return task_rel_under_phase(
            self.station, phase, task_id, use_shard=use_shard
        )

    def phase_dir(self, phase: Union[str, PhaseRef]) -> Path:
        ref = self.phases.require(phase)
        return self.local_root / ref.name

    def item_dir(
        self,
        phase: Union[str, PhaseRef],
        task_id: str,
        *,
        use_shard: bool = True,
    ) -> Path:
        rel = self.relative_item(phase, task_id, use_shard=use_shard)
        return self.local_root / Path(rel)

    def s3_prefix(self) -> str:
        return f"campaigns/{self.campaign_name}/queues/{self.queue_name}"

    def s3_item_prefix(
        self,
        phase: Union[str, PhaseRef],
        task_id: str,
        *,
        use_shard: bool = True,
    ) -> str:
        """S3 key prefix for the task directory (no trailing file name)."""
        rel = self.relative_item(phase, task_id, use_shard=use_shard)
        return f"{self.s3_prefix()}/{rel}"

    def s3_task_key(
        self,
        phase: Union[str, PhaseRef],
        task_id: str,
        *,
        use_shard: bool = True,
    ) -> str:
        return f"{self.s3_item_prefix(phase, task_id, use_shard=use_shard)}/task.json"

    def s3_lease_key(
        self,
        phase: Union[str, PhaseRef],
        task_id: str,
        *,
        use_shard: bool = True,
    ) -> str:
        return f"{self.s3_item_prefix(phase, task_id, use_shard=use_shard)}/lease.json"

    def local_task_path(
        self,
        phase: Union[str, PhaseRef],
        task_id: str,
        *,
        use_shard: bool = True,
    ) -> Path:
        return self.item_dir(phase, task_id, use_shard=use_shard) / "task.json"

    def local_lease_path(
        self,
        phase: Union[str, PhaseRef],
        task_id: str,
        *,
        use_shard: bool = True,
    ) -> Path:
        return self.item_dir(phase, task_id, use_shard=use_shard) / "lease.json"


def default_dfq_station() -> StationDecl[object]:
    """DFQ station decl: DFQ phases + place_id 6th-char shard (algorithm-preserving)."""
    from cocli.station_defs.campaigns.queues import DFQ_QUEUE_STATION

    return DFQ_QUEUE_STATION
