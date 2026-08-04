-- The actual fix for 04's duplicate place_ids: this is a field-level MERGE,
-- not identity resolution - place_id is already the correct unique key, the
-- problem is that N separate discovery events (same place found via
-- overlapping geo-tiles / different keyword searches) each captured a
-- different subset of fields. MAX() ignores NULLs, so for each field it
-- keeps any non-null value that exists across the duplicates instead of
-- whatever `discovery_tile_id`-sorted row happened to win.
--
-- NOT safe to use MAX() for a field that is legitimately multi-valued per
-- place (checked: nothing currently reads discovery_tile_id/discovery_phrase
-- off the checkpoint for tile-completion tracking, so collapsing them to one
-- representative value is acceptable today - revisit if that changes).
--
-- This must run BEFORE gm_results is joined against the checkpoint in
-- gm_list_to_checkpoint.py - that join currently happens against the raw,
-- un-reduced table.
CREATE OR REPLACE TABLE gm_results_reduced AS
SELECT
    place_id,
    max(company_slug) AS company_slug,
    max(name) AS name,
    max(category) AS category,
    max(phone) AS phone,
    max(domain) AS domain,
    max(reviews_count) AS reviews_count,
    max(average_rating) AS average_rating,
    max(street_address) AS street_address,
    max(gmb_url) AS gmb_url,
    max(discovery_phrase) AS discovery_phrase,
    max(discovery_tile_id) AS discovery_tile_id,
    max(html) AS html
FROM gm_results
GROUP BY place_id;

SELECT
    (SELECT COUNT(*) FROM gm_results) AS raw_rows,
    (SELECT COUNT(*) FROM gm_results_reduced) AS reduced_rows,
    (SELECT COUNT(*) FROM gm_results WHERE category IS NOT NULL AND TRIM(category) != '') AS raw_rows_with_category,
    (SELECT COUNT(*) FROM gm_results_reduced WHERE category IS NOT NULL AND TRIM(category) != '') AS reduced_rows_with_category;
