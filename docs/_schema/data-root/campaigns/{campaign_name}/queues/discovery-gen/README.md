# Discovery Generation Queue (`discovery-gen`)

This is the "Head of the Funnel." It transforms campaign configuration into actionable geographic targets. It acts as the **Mission Master Index**, defining the total search perimeter for all map-based discovery sources (Google Maps, Yelp, etc.).

## Core Transformations

| Operation | Input | Transformation | Output |
| :--- | :--- | :--- | :--- |
| **Prepare** | `config.toml` | Grid Generation + ScrapeIndex Diff | `mission.usv` + `pending/frontier.usv` |
| **Batch** | `pending/frontier.usv` | Subset Selection (Limit/Random) | `pending/batches/{name}.usv` |
| **Activate** | `pending/batches/*.usv` | "Explode" into Sharded Files | `completed/{shard}/{lat}/{lon}/{phrase}.usv` |

## Transformation Functions
- **Prepare**: `cocli.commands.campaign.prospecting.prepare_mission`
- **Batch**: `cocli.commands.campaign.prospecting.create_batch`
- **Activate**: `cocli.commands.campaign.prospecting.build_mission_index`

## Models & Serialization
- **Model**: `cocli.models.campaigns.mission.MissionTask`
- **Serialization**: Unit-Separated Value (USV) using `\x1f`.
- **Fields**: `tile_id`, `search_phrase`, `latitude`, `longitude`.

## Relationship with Worker Queues
Files in `completed/` represent **Intent**. 
- To activate work for Google Maps, the `cocli campaign queue-mission` command transforms the `.usv` files here into the directory-based `task.json` structure required by `gm-list/pending/`. 
- **Direct copy-paste is not supported** due to this structural difference.
