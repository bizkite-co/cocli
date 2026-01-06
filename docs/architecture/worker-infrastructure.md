# Worker Infrastructure

This document details the architecture, configuration, and operational procedures for the `cocli` worker cluster, which handles Google Maps scraping, business detailing, and website enrichment.

## Overview

The infrastructure follows a **Distributed Hybrid Model**:
1.  **Residential Workers (Raspberry Pi)**: Handle Google Maps "List" and "Detail" scraping to avoid IP blocking from AWS ranges.
2.  **Cloud Workers (AWS Fargate)**: Handle general website enrichment (emails, social links) where IP blocking is less of a concern.

## Current Cluster Configuration

| Hostname | Role | Hardware | Purpose |
| :--- | :--- | :--- | :--- |
| `octoprint.local` | Scraper | Raspberry Pi 4 | Polling `scrape_tasks` queue; Grid scanning. |
| `coclipi.local` | Details | Raspberry Pi 4 | Polling `gm_list_item` queue; Fetching GMB metadata. |
| `cocli5x0.local` | TBD | Raspberry Pi 5 | High-performance expansion node (8GB RAM). |
| `AWS Fargate` | Enrichment | Virtual (10 nodes) | Polling `enrichment` queue; Scraping business websites. |

### Optimization & Resilience
*   **Restart Policy**: All Docker workers are configured with `--restart always`. They automatically resume operation after power cycles or reboots.
*   **Resource Blocking**: To save bandwidth and improve speed, workers automatically block `images`, `fonts`, and `stylesheets`.
*   **Bandwidth Tracking**: Real-time bandwidth logging is implemented to monitor data usage and estimate proxy costs.

## Operational Commands

The `Makefile` in the project root is the primary orchestration tool.

### Cluster Management
*   `make deploy-cluster`: Rebuilds Docker images on all Pis and restarts workers with the latest code.
*   `make shutdown-cluster`: Safely halts all Pis for hardware maintenance.
*   `make restart-rpi-all`: Restarts all containers without a full rebuild.
*   `make check-cluster-health`: Verifies voltage status, throttling history, and system load for all nodes (including Pi 5).

### Deployment to New Pis
1.  **Bootstrap**: Run `make setup-rpi RPI_HOST=new-pi.local` to install Docker and Git.
2.  **Credentials**: Run `make deploy-creds-rpi RPI_HOST=new-pi.local` to push AWS profiles.
3.  **Build**: Run `make rebuild-rpi-worker RPI_HOST=new-pi.local`.
4.  **Start**: Run `make start-rpi-worker RPI_HOST=new-pi.local` (or `details-worker`).

## Expansion Options

### 1. Scaling with Raspberry Pi 5
The Raspberry Pi 5 (8GB) is the recommended hardware for expansion. `cocli5x0.local` is the first node of this type in the cluster.
*   **Target Capacity**: 4-5 concurrent browser instances per Pi 5.
*   **Requirements**: Official 27W USB-C PSU (mandatory for high-current peripherals) and Active Cooler.
*   **Optimization**: Use NVMe Base for faster I/O during heavy logging or cache operations.

### 2. Reverse Residential Proxy
To eliminate the need for physical residential hardware, we can transition to a Residential Proxy service (e.g., Bright Data, Oxylabs).
*   **Integration**: Playwright supports proxies via the `launch(proxy=...)` parameter.
*   **Cost Management**: Use the built-in `BandwidthTracker` to estimate GB usage before signing up.
*   **Cloud Scaling**: Once a proxy is integrated, Google Maps scraping can be moved to AWS Fargate, enabling infinite scaling without hardware limits.

## Future Orchestration Roadmap
*   **Lightweight K8s (K3s)**: Move away from raw Docker commands to a K3s cluster for better container orchestration and self-healing.
*   **Portainer**: Deploy Portainer for a visual UI to monitor logs and container health across the residential cluster.
*   **Automated Scaling**: Implement a supervisor that scales Fargate workers based on SQS queue depth automatically.
