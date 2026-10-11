"""Publish the relationship journal as a readable company folder (ADR-014).

Writes ``companies/<slug>/org.md`` and regenerates ``units/`` and ``contacts/``
symlinks. The journal segments are left in place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

from cocli.application.relationships import FoldPolicy, Predicate, fold_policy
from cocli.core.relationship_log import (
    fold_relationship_instances,
    open_relationship_log,
)
from cocli.models.wal.relationship import RelationshipRecord

logger = logging.getLogger(__name__)


@dataclass
class CompanyOrg:
    """Open edges that explain one company."""

    parents: list[RelationshipRecord] = field(default_factory=list)
    children: list[RelationshipRecord] = field(default_factory=list)
    departments: list[RelationshipRecord] = field(default_factory=list)
    unit_of: list[RelationshipRecord] = field(default_factory=list)
    sites: list[RelationshipRecord] = field(default_factory=list)
    workers: list[RelationshipRecord] = field(default_factory=list)
    members: list[RelationshipRecord] = field(default_factory=list)


def publish_relationship_journal(
    *,
    data_root: Path,
    wal_root: Optional[Path] = None,
) -> int:
    """Fold the retained journal and publish present-state files.

    Returns the number of company folders written. Does not delete or move
    journal segments.
    """
    edge = open_relationship_log(wal_root=wal_root)
    records = list(edge.iter_beyond())
    return publish_relationship_present_state(records, data_root=data_root)


def publish_relationship_present_state(
    records: Sequence[RelationshipRecord],
    *,
    data_root: Path,
) -> int:
    """Rewrite ``org.md`` and relationship symlinks for companies in ``records``."""
    folded = _folded_instances(records)
    charts = _charts_for(folded)
    for slug, chart in sorted(charts.items()):
        _write_company(data_root, slug, chart)
        logger.info("published org chart for %s", slug)
    return len(charts)


def render_org_md(slug: str, chart: CompanyOrg) -> str:
    """Plain-text explanation of one company's open relationships."""
    lines = [
        f"# {slug}",
        "",
        "parentOrganization:",
        *_lines(chart.parents, lambda rec: rec.object_key),
        "subOrganization:",
        *_lines(chart.children, lambda rec: rec.subject),
        "department:",
        *_lines(chart.departments, lambda rec: rec.object_key),
        "unitOf:",
        *_lines(chart.unit_of, lambda rec: rec.subject),
        "sites:",
        *_lines(chart.sites, lambda rec: rec.object_key),
        "worksFor:",
        *_lines(chart.workers, lambda rec: rec.subject),
        "membership:",
        *_lines(chart.members, lambda rec: rec.subject),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _folded_instances(records: Sequence[RelationshipRecord]) -> list[RelationshipRecord]:
    instances = [
        rec
        for rec in records
        if fold_policy(rec.predicate) is FoldPolicy.INSTANCE
    ]
    return fold_relationship_instances(instances)


def _charts_for(records: Sequence[RelationshipRecord]) -> dict[str, CompanyOrg]:
    """Build a chart for every company an instance fact mentions.

    Closed facts still mark the company so a later publish can drop stale
    symlinks. Only open facts (empty ``ended_at``) appear in the chart.
    """
    slugs: set[str] = set()
    for rec in records:
        if rec.subject_type == "company":
            slugs.add(_slug(rec.subject))
        if rec.object_type == "company":
            slugs.add(_slug(rec.object_key))
    charts = {slug: CompanyOrg() for slug in slugs}
    for rec in records:
        if rec.ended_at:
            continue
        _place(charts, rec)
    return charts


def _place(charts: dict[str, CompanyOrg], rec: RelationshipRecord) -> None:
    predicate = rec.predicate
    if predicate == Predicate.PARENT_ORGANIZATION.value:
        if rec.subject_type == "company":
            charts[_slug(rec.subject)].parents.append(rec)
        if rec.object_type == "company":
            charts[_slug(rec.object_key)].children.append(rec)
        return
    if predicate == Predicate.DEPARTMENT.value:
        if rec.subject_type == "company":
            charts[_slug(rec.subject)].departments.append(rec)
        if rec.object_type == "company":
            charts[_slug(rec.object_key)].unit_of.append(rec)
        return
    if predicate == Predicate.HAS_SITE.value and rec.subject_type == "company":
        charts[_slug(rec.subject)].sites.append(rec)
        return
    if predicate == Predicate.WORKS_FOR.value and rec.object_type == "company":
        charts[_slug(rec.object_key)].workers.append(rec)
        return
    if predicate == Predicate.MEMBERSHIP.value and rec.object_type == "company":
        charts[_slug(rec.object_key)].members.append(rec)


def _write_company(data_root: Path, slug: str, chart: CompanyOrg) -> None:
    company_dir = data_root / "companies" / slug
    company_dir.mkdir(parents=True, exist_ok=True)
    (company_dir / "org.md").write_text(render_org_md(slug, chart), encoding="utf-8")
    unit_links = {
        _slug(rec.subject): Path("..") / ".." / _slug(rec.subject)
        for rec in chart.children
    }
    unit_links.update(
        {
            _slug(rec.object_key): Path("..") / ".." / _slug(rec.object_key)
            for rec in chart.departments
            if rec.object_type == "company"
        }
    )
    contact_links = {
        _slug(rec.subject): Path("..") / ".." / ".." / "people" / _slug(rec.subject)
        for rec in (*chart.workers, *chart.members)
        if rec.subject_type == "person"
    }
    _sync_symlinks(company_dir / "units", unit_links)
    _sync_symlinks(company_dir / "contacts", contact_links)


def _sync_symlinks(directory: Path, links: dict[str, Path]) -> None:
    """Make ``directory`` contain exactly the relationship symlinks in ``links``.

    Regular files are left alone. Symlinks whose names are no longer open
    relationships are removed.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for name, target in sorted(links.items()):
        path = directory / name
        if path.is_symlink():
            if path.readlink() == target:
                continue
            path.unlink()
        elif path.exists():
            raise FileExistsError(
                f"{path} exists and is not a symlink; refusing to replace it"
            )
        path.symlink_to(target)
    for existing in directory.iterdir():
        if existing.name not in links and existing.is_symlink():
            existing.unlink()


def _lines(
    records: Sequence[RelationshipRecord],
    label_of: Callable[[RelationshipRecord], str],
) -> list[str]:
    if not records:
        return ["- (none)", ""]
    ordered = sorted(records, key=lambda rec: (label_of(rec), rec.relationship_id))
    return [_fact_line(label_of(rec), rec) for rec in ordered] + [""]


def _fact_line(label: str, rec: RelationshipRecord) -> str:
    primary = "yes" if rec.is_primary else "no"
    return (
        f"- {label} since={rec.started_at or '-'} until={rec.ended_at or '-'} "
        f"primary={primary} source={rec.source or '-'} "
        f"method={rec.method or '-'} observed_at={rec.observed_at or '-'}"
    )


def _slug(value: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"unsafe relationship slug {value!r}")
    return value
