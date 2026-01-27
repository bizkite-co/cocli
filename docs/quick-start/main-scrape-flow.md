# Main Scrape Flow

This guide outlines the standard procedure for initiating and managing a large-scale Google Maps scraping mission using `cocli`.

## 1. Prepare Campaign Configuration
Ensure your `campaign/config.toml` has the correct search queries and target locations.

- **Check queries:** Verify `[prospecting] queries = [...]`
- **Check locations:** Verify `[prospecting] target-locations = [...]`
- **Set Proximity:** Ensure `proximity-miles = 50` (or your desired radius) is set.

## 2. Generate Mission Grid
Create a deterministic master list of all tiles to be searched. This command geocodes locations and calculates the coordinate grid.

```bash
cocli campaign prepare-mission <campaign-name>
```
* **What it does:** Creates `mission.json` and `indexes/pending_scrape_total.csv`. It identifies which tiles have never been scraped for the given queries.

## 3. Build Mission Index
Explode the master mission list into a filesystem-based index for distributed processing.

```bash
cocli campaign build-mission-index <campaign-name>
```
* **What it does:** Creates thousands of small `.csv` files in `indexes/target-tiles/`. Each file represents a unique "Tile + Query" combination.

## 4. Enqueue Tasks to S3
Push the local mission index to the cloud so that remote workers (Raspberry Pis) can see the tasks.

```bash
aws s3 sync data/campaigns/<campaign-name>/indexes/target-tiles/ \
    s3://<bucket-name>/campaigns/<campaign-name>/indexes/target-tiles/ \
    --profile <aws-profile>
```
* **What it does:** Uploads the "To-Do" list to the shared campaign bucket. Workers poll this S3 directory to find their next task.

## 5. Scale Workers
Direct the cluster workers to focus on the scraping role.

- **Edit `config.toml`:** Adjust the `[prospecting.scaling.<hostname>]` section.
    - Set `gm-list = 4` (number of concurrent scrape threads).
    - Set `enrichment = 2` (if you want to process websites in parallel).
- **Sync Config to S3:**
```bash
aws s3 cp data/campaigns/<campaign-name>/config.toml s3://<bucket-name>/config.toml --profile <aws-profile>
```
* **What it does:** The `cocli-supervisor` on each worker reloads this config every 60 seconds and automatically starts/stops worker threads to match your targets.

## 6. Monitor Progress
Verify that workers are active and tasks are being completed.

- **Check Heartbeats:**
```bash
aws s3 cp s3://<bucket-name>/status/<hostname>.json - --profile <aws-profile>
```
- **Run Cluster Health Script:**
```bash
python3 scripts/check_cluster_health.py
```
* **What it does:** Displays active worker counts, CPU/Memory usage, and current task IDs for every machine in the cluster.
