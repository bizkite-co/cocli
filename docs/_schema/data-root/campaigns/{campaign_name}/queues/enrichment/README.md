# Enrichment Queue

The enrichment queue manages tasks for scraping company websites to extract emails, social links, and other metadata.

## Structure
`queues/enrichment/pending/{shard}/{task_id}/`
*   `task.json`: Contains the `domain`, `company_slug`, and `campaign_name`.
*   `lease.json`: Atomic lease file to prevent duplicate processing.

## Sharding
Tasks are sharded using an MD5 hash of the `{company_slug}_{domain}` to distribute load and avoid filesystem limits.
`shard = md5(id)[0]`
