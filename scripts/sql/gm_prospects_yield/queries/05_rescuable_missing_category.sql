-- Of the checkpoint rows currently missing category/first_category, how many
-- COULD be backfilled just from gm-list result files already on local disk
-- (as opposed to rows whose category was never captured by any known local
-- source, which need a different fix - re-scrape, S3 archive pull, etc).
-- NOTE: run 04_gm_results_duplicate_place_ids.sql first - if that returns
-- rows, this count may be inflated by join fan-out from duplicate place_ids.
SELECT
    COUNT(DISTINCT p.place_id) AS distinct_checkpoint_rows_missing_category,
    COUNT(DISTINCT CASE WHEN g.place_id IS NOT NULL THEN p.place_id END) AS of_those_present_in_gm_results,
    COUNT(DISTINCT CASE
        WHEN g.category IS NOT NULL AND TRIM(g.category) != '' THEN p.place_id
    END) AS of_those_rescuable_with_a_real_category_value
FROM prospects p
LEFT JOIN gm_results g ON p.place_id = g.place_id
WHERE (p.category IS NULL OR TRIM(p.category) = '')
  AND (p.first_category IS NULL OR TRIM(p.first_category) = '');
