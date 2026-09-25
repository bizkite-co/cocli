#!/usr/bin/env python3
"""Batch-enqueue and render follow-up email drafts for Roadmap RTA testimonial targets."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from cocli.core.paths import paths
from cocli.models.companies.company import Company
from cocli.models.people.person import Person
from cocli.application.follow_up_service import FollowUpService

logger = logging.getLogger("enqueue_testimonials_follow_up")


def setup_script_logging(log_file: Path) -> None:
    logger.setLevel(logging.DEBUG)

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(fh)
    except OSError:
        pass

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(ch)


def link_person_contacts(campaign: str = "roadmap", dry_run: bool = False) -> int:
    """Ensure every testimonial-target company has its Person contact symlinked in contacts/."""
    companies_dir = paths.companies.ensure()
    linked_count = 0

    logger.info("Indexing people directory once for fast contact matching...")
    people_records: list[Person] = []
    for p_dir in paths.people.path.glob("*"):
        p = Person.from_directory(p_dir)
        if p:
            people_records.append(p)
    logger.info("Indexed %d people records.", len(people_records))

    cache_path = paths.campaign(campaign).path / "indexes" / "company_cache" / "company_cache.usv"
    candidate_slugs: list[str] = []
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            if "testimonial-target" in line:
                candidate_slugs.append(line.split("\x1f")[0])
    else:
        for idx_file in sorted(companies_dir.glob("*/_index.md")):
            slug = idx_file.parent.name
            company = Company.get(slug)
            if company and company.belongs_to_campaign(campaign) and "testimonial-target" in (company.tags or []):
                candidate_slugs.append(slug)

    for slug in candidate_slugs:
        company = Company.get(slug)
        if not company:
            continue

        # Look for matching Person in paths.people
        contacts_dir = paths.companies.entry(slug).path / "contacts"
        existing_symlinks = [p for p in contacts_dir.iterdir() if p.is_symlink()] if contacts_dir.exists() else []

        valid_existing = False
        if existing_symlinks:
            # Check if any existing symlink is invalid / pointing to the entire people dir
            for p in existing_symlinks:
                try:
                    if p.resolve() == paths.people.path:
                        if not dry_run:
                            p.unlink()
                    elif p.exists():
                        valid_existing = True
                except OSError:
                    pass

        if valid_existing:
            logger.debug("Company %s already has valid contact", slug)
            continue

        # Find candidate person from in-memory index
        matched_person: Person | None = None
        for p in people_records:
            if p.company_name == company.name or (company.email and p.email == company.email):
                matched_person = p
                break

        if not matched_person:
            # Fallback by slug matching
            for p in people_records:
                if p.slug in slug:
                    matched_person = p
                    break

        if matched_person:
            logger.info("Linking %s -> %s", slug, matched_person.slug)
            if not dry_run:
                contacts_dir.mkdir(parents=True, exist_ok=True)
                symlink = contacts_dir / matched_person.slug
                if symlink.is_symlink():
                    symlink.unlink()
                symlink.symlink_to(matched_person.get_local_path())
            linked_count += 1
        else:
            logger.warning("No Person record found for company %s", slug)

    return linked_count


def enqueue_and_render_testimonials(
    campaign: str = "roadmap",
    template: str = "request_testimonial.md",
    initiative: str = "testimonials",
    tag: str = "testimonial-target",
    render: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Enqueue all testimonial targets into FollowUpQueue and optionally render drafts via enqueue_initiative."""
    service = FollowUpService(campaign)

    logger.info("Checking contact symlinks for %s targets...", tag)
    linked = link_person_contacts(campaign, dry_run=dry_run)
    logger.info("Ensured %d contact symlinks.", linked)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task_id = progress.add_task("Executing initiative enqueue...", total=1)
        res = service.enqueue_initiative(
            initiative,
            template_id=template,
            render=render,
            dry_run=dry_run,
        )
        progress.update(task_id, completed=1)

    logger.info(
        "Initiative '%s': %d enqueued, %d rendered. (%d errors)",
        initiative,
        res.enqueued,
        res.rendered,
        len(res.errors),
    )
    if res.errors:
        for err in res.errors:
            logger.warning("Error: %s", err)

    return {
        "enqueued": res.enqueued,
        "rendered": res.rendered,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enqueue and render follow-up email drafts for testimonial targets."
    )
    parser.add_argument(
        "--campaign",
        type=str,
        default="roadmap",
        help="Campaign name (default: roadmap)",
    )
    parser.add_argument(
        "--template",
        type=str,
        default="request_testimonial.md",
        help="Template name (default: request_testimonial.md)",
    )
    parser.add_argument(
        "--initiative",
        type=str,
        default="testimonials",
        help="Initiative name (default: testimonials)",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default="testimonial-target",
        help="Company tag (default: testimonial-target)",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Do not immediately render drafts (leave in follow-up queue)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without writing files",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path(".logs/enqueue_testimonials_follow_up.log"),
        help="Path to log file (default: .logs/enqueue_testimonials_follow_up.log)",
    )

    args = parser.parse_args()
    setup_script_logging(args.log_file)

    try:
        enqueue_and_render_testimonials(
            campaign=args.campaign,
            template=args.template,
            initiative=args.initiative,
            tag=args.tag,
            render=not args.no_render,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        logger.error("Execution failed: %s", exc, exc_info=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
