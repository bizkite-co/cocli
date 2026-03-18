# PI Results SyncTracker

Automatic synchronization of Google Maps list results from Raspberry Pi workers.

## Overview

The SyncTracker ensures that the latest gm-list results from Pi workers are available locally for compaction. It runs automatically when the TUI starts (if stale) or can be triggered manually.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        COCLI Application                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  TUI Init    │───▶│ SyncTracker  │───▶│ Background Sync   │  │
│  │ (auto-check) │    │ (1hr check)  │    │ (detached rsync)  │  │
│  └──────────────┘    └──────────────┘    └──────────────────┘  │
│         │                   │                     │              │
│         ▼                   ▼                     ▼              │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                  Timestamp File                             │ │
│  │  data/campaigns/{campaign}/.last_pi_sync                    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `scripts/sync_pi_results.py` | Standalone rsync script |
| `cocli/core/sync_tracker.py` | Read/write last-sync timestamps |
| `cocli/commands/sync.py` | CLI command `cocli sync-pi-results` |
| `cocli/application/pi_sync_service.py` | Background sync logic |
| `cocli/tui/widgets/application_view.py` | Auto-sync on TUI startup |
| `data/campaigns/{campaign}/.last_pi_sync` | Timestamp file |

## Timestamp File

| Property | Value |
|----------|-------|
| **Location** | `data/campaigns/{campaign}/.last_pi_sync` |
| **Format** | ISO 8601 datetime string |
| **Example** | `2026-03-18T10:30:00+00:00` |

## Components

### SyncTracker

```python
class SyncTracker:
    """Manages PI sync timestamps for a campaign."""
    
    timestamp_file: Path  # data/campaigns/{campaign}/.last_pi_sync
    
    def get_last_sync() -> Optional[datetime]
    def needs_sync(threshold_hours: float = 1.0) -> bool
    def update_last_sync() -> None
```

### CLI Commands

```bash
# Manual sync (blocks)
cocli sync-pi-results --campaign roadmap

# Manual sync with force (ignores timestamp)
cocli sync-pi-results --campaign roadmap --force

# Check status
cocli sync-pi-results --campaign roadmap --status
# Output: Last sync: 2026-03-18 10:30:00 (30 minutes ago)
```

### Rsync Command

```bash
rsync -avz --progress \
  mstouffer@{host}:repos/data/campaigns/{campaign}/queues/gm-list/completed/results/ \
  {local}/data/campaigns/{campaign}/queues/gm-list/completed/results/
```

## TUI Auto-Sync

On TUI startup or campaign switch:
1. Check `SyncTracker.needs_sync()` (threshold: 1 hour)
2. If stale, spawn detached background sync
3. Update `.last_pi_sync` on completion

## Pipeline Integration

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│ Sync from PIs│────▶│ Compaction   │────▶│ Checkpoint       │
│ (auto/manual)│     │ op_compact   │     │ (ratings data)   │
└──────────────┘     └──────────────┘     └──────────────────┘
```

## Worker Nodes

Configured in `data/config/cocli_config.toml`:

```toml
[cluster]
nodes = [
    { host = "cocli5x1.pi", ip = "10.0.0.17", label = "Pi 5x1" },
    { host = "coclimicrosd.pi", ip = "10.0.0.12", label = "Pi 3 (SD)" },
    { host = "cocliusbssd.pi", ip = "10.0.0.200", label = "Pi 4 (SSD)" },
]
```

## Implementation Tasks

- [x] Update `docs/_schema/rpi-worker/README.md` to reflect data path
- [x] Create `scripts/sync_pi_results.py`
- [x] Create `cocli/core/sync_tracker.py`
- [x] Add CLI command to `cocli/commands/sync.py`
- [x] Create `cocli/application/pi_sync_service.py`
- [x] Integrate auto-sync into TUI startup
