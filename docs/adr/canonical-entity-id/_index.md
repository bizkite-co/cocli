# Architectural Decision Record: Canonical Entity Identification (Companies and People)

## 1. Context and Problem Statement

The "Hierarchical Entity Data with Symlinks" ADR proposes storing canonical entity data (companies and people) in unique directories under `~/.local/share/cocli_data/.entities/`. The naming strategy for these canonical directories is critical to ensure data integrity, prevent accidental duplication, and handle real-world complexities such as entities with similar names, multiple branches/roles, or name changes.

The challenge is to define a robust and flexible identification strategy that:
*   Provides a stable, unique identifier for each entity (company or person).
*   Minimizes the risk of accidental duplication.
*   Allows for clear identification and management of related entities (e.g., branches of the same company, people with similar names).
*   Accommodates changes over time (e.g., entity name changes, a person changing companies).
*   Remains human-readable where possible, without sacrificing uniqueness.

## 2. Potential Identification Strategies

### A. UUID (Universally Unique Identifier)

*   **Description:** Use a standard UUID (e.g., UUIDv4) as the directory name for each entity.
*   **Pros:** Guaranteed uniqueness, simple to generate.
*   **Cons:**
    *   **Human Readability:** UUIDs are not human-readable, making it difficult to quickly identify an entity by looking at the directory name.
    *   **Accidental Duplication Detection:** If a user accidentally adds the same entity twice (e.g., with slightly different names), it would result in two distinct UUIDs, making it hard to detect and merge the duplicates.
    *   **No Semantic Meaning:** Provides no inherent information about the entity.

### B. Slug-based Identifier

*   **Description:** Generate a "slug" from the entity's primary name (e.g., "My Company, Inc." -> "my-company-inc"; "John Doe" -> "john-doe").
*   **Pros:** Human-readable, somewhat descriptive.
*   **Cons:**
    *   **Uniqueness Issues:** Not guaranteed to be unique. "Acme Corp" in New York and "Acme Corp" in London would generate the same slug. "John Smith" and another "John Smith" would also collide.
    *   **Name Changes:** If an entity changes its name (e.g., a company rebrands, a person changes their legal name), the slug would change, requiring a directory rename and updating all symlinks, which is complex.
    *   **Collision Handling:** Requires a strategy for handling slug collisions (e.g., appending a number: "acme-corp-1", "acme-corp-2"; "john-doe-1", "john-doe-2").

### C. Hybrid Identifier (Slug + Short Hash/Contextual Suffix)

*   **Description:** Combine a slug with a short, unique suffix (e.g., a truncated hash of additional identifying information like address/email, or a user-defined disambiguator).
*   **Pros:** Improved human readability (from the slug), enhanced uniqueness (from the suffix).
*   **Cons:**
    *   **Complexity:** More complex generation logic.
    *   **Suffix Management:** Requires careful consideration of what information to include in the hash/suffix and how to manage it.

### D. User-Defined Identifier (with validation)

*   **Description:** Allow the user to specify a unique identifier when adding an entity, with the system validating its uniqueness.
*   **Pros:** Full user control, potentially highly descriptive.
*   **Cons:**
    *   **User Burden:** Places the responsibility of ensuring uniqueness on the user.
    *   **Error Prone:** Users might choose non-unique or inconsistent identifiers.

## 3. Scenarios to Address

### A. Entities with Identical or Very Similar Names (Companies and People)

*   **Problem:** "Acme Corp" (New York) vs. "Acme Corp" (London). "John Smith" (Software Engineer) vs. "John Smith" (Photographer).
*   **Solution Consideration:** A hybrid approach (Slug + Location/Context/Email Hash) or a system-generated unique ID with a user-editable display name.

### B. Entity Name Changes (Companies and People)

*   **Problem:** "Old Name Co." changes to "New Name Corp." A person changes their legal name.
*   **Solution Consideration:** If the canonical ID is name-derived, it would require renaming the canonical directory and updating all symlinks. If the canonical ID is stable (e.g., UUID or a stable hash), only the internal entity data (e.g., `_index.md` file) would need updating, and symlinks would remain valid.

### C. Companies with Multiple Branches/Locations

