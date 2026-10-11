# ADR-014: Org, branch, and person relationships

**Status:** Accepted (2026-10-11)

**Task:** `adr-orgbranchperson-relationship-taxonomy-and-provenance-model`

## Context

Company-to-person links are undated symlinks at `companies/<slug>/contacts/<person_slug>`. A branch such as Higginbotham – Austin has no representation. `Company.email_provider` and `Company.tech_stack` already store present-state labels that overlap with provenance-bearing observations such as "uses Mimecast, source dig MX".

Stations owns queues, WALs, indexes, and claim/lease. Cocli consumes that library. Companies and people stay sovereign records (`docs/reference/markets/twenty/kanban_stations_and_deal_lifecycle.md`): a station phase holds a deal or other engagement that references slugs. It does not hold the company or the person.

Vocabulary below was checked against the published specs, not recalled:

- schema.org [`parentOrganization`](https://schema.org/parentOrganization) ("the larger organization that this organization is a subOrganization of"; supersedes `branchOf`), inverse [`subOrganization`](https://schema.org/subOrganization), narrower [`department`](https://schema.org/Organization), and Person [`worksFor`](https://schema.org/Organization).
- W3C ORG ([`vocab-org`](https://www.w3.org/TR/vocab-org/)): `FormalOrganization` versus `OrganizationalUnit` (a unit recognized only inside its parent, not a legal entity); `subOrganizationOf` / `hasUnit`; `hasSite` with range `Site`; `Membership` as the interval-bearing link from an agent to an organization.

## Decision

### 1. A branch with its own identity is its own company

Higginbotham the legal entity is a sovereign company classified `formalOrganization`. Higginbotham – Austin, when it has its own people, phone, or place, is another sovereign company classified `organizationalUnit`. The log stores one direction: the child's `parentOrganization` is the parent. Compaction writes the inverse into the parent's folder.

`department` is the same shape, used only for a true department (schema.org's store-with-a-pharmacy case; ORG's `hasUnit`).

An address with no staff and no identity is a `hasSite` fact on the parent. It does not become a company.

Classification lives on the company record. It is not a third storage system and it is not a station phase.

### 2. One fact record, three fold policies

A relationship or observation is an append-only log record on a cocli station, `RELATIONSHIP_JOURNAL`, using stations `LogEdge` and `last_write_wins_fold`. The stations library does not gain an organization concept.

The record is a whole typed row. Fields, in USV order, separated by `\x1f`, one record per `\n` line (no `\x1e`):

`relationship_id`, `timestamp`, `node_id`, `campaign_name`, `subject_type`, `subject`, `predicate`, `object_type`, `object_key`, `started_at`, `ended_at`, `is_primary`, `source`, `method`, `observed_at`.

`subject_type` and `object_type` are `company`, `person`, `literal`, or `blob`. `source` is who asserted it (`manual`, `dig MX`, `People Data Labs`). `method` is how (`osint`, `mx`, `import`). `observed_at` is when the world was seen. `timestamp` is when this node wrote the row and is the fold version stamp.

Identity is `relationship_id`, not the triple:

- A correction or a close reuses the id. The later `timestamp` wins. Setting `ended_at` closes that instance.
- A second stint (Mitch leaves Higginbotham and returns) is a new id. Both survive.

Predicates in the closed vocabulary:

| Predicate | Who | Fold | Meaning |
| :--- | :--- | :--- | :--- |
| `parentOrganization` | company → company | per `relationship_id` | Child's parent. Inverse materialized as `subOrganization`. |
| `department` | company → company | per `relationship_id` | Narrower unit-of link. |
| `hasSite` | company → literal | per `relationship_id` | A place that is not its own company. |
| `worksFor` | person → company | per `relationship_id` | Employment. `is_primary` marks the current main job. |
| `membership` | person → company | per `relationship_id` | Board, vendor, or other non-employee role. Role text rides in `method` until a role column is justified. |
| `usesEmailService` | company → literal | per `(subject, predicate)` | One current provider. Later row replaces the earlier provider. |
| `usesTechnology` | company → literal | per `(subject, predicate, object_key)` | One current row per product. Two products both remain. |

A new predicate is a vocabulary entry in `cocli/application/`. The record and the log edge do not change.

The journal is a **retained** WAL. Compaction publishes present state. It does not delete segments. History stays in the log.

### 3. Existing company fields stay until readers move

`Company.email_provider` and `Company.tech_stack` remain the structured present-state fields current readers use. Observation facts may cite the same world. They do not replace those fields in this ADR. A later reader cutover may fold `usesEmailService` into `email_provider` and `usesTechnology` into `tech_stack`. Until that cutover, writers of those fields keep writing the fields.

### 4. Layers

| Piece | Home |
| :--- | :--- |
| `LogEdge`, Shape A segments, `last_write_wins_fold`, inspect | `stations`, unchanged |
| `RelationshipRecord`, `RELATIONSHIP_JOURNAL`, append/iterate, the three pure folds | `cocli/models/wal/`, `cocli/station_defs/wal/`, `cocli/core/` |
| Predicate list, which fold a predicate uses, org-chart wording, campaign-relevance | `cocli/application/` |
| CLI | `cocli/commands/`, when a command exists |

`core` does not import `application`. Path template: `wal/relationships/{period}_{writer}.usv`.

### 5. Sovereign entities, and what a person can read

Companies stay under `companies/<slug>/`. People stay under `people/<slug>/`. Deals stay in queue stations and store slugs. The relationship journal stores facts about those records, the same way the entity field journal stores field updates.

The USV segment is the audit log. The explanation a person reads is regenerated next to the company:

```text
companies/higginbotham/
  README.md
  org.md
  units/higginbotham-austin    # symlink to the child company
  contacts/mitch-gaylord       # symlink from open worksFor / membership
```

`org.md` lists parent, child units, open memberships, and open sites. Each line carries since, until, role, source, and observed_at. Yazi on the company folder is the org chart. `stations inspect` reports journal health. It is not the org browser.

Campaign tags stay on the company. A person's campaign relevance is computed from open `worksFor` or `membership` edges. It is not copied onto the person.

Raw provider payloads (a future People Data Labs body) are Shape B files, one file per blob, named by content hash. Journal rows with `object_type=blob` cite that id. The payload is not columns on the company.

### 6. First implementation slice

The journal code is the record, the station declaration, the log edge, the three folds, and the predicate registry. `publish_relationship_journal` writes `org.md` and regenerates `units/` and `contacts/` symlinks from open instance edges. It does not delete journal segments, derive campaign tags, or ingest provider blobs.

## Consequences

- Branch offices that have people become company records plus a `parentOrganization` fact. Empty addresses stay `hasSite` facts.
- Job history survives because each stint has its own id.
- `email_provider` and `tech_stack` keep their current readers.
- The relationship log is retained. Compaction must not copy the entity-field journal's "archive the segment after folding" behavior.
- Follow-ons: publish `org.md` and regenerate symlinks; derive person campaign tags from today's `contacts/` symlinks; provider blobs; reader cutover for the two company fields.
