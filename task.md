# Current Task: Refactor Queue System to V2 (Distributed Filesystem Queue)

## Objective
Refactor the filesystem-based queue to use a nested, atomic locking structure (`pending/{hash}/task.json` + `lease.json`) to improve robustness, observability, and data organization for the distributed RPI cluster.

## Current Status (2026-01-11)
- **Cluster Status:** `cocli5x0` (RPi 5) is successfully processing enrichment tasks using the new V2 Filesystem Queue.
- **Queue System:** V2 (Distributed Filesystem Queue) implemented and verified.
    - **Atomic Locking:** `lease.json` + `O_EXCL` prevents race conditions.
    - **S3 Sync:** Supervisor correctly syncs tasks DOWN, results UP, and ACKs deletions to S3.
    - **Robustness:** System recovers from restarts without losing data or duplicating work (mostly).
- **Bulk Processing:** Batch of 100 items enqueued and currently processing on `cocli5x0`.

## Key Changes (V2)
- **Centralized Location:** `data/queues/<campaign>/<queue>/`.
- **Atomic Locking:** Co-located `lease.json` inside `pending/{hash}/` using `O_EXCL`.
- **Completion:** Successful tasks move to `completed/{hash}.json` (flattened).

## Next Steps
1.  **Monitor Bulk Batch:** Allow the current batch of 100 items to finish.
2.  **Scale Up:** Enqueue the rest of the 18,000 items.
3.  **Update Other Workers:** Deploy the V2 code to `octoprint` (Pi 4) and other nodes.
4.  **Refine Reporting:** Ensure `campaign_report.py` fully utilizes the new `completed/` directory for stats.

## TODO Track
- [x] **Update Documentation:** `task.md` and `queue-design.md`.
- [x] **Refactor `FilesystemQueue`:** Implement V2 class.
- [x] **Migration Script:** Move existing pending items.
- [x] **Update Reporting:** Fix stats counters.
- [x] **Verify:** Run on local/test environment.
- [x] **Deploy & Test:** Successfully running on `cocli5x0`.