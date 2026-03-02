# Discovery-Gen Active Pool (Completed)

Despite the directory name `completed/`, in the context of `discovery-gen`, this represents the **Active Task Pool**. 

## Why "Completed"?
In the `discovery-gen` queue's own lifecycle, these tasks are "complete" once they have been exploded from a batch and sharded onto the disk. For the **Downstream Workers** (like `gm-list`), this directory serves as their input source.

## Structure
Files are sharded using the **Geo-Tile** strategy to ensure high performance during `cocli smart-sync`:
`{lat_shard}/{lat_tenth_degree}/{lon_tenth_degree}/{search_slug}.usv`

- **`lat_shard`**: First character of latitude (e.g., `2` for `25.0`).
- **`lat_tenth_degree`**: Latitude rounded to 0.1 (e.g., `25.0`).
- **`lon_tenth_degree`**: Longitude rounded to 0.1 (e.g., `-79.9`).

## Content
Each `.usv` file contains exactly one line representing the task. This line is identical to the entry in the master `mission.usv`.

## Lifecycle
1. **Activation**: `build-mission-index` writes the file here.
2. **Polling**: `FilesystemGmListQueue` finds the file during a scan.
3. **Execution**: Worker creates a lease in `gm-list/pending/`.
4. **Conclusion**: Results are saved to `gm-list/completed/results/`. The file in `discovery-gen/completed/` REMAINS as a permanent record of the intent.
