"""Roadmap usage facts stored on a company as ``rta_metrics``.

The field name is historical. Callers and the screens say The Roadmap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

USAGE_TAG_MARKERS = ("testimonial-target", "rta-user")


def company_has_usage_tag(tags: list[str] | None) -> bool:
    for tag in tags or []:
        if tag in USAGE_TAG_MARKERS or tag.startswith("rta-rank-"):
            return True
    return False


def read_rta_metrics(slug: str) -> dict[str, Any] | None:
    """Frontmatter ``rta_metrics`` for one company. Does not apply the field journal."""
    from cocli.core.paths import paths

    index_path = paths.companies.entry(slug).index
    return read_rta_metrics_file(index_path)


def read_rta_metrics_file(index_path: Path) -> dict[str, Any] | None:
    if not index_path.is_file():
        return None
    text = index_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    metrics = meta.get("rta_metrics") if isinstance(meta, dict) else None
    if isinstance(metrics, dict) and metrics:
        return metrics
    return None


def rank_from_tags(tags: list[str] | None) -> str | None:
    for tag in tags or []:
        if tag.startswith("rta-rank-"):
            rank = tag.split("rta-rank-", 1)[-1].strip()
            if rank:
                return rank
    return None


def usage_bits(
    metrics: Mapping[str, Any] | None,
    rank_fallback: str | None = None,
) -> list[tuple[str, str]]:
    """Ordered (kind, value) pairs. Kinds: rank, logins, minutes, days, events, last."""
    bits: list[tuple[str, str]] = []
    data = metrics if isinstance(metrics, Mapping) else None
    if data:
        rank = data.get("rank")
        if rank not in (None, ""):
            bits.append(("rank", str(rank)))
        for kind, key in (
            ("logins", "login_count"),
            ("minutes", "active_minutes"),
            ("days", "active_days"),
            ("events", "event_count"),
        ):
            value = data.get(key)
            if value not in (None, ""):
                bits.append((kind, str(value)))
        last = data.get("last_activity")
        if last not in (None, ""):
            bits.append(("last", str(last)[:10]))
    elif rank_fallback:
        bits.append(("rank", rank_fallback))
    return bits


def usage_plain(
    metrics: Mapping[str, Any] | None,
    rank_fallback: str | None = None,
) -> str:
    labels = {
        "rank": "Rank #",
        "logins": " logins",
        "minutes": " active min",
        "days": " active days",
        "events": " events",
        "last": "last ",
    }
    parts: list[str] = []
    for kind, value in usage_bits(metrics, rank_fallback):
        label = labels[kind]
        if kind in ("rank", "last"):
            parts.append(f"{label}{value}")
        else:
            parts.append(f"{value}{label}")
    return " · ".join(parts)


def usage_markup(
    metrics: Mapping[str, Any] | None,
    rank_fallback: str | None = None,
) -> str:
    colors = {
        "rank": "cyan",
        "logins": "green",
        "minutes": "yellow",
        "days": "white",
        "events": "magenta",
        "last": "cyan",
    }
    parts: list[str] = []
    for kind, value in usage_bits(metrics, rank_fallback):
        color = colors[kind]
        if kind == "rank":
            parts.append(f"Rank [bold {color}]#{value}[/]")
        elif kind == "logins":
            parts.append(f"[bold {color}]{value}[/] logins")
        elif kind == "minutes":
            parts.append(f"[bold {color}]{value}[/] active min")
        elif kind == "days":
            parts.append(f"[bold {color}]{value}[/] active days")
        elif kind == "events":
            parts.append(f"[bold {color}]{value}[/] events")
        else:
            parts.append(f"last [bold {color}]{value}[/]")
    return " • ".join(parts)


def attach_stored_usage(company: Any) -> None:
    """Fill ``rta_metrics`` from the company file when the search row only has the rank tag."""
    if getattr(company, "rta_metrics", None):
        return
    tags = list(getattr(company, "tags", None) or [])
    if not company_has_usage_tag(tags):
        return
    slug = getattr(company, "slug", None)
    if not slug:
        return
    metrics = read_rta_metrics(str(slug))
    if metrics:
        company.rta_metrics = metrics
