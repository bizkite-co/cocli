# Current Task: Refactor Queue System to V2 (Distributed Filesystem Queue)

## Objective
Refactor the filesystem-based queue to use a nested, atomic locking structure (`pending/{hash}/task.json` + `lease.json`) to improve robustness, observability, and data organization for the distributed RPI cluster.

## Current Status (2026-01-11)
- **Cluster Status:** Workers stopped to allow for architecture migration.
- **Legacy Queue:** Currently using `frontier/` and separated `active-leases/`.
- **Target Architecture:** V2 design documented in `docs/data-management/queue-design.md`.
- **Primary Test Node:** `cocli5x0` (RPi 5) will be the first deployment target.

## Key Changes (V2)
- **Centralized Location:** `data/queues/<campaign>/<queue>/`.
- **Atomic Locking:** Co-located `lease.json` inside `pending/{hash}/` using `O_EXCL`.
- **Completion:** Successful tasks move to `completed/{hash}.json` (flattened).

## Next Steps
1.  **Refactor Code:** Update `cocli/core/queue/filesystem.py` to implement V2 logic.
2.  **Migrate Data:** Script to move existing `frontier/` items to new `queues/.../pending/` structure.
3.  **Update Reporting:** Point `cocli/core/reporting.py` to new paths.
4.  **Deploy & Test:** Deploy to `cocli5x0` and verify processing.

## TODO Track
- [x] **Update Documentation:** `task.md` and `queue-design.md`.
- [ ] **Refactor `FilesystemQueue`:** Implement V2 class.
- [ ] **Migration Script:** Move existing pending items.
- [ ] **Update Reporting:** Fix stats counters.
- [ ] **Verify:** Run on local/test environment.