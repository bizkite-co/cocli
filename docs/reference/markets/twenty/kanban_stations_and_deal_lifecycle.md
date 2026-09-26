# Conforming Kanban Phases to Stations Architecture: Deal & Initiative Lifecycle

**Date:** September 2026  
**Context:** Specification for implementing visual Kanban pipeline management in `cocli` conforming to the existing `stations` queue processing architecture ([`cocli/core/queue/layout.py`](file:///home/mstouffer/repos/company-cli/cocli/core/queue/layout.py)), contrasted with [Twenty CRM](https://twenty.com)'s relational Opportunity stages.

---

## Executive Summary

Twenty CRM provides a polished, Notion/Linear-style visual Kanban board where sales teams drag and drop deals across stages (e.g., *New*, *Screening*, *Meeting*, *Proposal*, *Won/Lost*). In Twenty, every card is an `Opportunity` entity stored as a mutable row in PostgreSQL, with stage transitions executed via REST/GraphQL mutations.

To bring the speed, visual pipeline clarity, and stage management of Kanban into `cocli` without introducing a database daemon, we conform Kanban pipeline stages directly to **`cocli`'s `stations` queue architecture**.

### The Foundational Sovereign Boundary
> [!IMPORTANT]
> **A Company or Person is NEVER stored inside a station.**
> 
> * **Companies and People are Sovereign Master Entities:** They are long-lived, authoritative plain-text markdown records (`data/companies/<slug>/README.md` and `data/people/<slug>/README.md`) that endure across years, relationships, and initiatives.
> * **Stations Store Discrete Engagements (Deals & Initiative Targets):** Stations represent asynchronous workflows and state machines. What lives in a station phase is a **`DealTask`** or **`InitiativeEngagement`**—a transient or bounded commercial effort associated with a sovereign company. A single company can simultaneously be associated with multiple active initiatives (e.g., an ongoing enterprise sales deal, a testimonial request, and a joint webinar outreach).

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                          SOVEREIGN ENTITY VS. ENGAGEMENT QUEUE                              │
│                                                                                             │
│   Sovereign Entity (Long-Lived Master Data)                                                 │
│   📁 data/companies/acme-corp/README.md                                                     │
│   ├── name: "Acme Corporation"                                                              │
│   ├── domain: "acme.com"                                                                    │
│   └── active_initiatives: ["testimonials-2026", "enterprise-license-q4"]                   │
│                                                                                             │
│                                           │ (Referenced by slug)                            │
│                                           ▼                                                 │
│   Station Queues (Transient Phase State Machines)                                           │
│   ┌──────────────────────────────────────────────────────────────────────────────────────┐  │
│   │ Queue: campaigns/b2b-saas/queues/deals/                                              │  │
│   │                                                                                      │  │
│   │ [ Discovery ] ──> [ Contacted ] ──> [ Meeting ] ──> [ Proposal ] ──> [ Closed Won ]  │  │
│   │        │                                                                             │  │
│   │        └── task.json: { "deal_id": "dl-981", "company_slug": "acme-corp", ... }      │  │
│   └──────────────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Conforming Kanban Stages to `stations.segments`

In `cocli`, stations are defined using declarative segments ([`stations.station.StationDecl`](file:///home/mstouffer/repos/company-cli/cocli/station_defs/campaigns/queues/__init__.py)) that dictate filesystem and S3 path layout without path drift ([`QueueLayout`](file:///home/mstouffer/repos/company-cli/cocli/core/queue/layout.py)).

### A. Stage Declaration (`PhaseRef` & `Phases`)

Instead of hardcoded database enum columns, Kanban stages are declared as first-class station phases:

```python
from stations.segments import phases, shard_by_hash
from stations.station import StationDecl
from cocli.models.campaigns.queues.deal_task import DealTask

# Kanban pipeline columns as station phases
DEAL_PIPELINE_PHASES = phases(
    "discovery",          # Initial prospect qualified from cold scraping
    "outreach_queued",    # Cold sequence generated, awaiting review/dispatch
    "contacted",          # Email sent / phone dialed; awaiting response
    "meeting_scheduled",  # Prospect booked a discovery call or demo
    "proposal_sent",      # Commercial proposal or pricing sent
    "negotiation",        # Redlining, procurement, or contract review
    "closed_won",         # Terminal success: Deal executed
    "closed_lost",        # Terminal exit: Prospect declined, timing wrong, or ghosted
)

DEAL_SHARD = shard_by_hash(2)  # 256 hash shards for high-volume deal directories

DEAL_STATION: StationDecl[DealTask] = StationDecl(
    name="deal-pipeline",
    path_template="campaigns/{campaign}/queues/deals",
    model=DealTask,
    serialization="json-file",
    segments=(DEAL_PIPELINE_PHASES, DEAL_SHARD),
)
```

### B. Shared Filesystem and S3 Layout via `QueueLayout`

Using [`QueueLayout`](file:///home/mstouffer/repos/company-cli/cocli/core/queue/layout.py), a deal card residing in the `meeting_scheduled` stage has an identical relative path both on the local workstation and in S3:

```
campaigns/alpha/queues/deals/
├── discovery/
├── outreach_queued/
├── contacted/
├── meeting_scheduled/
│   └── 3f/
│       └── dl-2026-0926-acme/
│           ├── task.json        # DealTask payload
│           └── lease.json       # Optional operator lease (when being edited)
├── proposal_sent/
├── negotiation/
├── closed_won/
└── closed_lost/
```

- **Local Path:** `~/.local/share/cocli/campaigns/alpha/queues/deals/meeting_scheduled/3f/dl-2026-0926-acme/task.json`
- **S3 Key:** `campaigns/alpha/queues/deals/meeting_scheduled/3f/dl-2026-0926-acme/task.json`

---

## 2. Deal Task Data Model (`DealTask`)

The data payload residing in each station task folder represents the commercial engagement, linking back to the sovereign entities:

```python
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class DealTask(BaseModel):
    """Payload representing a deal or engagement inside a station queue."""

    deal_id: str = Field(description="Unique engagement identifier, e.g. dl-20260926-acme")
    initiative: str = Field(description="Initiative name, e.g. 'q4-expansion' or 'testimonials-2026'")
    
    # Sovereign entity foreign keys (slugs)
    company_slug: str = Field(description="Sovereign company slug in data/companies/<slug>")
    contact_slugs: List[str] = Field(default_factory=list, description="Associated people in data/people/<slug>")

    # Stage & Commercial Attributes
    phase: str = Field(description="Current station phase, e.g. 'meeting_scheduled'")
    title: str = Field(description="Deal title, e.g. 'Acme Enterprise License (50 seats)'")
    amount: Optional[float] = Field(default=None, description="Monetary deal value in USD")
    probability: float = Field(default=0.2, ge=0.0, le=1.0, description="Estimated win probability")
    
    # Ownership & Timestamps
    assigned_to: Optional[str] = Field(default=None, description="Operator user_id (e.g. 'mark')")
    target_close_date: Optional[str] = Field(default=None, description="Expected close date (YYYY-MM-DD)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Context & Notes
    next_action: Optional[str] = Field(default=None, description="Next actionable step")
    next_action_due: Optional[str] = Field(default=None, description="Due date for next action")
    lost_reason: Optional[str] = Field(default=None, description="Reason if moved to closed_lost")
```

---

## 3. Kanban State Transitions & Distributed WAL Journaling

In Twenty, dragging a deal card from *Meeting Scheduled* to *Proposal Sent* performs an HTTP `PATCH /opportunities/{id}` request that immediately updates the PostgreSQL row.

In `cocli`'s distributed environment:
1. **Atomic Local Transition:** The item directory is atomically moved across phase directories using [`QueueLayout.relative_item`](file:///home/mstouffer/repos/company-cli/cocli/core/queue/layout.py#L74).
2. **Immutable WAL Append:** An immutable transition fact is appended to the operator's dedicated Write-Ahead Log.
3. **Sovereign Entity Backlink:** The sovereign company's entity field journal is updated to record the current active deal phase.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                             KANBAN CARD TRANSITION LIFECYCLE                                │
│                                                                                             │
│  1. Operator presses 'L' in TUI Kanban to advance deal                                      │
│     │                                                                                       │
│     ├──> Atomic Directory Rename (Local & S3)                                               │
│     │    queues/deals/meeting_scheduled/3f/dl-acme/  ──>  queues/deals/proposal_sent/3f/dl-acme/
│     │                                                                                       │
│     ├──> Append Transition Fact to Station WAL                                              │
│     │    wal/deals/{date}_{user_id}.usv:                                                    │
│     │    "2026-09-26T15:00:00Z ␟ user:mark ␟ dl-acme ␟ meeting_scheduled ␟ proposal_sent"   │
│     │                                                                                       │
│     └──> Update Sovereign Company Journal (cocli/core/wal.py:append_update)                 │
│          target: "companies/acme-corp" ␟ field: "deal_stage" ␟ value: "proposal_sent"       │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Transition Code Pattern

```python
from datetime import UTC, datetime
from cocli.core.queue.layout import QueueLayout
from cocli.core.wal import append_update
from cocli.station_defs.campaigns.queues import DEAL_STATION


def transition_deal_stage(
    layout: QueueLayout,
    deal: DealTask,
    from_phase: str,
    to_phase: str,
    operator: str,
    reason: Optional[str] = None,
) -> None:
    """Move deal across station phases and log immutable WAL records."""
    old_dir = layout.item_dir(from_phase, deal.deal_id)
    new_dir = layout.item_dir(to_phase, deal.deal_id)
    
    # 1. Update task payload
    deal.phase = to_phase
    deal.updated_at = datetime.now(UTC)
    if reason and to_phase == "closed_lost":
        deal.lost_reason = reason

    # 2. Atomic directory move
    new_dir.parent.mkdir(parents=True, exist_ok=True)
    old_dir.rename(new_dir)
    (new_dir / "task.json").write_text(deal.model_dump_json(indent=2))

    # 3. Append to deal transition WAL
    wal_entry = (
        f"{deal.updated_at.isoformat()}\x1f"
        f"{operator}\x1f"
        f"{deal.deal_id}\x1f"
        f"{deal.company_slug}\x1f"
        f"{from_phase}\x1f"
        f"{to_phase}\x1f"
        f"{deal.amount or 0.0}\x1f"
        f"{reason or ''}\n"
    )
    wal_file = layout.local_root.parent / "wal" / f"deals_{datetime.now(UTC).strftime('%Y%m%d')}_{operator}.usv"
    wal_file.parent.mkdir(parents=True, exist_ok=True)
    with open(wal_file, "a", encoding="utf-8") as f:
        f.write(wal_entry)

    # 4. Touch sovereign company entity journal (Decision 0009)
    append_update(
        target_dir=layout.local_root.parents[2] / "companies" / deal.company_slug,
        field="pipeline_phase",
        value=to_phase,
    )
```

---

## 4. Textual TUI Kanban Board Architecture

In Twenty, the Kanban board is a React 18 component using HTML5 drag-and-drop. In `cocli`, the Kanban interface is rendered directly in the terminal using **Textual**, optimized for lightning-fast keyboard navigation:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ COCLI PIPELINE: Campaign [alpha] | Initiative [q4-expansion]              (q:quit ?:help)   │
├───────────────────┬───────────────────┬───────────────────┬───────────────────┬─────────────┤
│ CONTACTED (14)    │ MEETING SCHED (5) │ PROPOSAL SENT (3) │ NEGOTIATION (2)   │ WON (8)     │
├───────────────────┼───────────────────┼───────────────────┼───────────────────┼─────────────┤
│ * Acme Corp       │ * WidgetCo Inc    │ * Global Logistics│ * Apex FinTech    │ * Beta Corp │
│   $12,000 | 4d ago│   $45,000 | Demo  │   $85,000 | v2 SOW│   $120,000 | Redln│   $30,000   │
│   Next: Followup  │   Next: Call 2pm  │   Next: Exec Rev  │   Next: Legal Sgn │             │
│                   │                   │                   │                   │             │
│ * Initech LLC     │ * Stark Dynamics  │ * Cyberdyne Sys   │ * Pied Piper      │             │
│   $8,500 | 1d ago │   $60,000 | Prep  │   $50,000 | Sent  │   $95,000 | CFO   │             │
│                   │                   │                   │                   │             │
│ * Hooli Inc       │                   │                   │                   │             │
│   $25,000 | Today │                   │                   │                   │             │
└───────────────────┴───────────────────┴───────────────────┴───────────────────┴─────────────┘
  [h/l]: Switch Column  [j/k]: Navigate Cards  [H/L]: Move Stage  [Enter]: View Company  [c]: Call
```

### Keybindings & Interaction Model

| Keybinding | Action | Description |
| :--- | :--- | :--- |
| `h` / `l` | Focus Column | Navigate focus horizontally between pipeline phases. |
| `j` / `k` | Select Deal | Move card selection vertically within the active column. |
| `H` / `L` | Shift Stage | Instantly move selected deal to adjacent stage (Left = previous, Right = next). |
| `m` | Move Menu | Open fuzzy-search modal to move card to any non-adjacent stage (e.g. `closed_lost`). |
| `Enter` | Open Master Entity | Navigate directly to `cocli`'s company detail view for the underlying prospect. |
| `c` | Dial Bridge | Initiate a Twilio voice bridge call to the primary contact associated with the deal. |
| `v` | Preview Draft | Open pandoc-rendered terminal HTML preview of active email drafts for this prospect. |
| `a` | Adjust Amount | Quick edit modal to update deal value or expected close date. |

---

## 5. Pipeline Analytics & Funnel Velocity with DuckDB

Because every state transition is recorded in append-only WAL files with exact UTC timestamps, `cocli` leverages **DuckDB** to calculate deep pipeline analytics directly from local storage with zero server overhead:

```python
import duckdb

def analyze_pipeline_velocity(campaign_path: str) -> duckdb.DuckDBPyRelation:
    """Analyze stage duration and dropoff rates directly from transition WALs."""
    con = duckdb.connect()
    
    # Read all daily deal WAL files using DuckDB's USV/CSV scanner
    query = f"""
    WITH transitions AS (
        SELECT 
            column0::TIMESTAMP as transitioned_at,
            column1 as operator,
            column2 as deal_id,
            column3 as company_slug,
            column4 as from_phase,
            column5 as to_phase,
            column6::DOUBLE as amount
        FROM read_csv(
            '{campaign_path}/wal/deals_*.usv',
            delim='\x1f',
            header=False
        )
    ),
    stage_durations AS (
        SELECT 
            deal_id,
            from_phase,
            to_phase,
            transitioned_at,
            LAG(transitioned_at) OVER (PARTITION BY deal_id ORDER BY transitioned_at) as entered_at,
            date_diff('day', entered_at, transitioned_at) as days_in_stage
        FROM transitions
    )
    SELECT 
        from_phase as stage,
        COUNT(deal_id) as total_transitions,
        AVG(days_in_stage) as avg_days_in_stage,
        MEDIAN(days_in_stage) as median_days_in_stage
    FROM stage_durations
    WHERE days_in_stage IS NOT NULL
    GROUP BY from_phase
    ORDER BY avg_days_in_stage DESC;
    """
    return con.sql(query)
```

### Analytical Capabilities Enabled by WAL + DuckDB

1. **Cycle Velocity:** Quantify exactly how many days deals spend in *Meeting Scheduled* before moving to *Proposal Sent*.
2. **Bottleneck Identification:** Instantly see if a particular operator has deals stagnating in *Proposal Sent* longer than the team average.
3. **True Historical Win Rates:** Calculate conversion percentages per stage over time without risking historical data mutation (unlike PostgreSQL, where stage updates overwrite the previous stage value).
4. **Weighted Pipeline Forecasts:** Group open station items by `target_close_date` and compute `SUM(amount * probability)`.

---

## 6. Comparison: Twenty vs. `cocli` Stations Pipeline

| Architectural Dimension | Twenty CRM (`Opportunity`) | `cocli` Stations (`DealTask`) |
| :--- | :--- | :--- |
| **Data Storage** | PostgreSQL table row | Plain-text JSON file in partitioned directory |
| **Phase Definition** | Relational enum column | Declarative station segment (`PhaseRef`) |
| **Stage Transition** | HTTP `PATCH` -> SQL `UPDATE` | Atomic directory move + append-only WAL |
| **Historical Audit** | `TimelineActivity` table rows | Immutable append-only USV transition log |
| **Company Relationship** | Foreign key (`companyId`) | Sovereign slug reference (`company_slug`) |
| **Offline Execution** | ❌ Fails without database connection | ✅ Full read/write/move capabilities offline |
| **Analytical Querying** | SQL over PostgreSQL connection | In-process vectorized DuckDB over local WAL |
| **Interface** | React 18 Web UI (Mouse drag-and-drop) | Textual TUI (Vim keyboard navigation) |

---

## Summary Roadmap for `cocli`

To implement this architecture in `cocli`:
1. **Model Definition:** Add [`cocli/models/campaigns/queues/deal_task.py`](file:///home/mstouffer/repos/company-cli/cocli/models/campaigns/queues/) implementing `DealTask`.
2. **Station Definition:** Register `DEAL_STATION` in [`cocli/station_defs/campaigns/queues/__init__.py`](file:///home/mstouffer/repos/company-cli/cocli/station_defs/campaigns/queues/__init__.py) with `DEAL_PIPELINE_PHASES`.
3. **TUI Widget:** Create `cocli/tui/widgets/kanban_view.py` with multi-column layout, vim navigation (`h/j/k/l/H/L`), and atomic transition execution.
4. **Analytics Command:** Implement `cocli pipeline velocity` using DuckDB over `wal/deals_*.usv`.

---

## Related Documents

* [Twenty CRM Feature Comparison & Interoperability Architecture](feature_compare_and_interoperability.md)
* [Distributed Architecture & Multi-User Synchronization: `cocli` vs. Twenty](distributed_architecture_and_aws_auth.md)
* [Queue Layout Architecture (`cocli/core/queue/layout.py`)](file:///home/mstouffer/repos/company-cli/cocli/core/queue/layout.py)
* [Campaign Station Definitions (`cocli/station_defs/campaigns/queues/__init__.py`)](file:///home/mstouffer/repos/company-cli/cocli/station_defs/campaigns/queues/__init__.py)
* [Entity Field Journal WAL Protocol (`cocli/core/wal.py`)](file:///home/mstouffer/repos/company-cli/cocli/core/wal.py)
