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

The proposed audit command will generate a **Traceability Report**:

```json
{
  "place_id": "ChIJ-v...",
  "status": "VALID",
  "history": [
    {"stage": "discovery", "tile": "33.4_-83.9", "phrase": "wealth-manager", "ts": "2026-02-06"},
    {"stage": "detailing", "node": "cocli5x0", "ts": "2026-02-06"},
    {"stage": "enrichment", "emails": 2}
  ]
}
```

This structure ensures that we never "lose" an ID and can prove exactly where a regression occurred.
