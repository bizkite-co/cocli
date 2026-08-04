-- Bounds the actual expected export-yield gain from fixing category, rather
-- than assuming all 4,257 rescuable rows (05) convert into export rows.
-- Rescuing category only matters for rows that ALREADY clear the phone+email
-- gates in 03_export_yield_funnel.sql - a rescued category on a row with no
-- phone or no email does not change the export count at all.
-- Run 06 first (needs gm_results_reduced).
WITH joined AS (
    SELECT
        p.place_id,
        p.phone,
        string_agg(DISTINCT e.email, '; ') AS emails,
        p.category,
        p.first_category,
        g.category AS gm_category
    FROM prospects p
    LEFT JOIN emails e ON (
        p.norm_domain = e.norm_domain OR
        p.slug = e.company_slug OR
        p.slug = e.norm_domain OR
        p.norm_domain = e.company_slug
    )
    LEFT JOIN gm_results_reduced g ON p.place_id = g.place_id
    GROUP BY p.place_id, p.phone, p.category, p.first_category, g.category
)
SELECT
    COUNT(*) FILTER (
        WHERE phone IS NOT NULL AND TRIM(phone) != ''
          AND emails IS NOT NULL
          AND COALESCE(category, first_category, '') = ''
          AND gm_category IS NOT NULL AND TRIM(gm_category) != ''
    ) AS rows_actually_rescued_at_the_export_gate
FROM joined;