*   **Problem:** "Starbucks - Downtown" vs. "Starbucks - Airport". Are these separate entities or branches of the same canonical company?
*   **Solution Consideration:**
    *   **Separate Canonical Entities:** Treat each branch as a distinct company with its own canonical ID. This simplifies data storage but might complicate aggregate reporting for the parent company.
    *   **Single Canonical Entity with Branch Data:** Store all branch data within a single canonical company directory, perhaps in subdirectories or within the `_index.md` file. This requires more complex data modeling within the company's data structure.
    *   **Parent-Child Relationship via Symlinks:** A "parent" company canonical ID, with "branch" canonical IDs symlinked under a "branches" category.

### D. People with Multiple Roles/Associations

*   **Problem:** A person works for multiple companies, or has multiple roles (e.g., "John Doe - CEO of Company A" and "John Doe - Advisor for Company B").
*   **Solution Consideration:** The canonical person entity remains unique. Associations with companies are managed through symlinks from company folders to the canonical person entity, as described in the "Hierarchical Entity Data with Symlinks" ADR.

## 4. Recommended Approach (Initial Draft)

Given the need for both uniqueness and some level of human readability, a **Hybrid Identifier** seems most promising for both companies and people.

*   **Canonical ID Format:** `[slug_of_entity_name]-[short_hash_of_disambiguating_info]`
    *   `slug_of_entity_name`: Derived from the primary entity name (company name or person's full name).
    *   `short_hash_of_disambiguating_info`: A short, deterministic hash generated from additional identifying attributes (e.g., primary address/email, website URL, or a user-provided unique key). This hash ensures uniqueness even if slugs collide.

*   **Handling Name Changes:** The `short_hash` component should be stable. If an entity name changes, the `slug_of_entity_name` part of the canonical ID might change, requiring a directory rename. However, if the `short_hash` is truly stable (e.g., based on a persistent internal ID or a hash of immutable attributes), it could be used to track the entity. Alternatively, the canonical ID could be a stable, non-changing ID (like a UUID) and the slug part could be a metadata field.

*   **Handling Duplication:** The system should attempt to detect potential duplicates during entity creation by comparing slugs and/or other identifying information. If a potential duplicate is found, the user should be prompted to confirm if it's a new entity or an existing one.

*   **Handling Branches/Roles:** Initially, treat each distinct company branch or person's primary role as a separate canonical entity if their identifying information is sufficiently different. If a need for aggregate reporting or explicit parent-child relationships arises, a separate mechanism for linking related canonical entities can be developed (e.g., a `parent_id` field in the entity's `_index.md`).

## 5. Performance Implications of Flat `.entities/` Directory

A flat `.entities/` directory, while simple to implement, could face performance issues as the number of entities grows into the tens of thousands or hundreds of thousands. File system operations (listing, searching, creating) can become slow.

**Potential Solutions for Scaling `.entities/`:**

*   **Sharding by First Character/Two Characters:** Similar to how Git stores objects, create subdirectories based on the first (or first two) characters of the canonical ID.
    *   **Example:** `~/.entities/a/company-a-id/`, `~/.entities/ab/company-ab-id/`
    *   **Pros:** Distributes entities across many subdirectories, reducing the number of items in any single directory.
    *   **Cons:** Adds a layer of complexity to path construction and resolution. Requires careful consideration of how to handle non-alphanumeric starting characters if the ID can start with those.

*   **Hashing for Distribution:** Use a hash function on the canonical ID to determine a subdirectory path.
    *   **Example:** `~/.entities/hash_prefix/company-id/`
    *   **Pros:** Even distribution of entities, less prone to "hot spots" than alphabetical sharding if IDs are not evenly distributed alphabetically.
    *   **Cons:** Less human-readable directory structure.

*   **Database Indexing (Future Consideration):** For very large datasets, offloading entity metadata and indexing to a lightweight database (e.g., SQLite) could provide faster lookups, with the file system still storing the actual content. This is a more significant architectural change.

**Recommendation for Initial Implementation:** Start with a flat `.entities/` directory. Implement the sharding mechanism (e.g., by first two characters) as a follow-up task when performance becomes a measurable concern. This allows for iterative development and avoids premature optimization.

## 6. Future Considerations

*   **Data Migration:** A plan for migrating existing flat-file company and person data to the new canonical structure.
*   **CLI Commands for ID Management:** Commands to rename canonical IDs, merge duplicate entities, or manage branch/role relationships.
*   **Integration with External IDs:** How to incorporate external identifiers (e.g., from CRM systems, public databases) into the canonical ID strategy.
*   **Performance Monitoring:** Tools and metrics to monitor file system performance as the number of entities grows, to inform when sharding or other optimizations are necessary.