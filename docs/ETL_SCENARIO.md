
# ETL Scenario: Acquiring and Enriching Prospects

## 1. Background & Strategy

The primary goal of this workflow is to systematically add new, targeted prospects to the CRM and enrich them with high-quality data, specifically email addresses. The process is designed as a multi-stage pipeline that is idempotent (re-runnable) and transparent.

The overall strategy is broken into three phases:

1.  **Prospecting:** Scrape raw business data (name, address, website, etc.) from Google Maps based on a set of search queries and locations defined in a campaign configuration file.

2.  **Ingestion & Import:** Process the raw scraped data, deduplicate it against the existing cache of known businesses, and create the formal, structured company data directories within the `cocli_data/companies/` directory.

3.  **Enrichment:** Scrape the websites of the newly imported companies to find additional details that are not available on Google Maps, such as contact page URLs and, most importantly, email addresses for the company and its key personnel.

This entire workflow can be repeated as needed. The system will automatically handle deduplication, so you can re-run the process to find new prospects without creating duplicates of companies already in the system.

## 2. Step-by-Step Workflow

Here are the precise steps to execute the workflow, from initial scraping to final verification.

### Preparation: Configure Your Campaign

Before starting, ensure your campaign configuration file is set up for the current goal. For this scenario, we are targeting Albuquerque.

**File:** `campaigns/2025/turboship/config.toml`

```toml
[campaign]
name = "turboship"
tag = "turboship"

[google_maps]
email = "admin@turboheatweldingtools.com"
one_password_path = "op://TurboHeatWelding/GMail_TurboHeatWeldingTools/password"

[prospecting]
locations = [
  "Albuquerque, NM"
    ]
queries = ["commercial vinyl flooring contractor", "rubber flooring contractor", "sports flooring contractor"]
```

### Step 1: Scrape New Prospects from Google Maps

This command reads your campaign config, searches Google Maps for each query/location pair, and saves the raw results. We use `--max-results` to control how many companies to aim for per query.

**Command:**
```bash
source .venv/bin/activate && cocli campaign scrape-prospects --max-results 100
```

### Step 2: Process and Import Scraped Companies

This command takes the raw CSV from Step 1, ingests it into the system's cache, and then creates the company directory structures in the CRM. We use `--skip-scrape` because we just completed that part.

**Command:**
```bash
source .venv/bin/activate && cocli google-maps process --skip-scrape
```

### Step 3: Enrich Websites for Emails

Now that the new companies exist in the CRM, this command will visit each company's website and look for email addresses. It automatically skips any company that has already been enriched, so it is safe to run multiple times.

**Command:**
```bash
source .venv/bin/activate && cocli enrich-websites
```

### Step 4: Verify Results and Generate Output

Finally, use the `query` command we built to check the results. This command will find all prospects in the Albuquerque area that now have one or more email addresses and save the list to a CSV file.

**Command:**
```bash
source .venv/bin/activate && cocli query prospects --city "Albuquerque" --state "NM" --radius 30 --has-email
```
This will produce the final CSV of prospects with emails and output the path and count to the console.

To get more emails, simply repeat this entire four-step process.
