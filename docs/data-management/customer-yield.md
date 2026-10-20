# Customer yield

The customer number is the row count of the enriched-emails CSV (quoted
fields can contain newlines, so `wc -l` is not the count). The command
prints `Exported N companies`. That same count is what
`csv.DictReader` returns.

Workers do not write that file. Enrichment writes emails only on the
worker's own disk, and Google Maps scrapers write prospect WAL only on
the worker. The CSV is produced on the dev machine by joining the
prospects checkpoint to the local email index, then uploaded for the
dashboard.

## One command

```bash
uv run cocli web export-emails --campaign turboship
```

That command is the full sequence below, then the upload. Needs AWS
credentials for the campaign profile (1Password, for `bizkite-support`).
It stops before upload if the email pull or the prospect compaction
fails. On success it writes:

- `~/.local/share/cocli_data/campaigns/<campaign>/exports/enriched_emails_<campaign>.csv`
- the matching `.usv`
- `s3://cocli-web-assets-<domain-slug>/exports/<campaign>-emails.csv`
- the matching `.usv`

`Cache-Control: no-cache, must-revalidate` is set on the CSV. The
dashboard fetches it with a cache-busting query string.

## Command sequence

Run these in order when you want each step visible. `web export-emails`
runs the same steps and then uploads, so you do not also run that
command after this list.

```bash
uv run cocli sync pi-results --campaign turboship --force
uv run cocli index sync-pi-emails --campaign turboship
uv run cocli data compact-emails --campaign turboship
uv run cocli index compact --campaign turboship --index google_maps_prospects
uv run cocli data export-enriched-emails --campaign turboship
```

Then publish. The upload is the last action of:

```bash
uv run cocli web export-emails --campaign turboship
```

which repeats the five commands above before it uploads. Use it when
you want one invocation. Use the five commands when you want to stop
and read the count before publishing.

What each step is for:

1. `sync pi-results` — gm-list, gm-details, and enrichment queue files
   from each node. The prospect compact merges gm-list results into the
   checkpoint from this local copy. Phone and category often arrive here.
2. `index sync-pi-emails` — each worker's `indexes/emails/` merged into
   the local email index (`rsync -au`, no `--delete`). Enrichment writes
   those files only on the worker. Nothing else copies them.
3. `data compact-emails` — inbox folded into shards. The export reads
   both, so this step is hygiene. The join still works if it is skipped,
   and the next export is slower.
4. `index compact` — pulls each worker's prospect WAL over Tailscale and
   folds it into `prospects.usv`. A node whose WAL sync fails aborts the
   compact. Google Maps detail scrapers write that WAL. Enrichment does
   not. `index sync-pi-wal` only copies the same WAL up to S3. The
   compact does not read that S3 copy. A failed S3 copy does not drop
   the rows.
5. `data export-enriched-emails` — joins the checkpoint to the email
   index. A row needs a phone, a plausible email, and a category or a
   website keyword. Exclusions are dropped. Prints `Exported N companies`.

`cocli web deploy` runs this same data refresh, then also rebuilds the
static shell, republishes reports and KML, and invalidates CloudFront.
Use `export-emails` when the shell has not changed.

Skipping step 2 or step 4 and then exporting counts the previous
checkpoint. That is what the first count in the 2026-10-19 session did.

## What the 2026-10-19 compile found

The first export that day read `prospects.usv` as it stood after the
12 September compaction: 20,907 place IDs, 4,308 customer rows. The
workers had kept writing after that.

The sequence above then did three things:

- Folded 25,705 prospect WAL files from cocli5x0 and NUC01. The
  checkpoint went to 23,924 place IDs. That is 3,017 companies that
  were already scraped and had never been compacted. None were dropped.
  Those files are gm-details output. There were no October prospect WAL
  files. Enrichment did not create them.
- Merged 23,693 gm-list results into the checkpoint. That filled phone
  and category on companies already in the September checkpoint, so
  more of them passed the export rules.
- Joined the worker email indexes (22,883 email records after
  compaction). A company with a phone and a category stays out of the
  CSV until it has an email. Those emails are the enrichment product.

The raw CSV went from 4,308 rows to 7,642. The gain is larger than the
3,017 new place IDs because the gm-list fill and the newly pulled emails
also qualified companies that were already in the checkpoint.

## While enrichment is still running

Both turboship machines are on enrichment only. They are not adding
Google Maps places. Each new email can add a customer row for a
prospect that already has a phone and a category and is not excluded.
A prospect that is already in the CSV does not become a second row.

The website number does not move while the workers run. It moves when
`web export-emails` is run again, and, for the dashboard count, when
the refined list is rebuilt and `web upload-lead-filter` is run. The
refined list will rise by less than the raw list, because the category
rules still drop hardware stores, woodworking supply stores, and the
other exclusions in `exports/filter-criteria.md`.

## What the client dashboard counts

https://cocli.turboheat.net/ (campaign `turboship`) shows the refined
list when `exports/turboship-leadfilter-summary.md` is on the site. The
prospect count and the cards are the row count of
`exports/turboship-leadfilter-in.csv`, not the raw emails CSV. The raw
file is the download only when that summary is absent.

The refined list is a separate classification (off-topic categories,
carpet/tile specialists, luxury vinyl tile without sheet-vinyl or sports
flooring). The rule is recorded in the campaign data directory at
`exports/filter-criteria.md`. Regenerating it re-reads `witness.html` on
the workers. That scan is not part of `web export-emails`.

After a new raw export, publish a refreshed refined list with:

```bash
# On each worker, against that node's own raw/enrichment tree.
# The scanner lives in the campaign data directory, not in git.
# One TSV row per witness.html:
# domain_folder, verdict, has_lvt, has_vinyl_sheet, has_sports_flooring
SCAN=~/.local/share/cocli_data/campaigns/turboship/exports/scan_witness_keywords.py
ssh mstouffer@<node> python3 - /home/mstouffer/repos/data/campaigns/turboship/raw/enrichment \
  < "$SCAN" > /tmp/<node>_scan.tsv

# Join those TSVs to the new enriched_emails CSV with
# exports/apply_filter_v2.py in that same data directory.
# It writes enriched_emails_<campaign>_filter_IN.csv and _OUT.csv.

uv run cocli web upload-lead-filter --campaign turboship
```

`upload-lead-filter` publishes the In CSV, the Out CSV, and
`lead-filter-summary.md`. It does not rebuild them, and it does not
upload `filter-criteria.md`.

The 2026-10-19 run of this sequence published 7,642 raw rows and a
refined list of 6,548 in / 1,094 out. The dashboard count is the refined
list. `Woodworking supply store` is a hard exclusion, same as
`Hardware store`.
