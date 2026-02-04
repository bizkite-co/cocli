# Raspberry Pi Worker Deployment Layout

This document catalogs the file system and container structure for the `cocli` workers running on Raspberry Pi nodes.

## Host Environment (Pi)
- **User**: `<user>` (e.g., `mstouffer`, `pi`)
- **Home Directory**: `/home/<user>`
- **Code Repository**: `/home/<user>/repos/company-cli`
- **Persistent Data**: `/home/<user>/repos/data` (Bind-mounted into container).

## Docker Container (`cocli-supervisor`)
- **Image**: `cocli-worker-rpi:latest`
- **Working Directory**: `/app`
- **Configuration**:
    - **Data Mount**: `/app/data` <-> `/home/<user>/repos/data` (Host)
    - **AWS Credentials**: `/root/.aws` <-> `/home/<user>/.aws` (Host, Read-Only)

## Log Locations
- **Container Logs**: `docker logs cocli-supervisor` (Captures stdout/stderr of the supervisor and its spawned workers).
- **Internal Supervisor Logs**: `/app/.logs/YYYYMMDD_HHMMSS_supervisor.log` (Rotated log files inside the container).
- **Worker Scrape Log**: Historically at `/home/<user>/worker_scrape.log` on the host, but primarily captured via container stdout in current supervisor mode.

## Critical Commands
- **Rebuild/Restart**: `make rebuild-rpi-worker RPI_HOST=<node>.pi`
- **Check Status**: `ssh <node>.pi "docker ps"`
- **Tail Logs**: `ssh <node>.pi "docker logs -f cocli-supervisor"`