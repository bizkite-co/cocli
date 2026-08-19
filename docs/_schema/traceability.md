# Identity Traceability Matrix

This document defines the backbone for tracing a single `Place_ID` from discovery to enrichment. It provides the "Confidence Backbone" required to audit the distributed system.

## 1. The Identity Lifecycle

Every prospect follows a strictly defined lifecycle. Confidence is achieved by verifying the "Hand-off" between these stages.

| Stage | Trigger | Output Artifact | Verification Metric |
| :--- | :--- | :--- | :--- |
| **Discovery** | Tile + Phrase | `queues/gm-list/completed/{shard}/{lat}_{lon}_{phrase}.csv` | Contains the `Place_ID`. |
| **Detailing** | `Place_ID` | `indexes/google_maps_prospects/{shard}/{place_id}.usv` | Validated against `GoogleMapsProspect` model (Name/Slug > 3 chars). |
| **Witness** | Detailing Success | `queues/gm-details/completed/{place_id}.json` | Exists and matches the Prospect Index. |
| **Enrichment** | Domain from Prospect | `indexes/emails/{domain}/{user}.json` | Cross-referenced via the company `hash`. |

---

## 2. The Traceability Map (Proposal)

To achieve absolute confidence, we maintain a virtual "Traceability Map" (Materialized during audit).

### A. The Geographic Root (The "Where")
Each search is anchored to a tile.
- **Key**: `{lat}_{lon}` (1-decimal precision)
- **Status**:
  - `EXPECTED`: Tiles defined in `target-tiles.usv`.
  - `DISCOVERED`: Tiles with a completion marker in `gm-list/completed`.

### B. The ID Chain (The "What")
For every `Place_ID` found in a tile:
1. **Discovery Record**: Did it appear in the discovery CSV?
2. **Identity Integrity**: Does the `.usv` file exist? Does it pass Pydantic validation?
3. **Queue Consensus**: Does the `completed/` marker match the Index? (Prevents "Ghost" records).
4. **Enrichment Yield**: How many valid emails are linked to this ID?

---

## 3. Auditing & Recovery Logic

Confidence is maintained by a "Self-Healing" audit loop:

### Identity Gaps
- **Symptom**: `Place_ID` exists in Discovery CSV but NO Prospect Index entry.
- **Recovery**: Re-enqueue `gm-details` task for that `Place_ID`.

### Integrity Gaps (Hollow Records)
- **Symptom**: Prospect Index entry exists but fails Pydantic validation (e.g., Name="").
- **Recovery**: Move to `recovery/hollow/`, delete completion marker, re-enqueue.

### Consensus Gaps (Zombie Records)
- **Symptom**: Completion marker exists but Prospect Index entry is missing.
- **Recovery**: Delete "Liar" completion marker to allow re-scraping.

---

## 4. Implementation: `cocli audit campaign`

**Implemented 2026-08-18** (task-agent ticket
`implement-cocli-audit-campaign-per-place-id-pipeline-traceability-and-leak-detection`).
Built on `cocli/core/prospect_trace.py`'s station-check mechanism (originally
written for the narrower `cocli index trace` targeted-debug command) plus a
new enrichment-stage check and aggregate gap-category tally.

```
cocli audit campaign --campaign <name> [--limit N] [--out path.csv]
```

Auto-discovers every `Place_ID` the campaign has ever touched (union of
gm-list's current discovery results and the prospect checkpoint's own
identities - gm-list's `completed/results/` tree does not retain every
record forever, so gm-list alone under-covers real state), traces each one
across gm-list -> gm-details -> Pi WAL -> checkpoint -> enrichment, and
reports an aggregate count per gap category, plus a full per-`Place_ID` CSV.

Confirmed live against turboship 2026-08-18: 17,080 identities traced,
15,413 (90.2%) clean, **1,667 with a real Identity Gap** - records present
in the checkpoint with a resolved domain that were never enqueued into the
enrichment queue at all (1,600 of the 1,667 are current-format `Place_ID`s,
not legacy-schema artifacts). This is read-only - it reports the gap, it
does not (yet) auto-recover it; see the Recovery section above for the
target self-healing behavior, not yet wired up.

Differs from the JSON-report shape originally sketched here: ships as a
Rich table + CSV export (matching this codebase's other `cocli audit *`
commands) rather than a per-`Place_ID` JSON document, and reports named gap
categories in aggregate rather than a `status`/`history` object per ID -
the full per-ID detail (state at every station) is in the CSV, one row per
`Place_ID`, which serves the same "prove exactly where it went cold"
purpose.
