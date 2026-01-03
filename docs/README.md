# Documentation Index

## Architecture
High-level design, patterns, and infrastructure.

*   [Structure](./architecture/structure.md): Application structure overview.
*   [System Architecture Map](./architecture/system-map.md): Nomenclature for execution domains and data flows.
*   [Infrastructure Roadmap](./architecture/infrastructure-roadmap.md): Deployment architecture (AWS CDK) and roadmap.
*   [Worker Infrastructure](./architecture/worker-infrastructure.md): Details on Raspberry Pi cluster, Fargate, and scaling options.
*   [Event Sourcing](./architecture/event-sourcing.md): Notes on event sourcing and logging.
*   [Review View Command](./architecture/review-view-command.md): Architectural review of the view command.

## Data Management
Data structures, storage, ETL pipelines, and S3 integration.

*   [Directory Data Structure](./data-management/DIRECTORY-DATA-STRUCTURE.md): Layout of `cocli_data`.
*   [Campaign Primitive](./data-management/CAMPAIGN.md): Campaign structure and lifecycle.
*   [Data Manager Design](./data-management/_index.md): Core design for the Data Manager component.
*   [ETL Scenarios](./data-management/ETL_SCENARIO.md): Local vs. Cloud ETL architectures.
*   [Index Intermediates](./data-management/INDEX-INTERMEDIATES.md): Philosophy of indexes as transformation outputs.
*   [Queue Design](./data-management/queue-design.md): Producer/Consumer queue architecture.
*   [Enrichment Policy](./data-management/enrichment-policy.md): Rules for source monitoring.
*   [S3 Integration Sequence](./data-management/s3-integration-sequence.md): Sequence diagram for S3 sync.

## Features
Specific feature documentation.

*   [TUI](./features/tui.md): Text User Interface documentation.

## Development
Guides for contributors, testing, and specifications.

*   [Specification](./development/specification.md): Project specification.
*   [Test Plan](./development/test-plan.md): Testing strategy.
*   [Logging](./development/logging.md): Application logging standards.
*   [Logging TUI Events](./development/logging-tui.md): Specifics on logging TUI events.

## Reference
API and command references.

*   [API](./reference/api.md): Internal API reference.
