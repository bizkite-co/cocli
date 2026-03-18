# RPi Worker Internal Structure

## Data Root

The RPis use a shadow folder structure mirrored from the local development environment:

| RPi Path | Description |
|----------|-------------|
| `$HOME/repos/data/` | Local data root (mirrors `cocli_data/` on dev machines) |

## Environment Mapping

| Environment | Data Root Path |
|-------------|----------------|
| Local (Dev) | `~/repos/company-cli/data/` or `~/.local/share/cocli_data/` |
| RPi Cluster | `$HOME/repos/data/` |
| S3 | `s3://cocli-data-{campaign}/` |

## Directory Structure

```
repos/data/
├── campaigns/
│   └── {campaign}/
│       ├── indexes/
│       ├── queues/
│       │   └── gm-list/
│       │       └── completed/
│       │           └── results/     # <-- Synced to DEV/PROD
│       └── .last_pi_sync           # <-- SyncTracker timestamp
├── companies/
├── config/
├── indexes/
├── queues/
├── remote_updates/
├── scraped_data/
└── wal/
```

## Sync Convention

| Property | Value |
|----------|-------|
| **Source** | RPi `repos/data/campaigns/{campaign}/queues/gm-list/completed/results/` |
| **Destination** | Local `data/campaigns/{campaign}/queues/gm-list/completed/results/` |
| **Tool** | `rsync` over local network |
| **Trigger** | TUI auto-sync (hourly) or manual CLI |

## SSH Access

Workers are configured in `data/config/cocli_config.toml`:

```toml
[cluster]
registry_host = "cocli5x1.pi"
nodes = [
    { host = "cocli5x1.pi", ip = "10.0.0.17", label = "Pi 5x1" },
    { host = "coclimicrosd.pi", ip = "10.0.0.12", label = "Pi 3 (SD)" },
    { host = "cocliusbssd.pi", ip = "10.0.0.200", label = "Pi 4 (SSD)" },
]
```

SSH login: `ssh mstouffer@{host}` (e.g., `ssh mstouffer@cocli5x1.pi`)
