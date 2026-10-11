"""Closed relationship vocabulary (ADR-014).

New relationship kinds are entries here. The journal record does not change.
"""

from __future__ import annotations

from enum import Enum


class FoldPolicy(Enum):
    """Which pure fold in ``cocli.core.relationship_log`` applies."""

    INSTANCE = "instance"
    OBSERVATION = "observation"
    OBSERVATION_MEMBER = "observation_member"


class Predicate(Enum):
    """Allowed ``RelationshipRecord.predicate`` values."""

    PARENT_ORGANIZATION = "parentOrganization"
    DEPARTMENT = "department"
    HAS_SITE = "hasSite"
    WORKS_FOR = "worksFor"
    MEMBERSHIP = "membership"
    USES_EMAIL_SERVICE = "usesEmailService"
    USES_TECHNOLOGY = "usesTechnology"


_POLICY: dict[Predicate, FoldPolicy] = {
    Predicate.PARENT_ORGANIZATION: FoldPolicy.INSTANCE,
    Predicate.DEPARTMENT: FoldPolicy.INSTANCE,
    Predicate.HAS_SITE: FoldPolicy.INSTANCE,
    Predicate.WORKS_FOR: FoldPolicy.INSTANCE,
    Predicate.MEMBERSHIP: FoldPolicy.INSTANCE,
    Predicate.USES_EMAIL_SERVICE: FoldPolicy.OBSERVATION,
    Predicate.USES_TECHNOLOGY: FoldPolicy.OBSERVATION_MEMBER,
}


def fold_policy(predicate: str) -> FoldPolicy:
    """Return the fold for a predicate name. Unknown names raise."""
    try:
        kind = Predicate(predicate)
    except ValueError as exc:
        known = ", ".join(item.value for item in Predicate)
        raise ValueError(
            f"unknown relationship predicate {predicate!r}; known: {known}"
        ) from exc
    return _POLICY[kind]
