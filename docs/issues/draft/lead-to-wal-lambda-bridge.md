# Task: Implement Lead-to-WAL Lambda bridge for Astro site

## Objective
Create a serverless bridge to capture email and name from a static Astro landing page and store it securely in S3 using the standardized WAL datagram pattern.

## Requirements
- **Lambda Function**: A Python-based AWS Lambda function that accepts a JSON POST request.
- **Validation**: Ensure name and email are present and formatted correctly.
- **Data Persistence**: Write a single `.datagram` file per submission to a specific S3 bucket/path (e.g., `s3://cocli-leads/fullertonian/wal/`).
- **Security**: Implement basic origin-based CORS and API key validation.
- **Integration**: Must be compatible with the existing `cocli sync` tools for bulk ingestion into the main CRM index.

## Rationale
Standardizing on the WAL (Write-Ahead-Log) datagram pattern allows us to avoid the complexity and cost of a database while maintaining high speed and reliability for our hyper-local newsletter campaigns.
