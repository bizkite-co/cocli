-- How populated is each field the export litmus test depends on, across the
-- whole prospects checkpoint? Run this first whenever the export yield moves,
-- to see which field's coverage moved with it.
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE phone IS NOT NULL AND TRIM(phone) != '') AS has_phone,
    COUNT(*) FILTER (WHERE domain IS NOT NULL AND TRIM(domain) != '') AS has_domain,
    COUNT(*) FILTER (WHERE category IS NOT NULL AND TRIM(category) != '') AS has_category,
    COUNT(*) FILTER (WHERE first_category IS NOT NULL AND TRIM(first_category) != '') AS has_first_category,
    COUNT(*) FILTER (
        WHERE (category IS NOT NULL AND TRIM(category) != '')
           OR (first_category IS NOT NULL AND TRIM(first_category) != '')
    ) AS has_category_or_first_category
FROM prospects;
