"""From-model-to-model field-lineage integrity checker (ADR-001).

Declares an explicit field contract per real transform edge (a function or
method - keyed by name, not a `transform_*` naming convention, since real
transforms in this codebase are often methods like `to_task`/`from_raw`) and
runs the REAL transform against a fully-populated set of source values to
verify every field survives - including merge/fallback rules, checked by
value equality, not just non-null presence.

Generic auto-mapping libraries (automapper, pydantic-mapper, etc.) are
deliberately not used here: they copy same-named fields and silently skip
renames, which is the exact failure mode this exists to catch (see
task-agent ticket build-a-from-model-to-model-field-lineage-integrity-validator).

Product-specific field maps (GoogleMapsListItem, GmItemTask, etc.) belong in
cocli, not in the stations library - this module knows nothing about any
specific model, only the generic contract-checking machinery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Fallback:
    """Merge policy for one target field: prefer `primary`'s value (a key
    into the source_values dict) if truthy, else use `fallback_field`'s."""

    primary: str
    fallback_field: str

    def resolve(self, source_values: dict[str, Any]) -> Any:
        primary_val = source_values.get(self.primary)
        if primary_val:
            return primary_val
        return source_values.get(self.fallback_field)


@dataclass
class FieldMap:
    """The field contract for one real transform edge.

    source_fields/target_fields are the field names this map is responsible
    for accounting for - not necessarily every field on either side's model;
    a map may be scoped to just the fields relevant to one merge concern.
    """

    name: str
    source_fields: set[str]
    target_fields: set[str]
    map: dict[str, str] = field(default_factory=dict)
    merge: dict[str, Fallback] = field(default_factory=dict)
    source_unmapped: set[str] = field(default_factory=set)
    target_unmapped: set[str] = field(default_factory=set)

    def structural_coverage_problems(self) -> list[str]:
        """Fields with no map/merge/unmapped declaration on either side -
        the 'we forgot this field exists' case."""
        problems = []

        accounted_source = set(self.map.keys()) | self.source_unmapped
        for rule in self.merge.values():
            accounted_source.add(rule.primary)
            accounted_source.add(rule.fallback_field)
        for f in self.source_fields:
            if f not in accounted_source:
                problems.append(
                    f"source field '{f}' has no map/merge/source_unmapped entry"
                )

        accounted_target = (
            set(self.map.values()) | set(self.merge.keys()) | self.target_unmapped
        )
        for f in self.target_fields:
            if f not in accounted_target:
                problems.append(
                    f"target field '{f}' has no map/merge/target_unmapped entry"
                )
        return problems


def assert_transform_field_integrity(
    edge: FieldMap,
    source_values: dict[str, Any],
    call_transform: Callable[[dict[str, Any]], Any],
    get_target_field: Callable[[Any, str], Any] = getattr,
) -> None:
    """Runs the REAL transform (via call_transform - real transforms have
    varying call signatures, methods vs multi-kwarg functions, so a generic
    checker can't invoke them uniformly without an adapter) and asserts
    every declared field survives per the FieldMap: direct maps by equality,
    merge/fallback fields by the declared policy - not just non-null.
    """
    problems = edge.structural_coverage_problems()
    assert not problems, (
        f"[{edge.name}] structural coverage gaps (declare or fix): "
        + "; ".join(problems)
    )

    result = call_transform(source_values)

    for src_field, tgt_field in edge.map.items():
        expected = source_values.get(src_field)
        actual = get_target_field(result, tgt_field)
        assert actual == expected, (
            f"[{edge.name}] {src_field} -> {tgt_field}: "
            f"expected {expected!r}, got {actual!r}"
        )

    for tgt_field, rule in edge.merge.items():
        expected = rule.resolve(source_values)
        actual = get_target_field(result, tgt_field)
        assert actual == expected, (
            f"[{edge.name}] merge {tgt_field} (prefer {rule.primary}, "
            f"fallback {rule.fallback_field}): expected {expected!r}, got {actual!r}"
        )
