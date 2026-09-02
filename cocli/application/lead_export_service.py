"""Lead export orchestration: prospects checkpoint + email index join, the
same query as the client dashboard's "download CSV" button.

Domain/orchestration layer (product-specific). No Rich/console presentation
or S3 upload here - callers handle progress display and delivery; this
module owns query correctness and writing the two output artifacts.

Extracted from scripts/export_enriched_emails.py (2026-08-23) after a
verification query hand-rolled elsewhere in the same investigation session
undercounted real results by ~18% (2,031 vs the real 2,462) by omitting the
found_keywords join this module gets right. One tested source of truth for
this query, not a second copy anyone might diverge from - see
docs/data-management/data-quality-incidents/README.md for why that matters.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel

from cocli.core.config import get_campaign_exports_dir, get_companies_dir
from cocli.core.exclusions import ExclusionManager
from cocli.utils.google_maps_url import google_maps_url
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.models.companies.website import Website
from cocli.models.wal.record import US

logger = logging.getLogger(__name__)

FIELDNAMES = [
    "company", "domain", "emails", "phone", "website", "city", "state",
    "categories", "services", "products", "tags", "gmb_url", "rating", "reviews",
]


class LeadExportResult(BaseModel):
    """Result of export_enriched_emails."""

    campaign_name: str
    exported_count: int = 0
    skipped_count: int = 0
    output_usv: Optional[Path] = None
    output_csv: Optional[Path] = None


def _get_website_data(company_slug: str) -> Optional[Website]:
    """Loads a company's website.md enrichment for its found_keywords."""
    website_md_path = get_companies_dir() / company_slug / "enrichments" / "website.md"
    if not website_md_path.exists():
        return None

    try:
        content = website_md_path.read_text()
        from cocli.core.text_utils import parse_frontmatter

        frontmatter_str = parse_frontmatter(content)
        if not frontmatter_str:
            return None
        data = yaml.safe_load(frontmatter_str)
        if not data:
            return None

        # Hotfix for legacy/malformed personnel data
        if "personnel" in data and isinstance(data["personnel"], list):
            sanitized_personnel = []
            for p in data["personnel"]:
                if isinstance(p, str):
                    sanitized_personnel.append({"raw_entry": p})
                elif isinstance(p, dict):
                    sanitized_personnel.append(p)
            data["personnel"] = sanitized_personnel

        return Website.model_validate(data)
    except Exception:
        return None


