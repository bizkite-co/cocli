"""Low-level infrastructure drivers for the cocli product.

This package is product-specific. It is NOT a stations-library extraction candidate.

Place modules here when they are infra drivers — SSH into workers, Docker managers,
S3 bucket helpers, WAL I/O adapters, cluster deploy/ops tooling — not domain
workflows. Domain/orchestration services belong in ``cocli.application``.

Layering (two orthogonal axes — do not collapse them):

* Extraction axis: only ``cocli.core`` (queue/WAL/index primitives) may later leave
  cocli as the reusable stations substrate. ``application`` and ``services`` both
  stay in cocli regardless of this internal split.
* Intra-product axis: ``services`` = infra drivers; ``application`` = domain/
  orchestration. Example: ``ClusterService`` (SSH + docker on Pi nodes) is correctly
  here, not under ``application`` and not under ``core``.

See ``docs/cli/target-tree.md`` §3.1 and ``CLAUDE.md`` ("Three-tier layering").
"""
