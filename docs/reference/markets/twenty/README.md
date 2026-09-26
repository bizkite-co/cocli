# Twenty CRM Reference & Market Analysis

This directory contains market analysis, architectural comparisons, and interoperability specifications for integrating `cocli` with the [Twenty](https://twenty.com) open-source CRM.

## Documents

* [Feature Comparison & Interoperability Architecture](feature_compare_and_interoperability.md): Comprehensive breakdown of feature overlap, data interchange methods (REST, DuckDB, PostgreSQL, MCP), plugin integration, and the build-vs-interoperate strategic evaluation.
* [Distributed Architecture & Multi-User Synchronization: `cocli` vs. Twenty](distributed_architecture_and_aws_auth.md): Architectural analysis of multi-user operations without a centralized PostgreSQL server, starting from AWS IAM/SSO and STS role delegation, S3 path partitioning, append-only WAL reconciliation, and commercial feature offerings capitalizing on the "No-Postgres" advantage (zero-ops, air-gapped field operations, residential edge scrapers, DuckDB in-process analytics).
* [Conforming Kanban Phases to Stations Architecture: Deal & Initiative Lifecycle](kanban_stations_and_deal_lifecycle.md): Specification for visual pipeline management adhering to `cocli`'s `stations` queue layout (`QueueLayout`). Details the sovereign entity invariant (companies/people are never stored in stations), the `DealTask` model, atomic stage transitions with WAL logging, and Textual TUI Kanban design.
