#!/usr/bin/env python3
"""Ingest active Roadmap RTA users into companies, contacts, and high-priority to-call queue items."""

from __future__ import annotations

import argparse
import csv
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from cocli.core.paths import paths
from cocli.core.config import set_campaign
from cocli.core.text_utils import slugify
from cocli.models.companies.company import Company
from cocli.models.people.person import Person
from cocli.models.campaigns.queues.to_call import ToCallTask

logger = logging.getLogger("ingest_testimonials_to_call")

INTERNAL_USERNAMES: set[str] = {
    "appdev",
    "joel",
    "josh_almieri",
    "angela_gerber",
    "aaron_scharf",
    "chip_slaughter",  # Provided model testimonial
}

INTERNAL_EMAILS: set[str] = {
    "mark@bizkite.net",
    "joel@roadmappartners.net",
    "josh@paradigmgoc.com",
    "angela@prsplan.com",
    "ascharf@higginbotham.net",
    "cslaughter@lpl.com",
}

# Known advisor profiles enriched with firm, phone, address, and domain
PRODUCER_PROFILES: dict[str, dict[str, Any]] = {
    "657": {  # Jan Mohamed
        "firm_name": "Higginbotham Financial",
        "company_name": "Higginbotham - Jan Mohamed",
        "slug": "higginbotham-jan-mohamed",
        "phone": "2142158004",
        "phone_formatted": "(214) 215-8004",
        "street_address": "8080 North Central Expressway, Suite 1435",
        "city": "Dallas",
        "state": "TX",
        "zip_code": "75206",
        "domain": "higginbotham.net",
    },
    "529": {  # Kevin Klaas
        "firm_name": "Monarch Solutions",
        "company_name": "Monarch Solutions - Kevin Klaas",
        "slug": "monarch-solutions-kevin-klaas",
        "phone": "8158476229",
        "phone_formatted": "(815) 847-6229",
        "street_address": "6870 Rote Road, STE 103",
        "city": "Rockford",
        "state": "IL",
        "zip_code": "61107",
        "domain": "monarchsolutionsinc.com",
    },
    "1180": {  # Cooper Gerami
        "firm_name": "Higginbotham",
        "company_name": "Higginbotham - Cooper Gerami",
        "slug": "higginbotham-cooper-gerami",
        "phone": "3377810147",
        "phone_formatted": "337-781-0147",
        "domain": "higginbotham.com",
    },
    "1174": {  # Don Blauner
        "firm_name": "Blauner Financial",
        "company_name": "Blauner Financial - Don Blauner",
        "slug": "blauner-financial-don-blauner",
        "phone": "3107392718",
        "phone_formatted": "(310) 739-2718",
        "street_address": "11600 Washington Place # 212",
        "city": "Los Angeles",
        "state": "CA",
        "zip_code": "90066",
        "domain": "blaunerfinancial.com",
    },
    "1181": {  # Mitch Gaylord
        "firm_name": "Higginbotham",
        "company_name": "Higginbotham - Mitch Gaylord",
        "slug": "higginbotham-mitch-gaylord",
        "phone": "9494907817",
        "phone_formatted": "949-490-7817",
        "domain": "higginbotham.com",
    },
    "1160": {  # William Cassidy
        "firm_name": "Cassidy & Company, LLC, A Higginbotham Partner",
        "company_name": "Cassidy & Company - William Cassidy",
        "slug": "cassidy-and-company-william-cassidy",
        "phone": "8135453789",
        "phone_formatted": "(813) 545-3789",
        "street_address": "614 W. Bay St.",
        "city": "Tampa",
        "state": "FL",
        "zip_code": "33606",
        "domain": "cassidy-co.com",
    },
    "1089": {  # Tzvi Kupfer
        "firm_name": "Tamar Fink",
        "company_name": "Tamar Fink - Tzvi Kupfer",
        "slug": "tamar-fink-tzvi-kupfer",
        "phone": "6126380143",
        "phone_formatted": "(612) 638-0143",
        "street_address": "1200 Ford Rd",
        "city": "Minnetonka",
        "state": "MN",
        "zip_code": "55305",
        "domain": "tamarfink.com",
    },
    "621": {  # Kevin Grant
        "firm_name": "Higginbotham",
        "company_name": "Higginbotham - Kevin Grant",
        "slug": "higginbotham-kevin-grant",
        "domain": "higginbotham.net",
    },
    "1159": {  # Matt Woodard
        "firm_name": "Higginbotham Financial",
        "company_name": "Higginbotham Financial - Matt Woodard",
        "slug": "higginbotham-financial-matt-woodard",
        "phone": "7277762353",
        "phone_formatted": "(727) 776-2353",
        "street_address": "3939 Tampa Road",
        "city": "Oldsmar",
        "state": "FL",
        "zip_code": "34677",
        "domain": "higginbotham.com",
    },
    "1164": {  # Taryn Martinez
        "firm_name": "Paradigm Gilbert",
        "company_name": "Paradigm Gilbert - Taryn Martinez",
        "slug": "paradigm-gilbert-taryn-martinez",
        "phone": "9514373729",
        "phone_formatted": "(951) 437-3729",
        "domain": "paradigmgilbert.com",
    },
    "526": {  # Hunter Ewing
        "firm_name": "Highground Company",
        "company_name": "Highground Company - Hunter Ewing",
        "slug": "highground-company-hunter-ewing",
        "phone": "4044782400",
        "phone_formatted": "404-478-2400",
        "domain": "highgroundcompany.com",
    },
    "1177": {  # Josh Bornstein
        "firm_name": "Higginbotham",
        "company_name": "Higginbotham - Josh Bornstein",
        "slug": "higginbotham-josh-bornstein",
        "phone": "8184295815",
        "phone_formatted": "818-429-5815",
        "domain": "higginbotham.com",
    },
    "1184": {  # Austin Somers
        "firm_name": "Higginbotham",
        "company_name": "Higginbotham - Austin Somers",
        "slug": "higginbotham-austin-somers",
        "domain": "higginbotham.net",
    },
    "507": {  # Dave Halvorson
        "firm_name": "Calibrate Wealth Partners, LLC",
        "company_name": "Calibrate Wealth Partners - Dave Halvorson",
        "slug": "calibrate-wealth-partners-dave-halvorson",
        "phone": "7012320643",
        "phone_formatted": "(701) 232-0643",
        "street_address": "3320 Westrac Dr. S, Suite D.",
        "city": "Fargo",
        "state": "ND",
        "zip_code": "58103",
        "domain": "calibratewp.com",
    },
    "1182": {  # Jake Dukart
        "firm_name": "Higginbotham",
        "company_name": "Higginbotham - Jake Dukart",
        "slug": "higginbotham-jake-dukart",
        "domain": "higginbotham.net",
    },
    "1151": {  # Tim Engelbert
        "firm_name": "Higginbotham",
        "company_name": "Higginbotham - Tim Engelbert",
        "slug": "higginbotham-tim-engelbert",
        "zip_code": "76102",
        "domain": "higginbotham.net",
    },
}


