"""LeadFilterEntry must own its own datapackage.json (never hand-authored),
covering both in.usv and out.usv as two resources in one sidecar."""

import json

from cocli.models.campaigns.indexes.lead_filter import LeadFilterEntry


def test_to_usv_from_usv_roundtrip() -> None:
    entry = LeadFilterEntry(
        slug="acme-floors", domain="acmefloors.com", verdict="out", reason="carpet/tile only"
    )
    parsed = LeadFilterEntry.from_usv(entry.to_usv())
    assert parsed == entry


def test_from_usv_tolerates_pre_schema_bare_slug_line() -> None:
    parsed = LeadFilterEntry.from_usv("acme-floors")
    assert parsed.slug == "acme-floors"
    assert parsed.domain is None
    assert parsed.verdict is None
    assert parsed.reason is None


def test_get_index_dir_is_campaign_scoped(mock_cocli_env, mocker) -> None:
    from cocli.core.paths import paths

    dir_a = LeadFilterEntry.get_index_dir("turboship")
    dir_b = LeadFilterEntry.get_index_dir("roadmap")
    assert dir_a != dir_b
    assert dir_a == paths.campaign("turboship").index("lead-filter").path


def test_append_resource_to_datapackage_covers_both_in_and_out(mock_cocli_env, mocker) -> None:
    """in.usv and out.usv share one directory - the second
    append_resource_to_datapackage call must not clobber the first
    resource's entry (write_datapackage() would, since it hardcodes a
    single resource path)."""
    index_dir = LeadFilterEntry.get_index_dir("turboship")
    index_dir.mkdir(parents=True, exist_ok=True)

    LeadFilterEntry.append_resource_to_datapackage(index_dir, "lead_filter_in", "in.usv")
    LeadFilterEntry.append_resource_to_datapackage(index_dir, "lead_filter_out", "out.usv")

    dp = json.loads((index_dir / "datapackage.json").read_text())
    resource_names = {r["name"] for r in dp["resources"]}
    assert resource_names == {"lead_filter_in", "lead_filter_out"}

    paths_by_name = {r["name"]: r["path"] for r in dp["resources"]}
    assert paths_by_name["lead_filter_in"] == "in.usv"
    assert paths_by_name["lead_filter_out"] == "out.usv"
