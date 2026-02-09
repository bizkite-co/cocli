# Target Tiles Index

This index stores the results of geographic search operations (Discovery). Each file represents a specific search phrase executed at a specific tenth-degree coordinate grid.

## Path Structure
`target-tiles/{lat_shard}/{lat_tenth_degree}/{lon_tenth_degree}/{search_slug}.csv`

- `{lat_shard}`: The first digit (and sign) of the latitude (e.g., `3` for `33.2`, `-1` for `-12.5`).
- `{lat_tenth_degree}`: Latitude rounded to one decimal place.
- `{lon_tenth_degree}`: Longitude rounded to one decimal place.
- `{search_slug}`: Slugified search phrase (e.g., `financial-advisor`).

## Content
The files are headerless CSVs containing basic Google Maps metadata (Place ID, Name, Business Status) as returned from the list-item scrape. These are used to seed the hydration queues.