def setup_script_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


def is_target_user(row: dict[str, str]) -> bool:
    """Filter out internal staff, empty emails, and completed testimonials."""
    uname = row.get("username", "").strip().lower()
    email = row.get("email", "").strip().lower()

    if not email:
        return False
    if uname in INTERNAL_USERNAMES:
        return False
    if email in INTERNAL_EMAILS:
        return False
    return True


def resolve_profile(row: dict[str, str]) -> dict[str, Any]:
    """Resolve producer profile metadata with fallbacks."""
    user_id = row.get("user_id", "").strip()
    if user_id in PRODUCER_PROFILES:
        return PRODUCER_PROFILES[user_id]

    # Fallback resolution based on email and name
    fname = row.get("first_name", "").strip()
    lname = row.get("last_name", "").strip()
    email = row.get("email", "").strip()
    domain = email.split("@")[-1] if "@" in email else "unknown.com"
    company_name = f"{domain} - {fname} {lname}"
    slug = slugify(f"{domain}-{fname}-{lname}")

    return {
        "firm_name": domain,
        "company_name": company_name,
        "slug": slug,
        "domain": domain,
    }


def ingest_testimonials(
    csv_path: Path,
    campaign: str = "roadmap",
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Ingest target producers from ranked user activity CSV into cocli."""
    set_campaign(campaign)

    if not csv_path.exists():
        raise FileNotFoundError(f"Testimonial activity CSV not found at: {csv_path}")

    logger.info(f"Reading ranked user activity from {csv_path} (dry_run={dry_run})")

    results: list[dict[str, Any]] = []

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    target_rows = [r for r in rows if is_target_user(r)]
    logger.info(
        f"Found {len(rows)} total rows in CSV, {len(target_rows)} active external targets."
    )

    for idx, row in enumerate(target_rows, start=1):
        user_id = row.get("user_id", "").strip()
        rank = int(row.get("rank", 0) or 0)
        first_name = row.get("first_name", "").strip()
        last_name = row.get("last_name", "").strip()
        email = row.get("email", "").strip()
        login_count = int(row.get("login_count", 0) or 0)
        active_minutes = int(row.get("active_minutes", 0) or 0)
        event_count = int(row.get("event_count", 0) or 0)
        active_days = int(row.get("active_days", 0) or 0)
        first_activity = row.get("first_activity", "").strip()
        last_activity = row.get("last_activity", "").strip()

        profile = resolve_profile(row)
        slug = profile["slug"]
        company_name = profile["company_name"]
        domain = profile["domain"]
        phone = profile.get("phone")
        street_address = profile.get("street_address")
        city = profile.get("city")
        state = profile.get("state")
        zip_code = str(profile.get("zip_code")) if profile.get("zip_code") else None

        rta_metrics = {
            "rank": rank,
            "user_id": user_id,
            "login_count": login_count,
            "active_minutes": active_minutes,
            "event_count": event_count,
            "active_days": active_days,
            "first_activity": first_activity,
            "last_activity": last_activity,
        }

        tags = [
            "client",
            "testimonial-target",
            "rta-user",
            f"rta-rank-{rank}",
            campaign,
        ]

        description = usage_description(
            first_name,
            last_name,
            str(profile["firm_name"]),
            rta_metrics,
        )

        company = Company(
            name=company_name,
            slug=slug,
            type="Client",
            domain=domain,
            phone_number=phone,
            street_address=street_address,
            city=city,
            state=state,
            zip_code=zip_code,
            email=email,
            tags=tags,
            campaigns=[campaign],
            rta_metrics=rta_metrics,
            description=description,
        )

        person = Person(
            name=f"{first_name} {last_name}",
            slug=slugify(f"{first_name}-{last_name}"),
            email=email,
            phone=phone,
            company_name=company_name,
            role="Advisor / Producer",
            tags=tags,
            street_address=street_address,
            city=city,
            state=state,
            zip_code=zip_code,
        )

        task = ToCallTask(
            company_slug=slug,
            domain=domain,
            campaign_name=campaign,
            priority=rank,
            callback_at=datetime.now(UTC),
        )

        logger.info(
            f"[{idx}/{len(target_rows)}] Target #{rank}: {first_name} {last_name} "
            f"({company_name}) -> Slug: {slug}, Phone: {phone or 'N/A'}"
        )

        if not dry_run:
            # 1. Save company (deferring cache rebuild to the end)
            company.save(rebuild_cache=False)
            # 2. Save person
            person.save()
            # 3. Link person contact to company
            contacts_dir = company.get_local_path().parent / "contacts"
            contacts_dir.mkdir(parents=True, exist_ok=True)
            symlink = contacts_dir / person.slug
            if not symlink.exists():
                symlink.symlink_to(person.get_local_path().parent)
            # 4. Save to-call pending task
            task.save()

        results.append(
            {
                "rank": rank,
                "user_id": user_id,
                "name": f"{first_name} {last_name}",
                "company": company_name,
                "slug": slug,
                "email": email,
                "phone": phone,
                "to_call_path": str(task.get_local_path()),
            }
        )

    if not dry_run and results:
        logger.info("Triggering campaign cache rebuild...")
        try:
            from cocli.core.cache import build_cache

            build_cache(campaign=campaign)
            logger.info("Campaign cache rebuild complete.")
        except Exception as e:
            logger.warning(f"Non-critical: Cache rebuild warning: {e}")

    logger.info(
        f"Completed ingestion of {len(results)} testimonial targets into campaign '{campaign}'."
    )
    return results


def select_recent_users(
    rows: list[dict[str, str]], limit: int = 40
) -> list[dict[str, str]]:
    """The ``limit`` users with the latest last_activity, re-ranked by event count.

    Ties on event_count share a rank, matching get_ranked_user_activity.sh.
    """
    dated = [row for row in rows if (row.get("last_activity") or "").strip()]
    dated.sort(key=lambda row: row.get("last_activity") or "", reverse=True)
    chosen = [dict(row) for row in dated[:limit]]
    chosen.sort(
        key=lambda row: (
            -int(row.get("event_count") or 0),
            -int(row.get("login_count") or 0),
            row.get("user_id") or "",
        )
    )
    previous_events: str | None = None
    rank = 0
    ranked: list[dict[str, str]] = []
    for index, row in enumerate(chosen, start=1):
        events = row.get("event_count") or ""
        if events != previous_events:
            rank = index
            previous_events = events
        updated = dict(row)
        updated["rank"] = str(rank)
        ranked.append(updated)
    return ranked


def usage_description(
    first_name: str,
    last_name: str,
    firm: str,
    metrics: dict[str, Any],
) -> str:
    return (
        f"# Testimonial Target: {first_name} {last_name}\n\n"
        f"- **Firm:** {firm}\n"
        f"- **Roadmap rank:** #{metrics['rank']}\n"
        f"- **Logins:** {metrics['login_count']}\n"
        f"- **Active Minutes:** {metrics['active_minutes']}\n"
        f"- **Active Days:** {metrics['active_days']}\n"
        f"- **Total Events:** {metrics['event_count']}\n"
        f"- **First Activity:** {metrics['first_activity']}\n"
        f"- **Last Activity:** {metrics['last_activity']}\n"
    )


def merge_usage_description(existing: str | None, block: str) -> str:
    """Replace the generated testimonial block and keep any notes written after it."""
    text = (existing or "").strip()
    if not text:
        return block
    if not text.startswith("# Testimonial Target:"):
        return text
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("- **Last Activity:") or line.startswith("- **Last activity:"):
            rest = "\n".join(lines[index + 1 :]).strip()
            if rest:
                return block.rstrip() + "\n\n" + rest + "\n"
            return block
    return block


def _metrics_from_row(row: dict[str, str]) -> dict[str, Any]:
    return {
        "rank": int(row.get("rank", 0) or 0),
        "user_id": row.get("user_id", "").strip(),
        "login_count": int(row.get("login_count", 0) or 0),
        "active_minutes": int(row.get("active_minutes", 0) or 0),
        "event_count": int(row.get("event_count", 0) or 0),
        "active_days": int(row.get("active_days", 0) or 0),
        "first_activity": row.get("first_activity", "").strip(),
        "last_activity": row.get("last_activity", "").strip(),
    }


def _contact_slug(
    company: Company | None, first_name: str, last_name: str
) -> str:
    """Keep the contact already linked on the company. A new name gets a fresh slug."""
    if company is not None:
        contacts_dir = company.get_local_path() / "contacts"
        if contacts_dir.is_dir():
            linked = sorted(
                child.name
                for child in contacts_dir.iterdir()
                if child.name and not child.name.startswith(".")
            )
            if linked:
                return linked[0]
    return slugify(f"{first_name}-{last_name}")


def _with_rank_tag(tags: list[str], rank: int, campaign: str) -> list[str]:
    kept = [tag for tag in tags if not tag.startswith("rta-rank-")]
    for needed in ("client", "testimonial-target", "rta-user", campaign, f"rta-rank-{rank}"):
        if needed not in kept:
            kept.append(needed)
    return kept


def refresh_usage(
    csv_path: Path,
    campaign: str = "roadmap",
    limit: int = 40,
    dry_run: bool = False,
    rebuild_cache: bool = True,
) -> list[dict[str, Any]]:
    """Update usage on the selected users without replacing call notes or follow-ups.

    ``limit`` applies after the file is read, to file order. Pass a CSV that
    ``select_recent_users`` already trimmed when the cap should be the most
    recent users rather than the first rows.
    """
    set_campaign(campaign)
    if not csv_path.exists():
        raise FileNotFoundError(f"Testimonial activity CSV not found at: {csv_path}")

    with open(csv_path, mode="r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    selected = rows[:limit]
    target_rows = [row for row in selected if is_target_user(row)]
    logger.info(
        "Refreshing usage for %s external users from %s rows (limit %s)",
        len(target_rows),
        len(selected),
        limit,
    )

    results: list[dict[str, Any]] = []
    for row in target_rows:
        metrics = _metrics_from_row(row)
        rank = int(metrics["rank"])
        first_name = row.get("first_name", "").strip()
        last_name = row.get("last_name", "").strip()
        email = row.get("email", "").strip()
        profile = resolve_profile(row)
        slug = str(profile["slug"])
        block = usage_description(
            first_name, last_name, str(profile["firm_name"]), metrics
        )
        existing = Company.get(slug)
        created = existing is None
        if existing is None:
            company = Company(
                name=profile["company_name"],
                slug=slug,
                type="Client",
                domain=profile["domain"],
                phone_number=profile.get("phone"),
                street_address=profile.get("street_address"),
                city=profile.get("city"),
                state=profile.get("state"),
                zip_code=str(profile["zip_code"]) if profile.get("zip_code") else None,
                email=email,
                tags=_with_rank_tag([], rank, campaign),
                campaigns=[campaign],
                rta_metrics=metrics,
                description=block,
            )
        else:
            company = existing
            company.rta_metrics = metrics
            company.tags = _with_rank_tag(list(company.tags or []), rank, campaign)
            company.description = merge_usage_description(company.description, block)
            if campaign not in (company.campaigns or []):
                company.campaigns = list(company.campaigns or []) + [campaign]

        person_slug = _contact_slug(company if not created else None, first_name, last_name)
        person_exists = Person.get(person_slug) is not None
        task = ToCallTask(
            company_slug=slug,
            domain=str(profile["domain"]),
            campaign_name=campaign,
            priority=rank,
            callback_at=None,
        )
        pending_path = task.get_local_path()
        completed_path = pending_path.parent.parent / "completed" / pending_path.name
        queue_task = not pending_path.exists() and not completed_path.exists()

        logger.info(
            "Usage rank #%s %s %s slug=%s created=%s queue=%s last=%s",
            rank,
            first_name,
            last_name,
            slug,
            created,
            queue_task,
            metrics["last_activity"],
        )
        if not dry_run:
            company.save(rebuild_cache=False)
            if not person_exists:
                Person(
                    name=f"{first_name} {last_name}",
                    slug=person_slug,
                    email=email,
                    phone=profile.get("phone"),
                    company_name=profile["company_name"],
                    role="Advisor / Producer",
                    tags=list(company.tags or []),
                    street_address=profile.get("street_address"),
                    city=profile.get("city"),
                    state=profile.get("state"),
                    zip_code=str(profile["zip_code"]) if profile.get("zip_code") else None,
                ).save()
            contacts_dir = company.get_local_path() / "contacts"
            contacts_dir.mkdir(parents=True, exist_ok=True)
            symlink = contacts_dir / person_slug
            if not symlink.exists():
                linked = Person.get(person_slug)
                if linked is not None:
                    symlink.symlink_to(linked.get_local_path())
            if queue_task:
                task.save()

        results.append(
            {
                "rank": rank,
                "slug": slug,
                "email": email,
                "created": created,
                "queued": queue_task,
                "last_activity": metrics["last_activity"],
            }
        )

    if not dry_run and rebuild_cache and results:
        logger.info("Triggering campaign cache rebuild...")
        try:
            from cocli.core.cache import build_cache

            build_cache(campaign=campaign)
            logger.info("Campaign cache rebuild complete.")
        except Exception as exc:
            logger.warning("Non-critical: Cache rebuild warning: %s", exc)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest top active RTA users into companies and to-call queue."
    )
    default_csv = (
        paths.campaign("roadmap").path
        / "initiatives"
        / "testimonials"
        / "ranked_user_activity.csv"
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=default_csv,
        help="Path to ranked_user_activity.csv",
    )
    parser.add_argument(
        "--campaign",
        type=str,
        default="roadmap",
        help="Campaign name (default: roadmap)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate ingestion without writing files",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Update usage on the CSV rows without replacing notes or follow-up dates",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=40,
        help="With --refresh, maximum CSV rows to apply (default: 40)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path(".logs/ingest_testimonials.log"),
        help="Path to log file (default: .logs/ingest_testimonials.log)",
    )

    args = parser.parse_args()
    setup_script_logging(args.log_file)

    try:
        if args.refresh:
            refresh_usage(
                csv_path=args.csv_path,
                campaign=args.campaign,
                limit=args.limit,
                dry_run=args.dry_run,
            )
        else:
            ingest_testimonials(
                csv_path=args.csv_path,
                campaign=args.campaign,
                dry_run=args.dry_run,
            )
    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
