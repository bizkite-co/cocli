-- Clusters checkpoint rows by the day they were last written (updated_at) and
-- shows category coverage per day. Surfaced that category is populated on
-- almost NO day except one recent one - i.e. this isn't a per-row fallback
-- bug, category was simply never written for the vast majority of the
-- checkpoint's history, across every source/migration event on record.
SELECT
    substr(updated_at, 1, 10) AS write_day,
    COUNT(*) AS n_rows,
    COUNT(*) FILTER (WHERE category IS NOT NULL AND TRIM(category) != '') AS has_category
FROM prospects
GROUP BY write_day
ORDER BY n_rows DESC;
