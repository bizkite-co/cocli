"""Substrate primitives: config, paths, queue/WAL/index, claim/lease, audit.

This package is the primary library-extraction candidate for the reusable stations /
typed file-path-queue substrate (see ``docs/DESCRIPTION.md``).

Layering (two orthogonal axes — do not collapse them):

* Extraction axis: ``core`` holds the cache/audit/DFQ machinery and path-grammar
  contracts that may become a standalone package. ``cocli.application`` and
  ``cocli.services`` are product code and stay in cocli.
* Intra-product axis (does not apply here): orchestration vs infra-driver is a split
  *among* product packages only — not a reason to park product services under
  ``core``.

Import-linter enforces that ``core`` must not import ``application``, ``services``,
``commands``, or ``tui``. See ``docs/cli/target-tree.md`` §3.1 and ``CLAUDE.md``
("Three-tier layering").
"""
