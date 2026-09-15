"""write_lead_filter_entries must converge the algorithmic lead-filter and
the human call-log disposition on one campaign-wide invalid set, not leave
them as two disconnected "this company is bad" lists."""

from cocli.application.lead_filter_service import write_lead_filter_entries
from cocli.core.exclusions import ExclusionManager
from cocli.models.campaigns.indexes.lead_filter import LeadFilterEntry

CAMPAIGN = "turboship"


def test_writes_in_and_out_usv_split_by_verdict(mock_cocli_env, mocker) -> None:
    entries = [
        LeadFilterEntry(slug="good-co", domain="good.com", verdict="in"),
        LeadFilterEntry(slug="bad-co", domain="bad.com", verdict="out", reason="hardware store"),
    ]
    in_path, out_path = write_lead_filter_entries(CAMPAIGN, entries)

    assert LeadFilterEntry.from_usv(in_path.read_text().strip()).slug == "good-co"
    assert LeadFilterEntry.from_usv(out_path.read_text().strip()).slug == "bad-co"


def test_algorithmic_out_verdict_feeds_forward_into_exclusion_manager(
    mock_cocli_env, mocker
) -> None:
    """An "out" verdict from the filter script must become a durable,
    campaign-wide exclusion - the same set to-call compilation and
    rendering-time checks already consult - so it doesn't resurface
    elsewhere just because the lead-filter step didn't touch it."""
    entries = [
        LeadFilterEntry(slug="bad-co", domain="bad.com", verdict="out", reason="hardware store"),
    ]
    write_lead_filter_entries(CAMPAIGN, entries)

    excl = ExclusionManager(CAMPAIGN)
    assert excl.is_excluded(slug="bad-co")
    assert excl.get_exclusion(slug="bad-co").reason == "hardware store"


def test_existing_human_exclusion_feeds_backward_overriding_in_verdict(
    mock_cocli_env, mocker
) -> None:
    """A company already marked Wrong Trade / No Fit via the call log must
    end up "out" here even if the algorithmic criteria say "in" - a human
    verdict always wins over the automated one."""
    ExclusionManager(CAMPAIGN).add_exclusion(
        slug="flagged-co", domain="flagged.com", reason="to-call-nonconforming"
    )

    entries = [
        LeadFilterEntry(slug="flagged-co", domain="flagged.com", verdict="in"),
        LeadFilterEntry(slug="fine-co", domain="fine.com", verdict="in"),
    ]
    in_path, out_path = write_lead_filter_entries(CAMPAIGN, entries)

    in_slugs = {LeadFilterEntry.from_usv(line).slug for line in in_path.read_text().splitlines() if line}
    out_slugs = {LeadFilterEntry.from_usv(line).slug for line in out_path.read_text().splitlines() if line}
    assert in_slugs == {"fine-co"}
    assert out_slugs == {"flagged-co"}


def test_datapackage_covers_both_resources_after_write(mock_cocli_env, mocker) -> None:
    import json

    entries = [LeadFilterEntry(slug="good-co", domain="good.com", verdict="in")]
    in_path, _ = write_lead_filter_entries(CAMPAIGN, entries)

    dp = json.loads((in_path.parent / "datapackage.json").read_text())
    resource_names = {r["name"] for r in dp["resources"]}
    assert resource_names == {"lead_filter_in", "lead_filter_out"}
