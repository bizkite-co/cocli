# Current Task: Stabilize Local ETL and Design/Implement Intelligent Data Manager with S3 Integration

This task focuses on ensuring the local ETL workflow (Google Maps scraping + local website enrichment) is fully stable, and in parallel, addressing the complexity of data storage and synchronization for cloud deployment by designing and implementing an intelligent data manager with S3 integration.

## Objective

To ensure local ETL stability, and to develop and implement a robust strategy for managing data across local and cloud storage (S3), leveraging existing data management principles. This includes enabling S3 synchronization from the local environment to prepare for EC2 deployment.

## Plan of Attack

1.  **Verify local Google Maps scrape is fully stable:**
    *   Run the `achieve-goal` command multiple times with varying `goal_emails` and locations to ensure consistent and error-free operation.
    *   Confirm that prospects are correctly imported and enriched locally.
2.  **Review Data Management Documentation:** (Already completed in previous turns)
    *   `docs/adr/from-model-to-model.md`
    *   `docs/INDEX-INTERMEDIATES.md`
    *   `docs/DIRECTORY-DATA-STRUCTURE.md`
    *   Understand the existing principles for data transformation, indexing, and directory structures.
3.  **Propose Design for Intelligent Data Manager:** Based on the review of existing documentation and the requirements for cloud deployment (EC2 with S3), sketch out a design for a data manager that can:
    *   **Abstract Storage:** Provide a unified interface for accessing data regardless of whether it's on the local filesystem or S3.
    *   **Handle Data Types:** Coordinate different data types (Pydantic models, CSVs, Markdown files).
    *   **Intelligent Synchronization:** Define mechanisms for syncing data between local and S3 stores, especially for directory-like structures and index files. This should address partial updates, concurrency, and consistency.
    *   **Index Management:** Offer a clear way to list and query all indexes, or indexes associated with a campaign.
    *   **Data Flow Diagram:** Illustrate how data flows into indexes and the directory store, and how indexes are used for data lookup.
4.  **Create `docs/data-manager-design.md`:** Document the proposed design, including architectural considerations, API interfaces, and data flow diagrams.
5.  **Implement `S3DomainManager` locally:** Develop the `S3DomainManager` that interacts with S3 for domain indexing and status, using S3 object tags. This will leverage the `aws_profile_name` added to the `Campaign` model.
6.  **Integrate `S3DomainManager` into Website Enrichment:** Modify the local website enrichment service to use the `S3DomainManager` instead of the local CSV manager for domain status and indexing.
7.  **Develop Local S3 Sync Mechanism:** Create a mechanism (e.g., a `cocli` command or a `make` target) to synchronize local `cocli_data/` with S3, specifically for the verbose company content and other non-index files.

## Future Considerations (for subsequent tasks)

*   **Revisit Website Enrichment to AWS Fargate (Next Major Step):** Deploy the website enrichment service to Fargate, integrating it with the new intelligent data manager.
*   **Website Enrichment Trigger:** Determine how the Fargate service will be triggered (e.g., SQS queue, Step Functions).
*   **Error Handling and Monitoring:** Implement robust error handling, logging, and monitoring for the Fargate service.
