# High-Fidelity Scraping & Data Management

This directory documents the architecture and operational practices for our high-fidelity scraping system. Our approach prioritizes "Absolute Fidelity" to bypass modern anti-bot detections (like Google Maps' "Limited View") while maintaining a deterministic, auditable, and refreshable data pipeline.

## Core Principles

1.  **Absolute Fidelity**: We simulate human behavior and load all browser assets (images, fonts, media) to create a believable browser fingerprint.
2.  **Deterministic Prospecting**: All scraping missions are driven by a "Mission Index" (e.g., geographic target tiles) rather than random discovery.
3.  **Auditable State Machine**: Every scrape follows a strict multi-stage simulation with formalized transitions and metadata capture.
4.  **Local-First Indexing**: We use a `ScrapeIndex` (Witness Files) to track the "Frontier" and manage staleness/refreshing without re-scraping successful hits.
5.  **Multi-Stage QC**: Quality control is integrated into the production pipeline through automated audits and threshold alerts.

## Documentation Index

- [**Scraping Strategy**](./strategy.md): Details on the multi-stage simulation, Human Flow navigation, and Session-Heal hydration.
- [**Data Pipeline & Staleness**](./pipeline.md): How we manage Mission Indices, Target Tiles, and the Scrape Index.
- [**Quality Control & Testing**](./quality-control.md): Our methodology for testing parsers, browser alignment, and production data audits.
- [**Anti-Bot Detection (Historical)**](../../issues/completed/2026/anti-bot-detection.md): The root cause analysis of the "Limited View" trap.

## Key Components

- **State Machine**: Defined in `cocli/scrapers/gm_details_scraper.py`.
- **Mission Index**: Managed in `cocli/commands/campaign/prospecting.py`.
- **Scrape Index**: Implemented in `cocli/core/scrape_index.py`.
- **Audits**: Located in `scripts/audit_*.py`.
