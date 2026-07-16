"""Domain and orchestration services for the cocli product.

This package is product-specific. It is NOT a stations-library extraction candidate.

Layering (two orthogonal axes — do not collapse them):

* Extraction axis: only ``cocli.core`` (queue/WAL/index primitives) may later leave cocli
  as the reusable typed file-path-queue / stations substrate. ``application`` and
  ``services`` both stay in cocli.
* Intra-product axis: ``application`` holds domain/orchestration services (meetings,
  tasks, workers, companies, …). Infra drivers (SSH, Docker, S3, WAL ops) live in
  ``cocli.services``.

Commands are thin adapters over this layer. See ``docs/cli/target-tree.md`` §3.1 and
``CLAUDE.md`` ("Three-tier layering").
"""
