# Canonical Entity ID

This document defines the deterministic generation of unique identifiers for businesses in the `cocli` ecosystem.

## The Identity Tripod
To ensure cross-campaign uniqueness and reliable join operations, every entity is identified by a "Tripod" of components:
1.  **Name**: The formal business name.
2.  **Street Address**: The primary physical location.
3.  **ZIP Code**: The 5-digit postal code.

## The Company Hash
The `company_hash` is a human-readable, deterministic string derived from the Identity Tripod. It is used as the primary key for deduplication and dashboard linking.

### Algorithm
- **Formula**: `slug(name)[:8]-slug(street)[:8]-zip[:5]`
- **Implementation**: `cocli.core.text_utils.calculate_company_hash`

### Examples
| Name | Street | ZIP | Resulting Hash |
| :--- | :--- | :--- | :--- |
| Advanced Financial | 123 Main St | 75094 | `advanced-123-main-75094` |
| Advanced Flooring | 456 Oak Ave | 75094 | `advanced-456-oak--75094` |

## Address Extraction
Because Google Maps often returns unstructured address strings, `cocli` employs a conservative extraction layer (`parse_address_components`) to salvage structured components during ingestion.

This layer ensures that even if raw data is messy, we can still generate a robust hash by identifying the street and ZIP within the string.

## Sharding
Entities are sharded based on their **Place ID** (the Google Maps anchor). 
- **Function**: `cocli.core.utils.get_place_id_shard`
- **Logic**: Uses the last character of the Place ID (e.g., `ChIJ...abc` -> shard `c`).
- **Purpose**: Prevents filesystem saturation and enables parallel processing across the Pi cluster.