def export_enriched_emails(
    campaign_name: str,
    *,
    keywords: bool = False,
    include_all: bool = False,
    progress_callback: Optional[Any] = None,
) -> LeadExportResult:
    """Joins the prospects checkpoint against the email index and writes the
    client-facing enriched-emails USV + CSV.

    Client report criteria (default, unless include_all): a contactable
    lead needs phone, at least one resolved email, and a category-or-keyword
    signal for outreach personalization. ``keywords=True`` further requires
    the company's own website-enrichment found_keywords, not just a
    checkpoint category.

    ``progress_callback``, if given, is called once per candidate row
    during the keyword-lookup pass (``callback(index, total)``) - purely
    for a caller-side progress bar, never required.
    """
    import duckdb

    from cocli.core.email_index_manager import EmailIndexManager
    from cocli.core.prospects_csv_manager import ProspectsIndexManager

    exclusion_manager = ExclusionManager(campaign_name)
    export_dir = get_campaign_exports_dir(campaign_name)
    output_file = export_dir / f"enriched_emails_{campaign_name}.csv"

    checkpoint_path = ProspectsIndexManager(campaign_name).checkpoint_path
    if not checkpoint_path.exists():
        raise FileNotFoundError(
            f"Prospects checkpoint not found for {campaign_name}: {checkpoint_path}"
        )

    con = duckdb.connect(database=":memory:")

    # Schema-derived, not hand-maintained - avoids the exact dual-authority
    # drift this module's own docstring warns about.
    columns = GoogleMapsProspect.duckdb_read_csv_columns()
    con.execute(f"""
        CREATE TABLE prospects AS SELECT * FROM read_csv('{checkpoint_path}',
            delim='\x1f',
            header=False,
            columns={columns!r},
            auto_detect=False,
            ignore_errors=True,
            quote=''
        )
    """)

    email_manager = EmailIndexManager(campaign_name)
    email_shard_glob = str(email_manager.shards_dir / "*.usv")
    if list(email_manager.shards_dir.glob("*.usv")):
        con.execute(f"""
            CREATE TABLE emails AS SELECT * FROM read_csv('{email_shard_glob}',
                delim='\x1f',
                header=False,
                columns={{
                    'email': 'VARCHAR',
                    'domain': 'VARCHAR',
                    'company_slug': 'VARCHAR',
                    'source': 'VARCHAR',
                    'found_at': 'VARCHAR',
                    'first_seen': 'VARCHAR',
                    'last_seen': 'VARCHAR',
                    'verification_status': 'VARCHAR',
                    'tags': 'VARCHAR'
                }},
                quote=''
            )
        """)
    else:
        con.execute(
            "CREATE TABLE emails (email VARCHAR, domain VARCHAR, company_slug VARCHAR, "
            "tags VARCHAR, last_seen VARCHAR)"
        )

    # Scraper artifacts occasionally land image filenames in the email
    # column - filter on plausible email shape and reject image extensions.
    con.execute(r"""
        DELETE FROM emails
        WHERE NOT regexp_matches(email, '^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$')
           OR regexp_matches(lower(email), '\.(png|jpe?g|gif|webp|bmp|svg|ico|tiff?)$')
    """)

    # Email domains are frequently stored as full URLs while prospect
    # domains are bare hostnames - normalize both sides before joining.
    con.execute("ALTER TABLE emails ADD COLUMN norm_domain VARCHAR")
    con.execute(
        r"UPDATE emails SET norm_domain = regexp_replace(regexp_replace(lower(domain), "
        r"'^https?://(www\.)?', ''), '/$', '')"
    )
    con.execute("ALTER TABLE prospects ADD COLUMN norm_domain VARCHAR")
    con.execute(
        r"UPDATE prospects SET norm_domain = regexp_replace(regexp_replace(lower(domain), "
        r"'^https?://(www\.)?', ''), '/$', '')"
    )

    query = """
        SELECT
            p.name,
            COALESCE(p.domain, p.slug) as domain,
            string_agg(DISTINCT e.email, '; ') as emails,
            p.phone as phone,
            p.city,
            p.state,
            p.keyword as tag,
            p.category as category,
            p.first_category as first_category,
            p.place_id,
            p.slug,
            p.average_rating,
            p.reviews_count
        FROM prospects p
        LEFT JOIN emails e ON (
            p.norm_domain = e.norm_domain OR
            p.slug = e.company_slug OR
            p.slug = e.norm_domain OR
            p.norm_domain = e.company_slug
        )
        GROUP BY p.name, p.domain, p.slug, p.phone, p.city, p.state, p.keyword,
                 p.category, p.first_category, p.place_id, p.average_rating, p.reviews_count
    """
    having_clauses = ["phone IS NOT NULL", "TRIM(phone) != ''"]
    if not include_all:
        having_clauses.append("emails IS NOT NULL")
    query += " HAVING " + " AND ".join(having_clauses)

    rows = con.execute(query).fetchall()

    results: list[dict[str, Any]] = []
    skipped_count = 0

    for i, row in enumerate(rows):
        if progress_callback is not None:
            progress_callback(i, len(rows))
        (
            name, domain, emails, phone, city, state, keyword, category,
            first_category, place_id, slug, rating, reviews,
        ) = row

        if exclusion_manager.is_excluded(domain=domain, slug=slug):
            continue

        website_data = _get_website_data(slug) if slug else None
        found_keywords = website_data.found_keywords if website_data else []

        report_category = category or first_category or ""
        has_category_or_keywords = bool(report_category) or bool(found_keywords)

        if keywords and not found_keywords:
            continue
        if not has_category_or_keywords:
            skipped_count += 1
            continue

        results.append({
            "company": name,
            "domain": domain,
            "emails": emails or "",
            "phone": phone,
            "website": domain,
            "city": city,
            "state": state,
            "categories": report_category,
            "services": "",
            "products": "",
            "tags": "; ".join(filter(None, [keyword] + found_keywords)),
            "gmb_url": google_maps_url(
                place_id=place_id,
                name=name,
                city=city,
            )
            or "",
            "rating": rating,
            "reviews": reviews,
        })

    output_file_usv = output_file.with_suffix(".usv")
    with open(output_file_usv, "w", newline="", encoding="utf-8") as f:
        f.write(US.join(FIELDNAMES) + "\n")
        for res in results:
            f.write(US.join(str(res[name]) for name in FIELDNAMES) + "\n")

    output_file_csv = output_file.with_suffix(".csv")
    with open(output_file_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for res in results:
            writer.writerow(res)

    return LeadExportResult(
        campaign_name=campaign_name,
        exported_count=len(results),
        skipped_count=skipped_count,
        output_usv=output_file_usv,
        output_csv=output_file_csv,
    )
