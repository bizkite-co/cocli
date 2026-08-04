-- Mirrors scripts/export_enriched_emails.py's exact filter chain (join,
-- HAVING phone/email, then the category-or-keyword gate) as a funnel, so we
-- can see which stage the yield actually collapses at without re-deriving
-- the query from scratch each time. Does NOT replicate the per-company
-- website.md found_keywords rescue (that part still needs Python) - treat
-- the last row as a lower bound, not the exact final export count.
WITH joined AS (
    SELECT
        p.place_id,
        p.phone,
        string_agg(DISTINCT e.email, '; ') AS emails,
        p.category,
        p.first_category
    FROM prospects p
    LEFT JOIN emails e ON (
        p.norm_domain = e.norm_domain OR
        p.slug = e.company_slug OR
        p.slug = e.norm_domain OR
        p.norm_domain = e.company_slug
    )
    GROUP BY p.place_id, p.phone, p.category, p.first_category
)
SELECT
    COUNT(*) AS after_join,
    COUNT(*) FILTER (WHERE phone IS NOT NULL AND TRIM(phone) != '') AS after_phone_filter,
    COUNT(*) FILTER (WHERE phone IS NOT NULL AND TRIM(phone) != '' AND emails IS NOT NULL) AS after_phone_and_email_filter,
    COUNT(*) FILTER (
        WHERE phone IS NOT NULL AND TRIM(phone) != '' AND emails IS NOT NULL
          AND (COALESCE(category, first_category, '') != '')
    ) AS after_category_gate_lower_bound
FROM joined;
