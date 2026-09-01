from pathlib import Path
from unittest.mock import patch

import pytest

from cocli.core.exclusions import ExclusionManager, list_all_exclusions
from cocli.core.paths import paths


@pytest.fixture
def sandboxed_root(tmp_path: Path):
    with patch.object(paths, "root", tmp_path):
        yield tmp_path


def test_campaign_scoped_exclusion_does_not_appear_in_a_different_campaign(
    sandboxed_root: Path,
) -> None:
    ExclusionManager("campaign-a").add_exclusion(slug="only-in-a")

    assert ExclusionManager("campaign-a").is_excluded(slug="only-in-a") is True
    assert ExclusionManager("campaign-b").is_excluded(slug="only-in-a") is False


def test_global_scope_is_shared_across_campaigns(sandboxed_root: Path) -> None:
    ExclusionManager("campaign-a", global_scope=True).add_exclusion(slug="excluded-everywhere")

    assert ExclusionManager("campaign-b", global_scope=True).is_excluded(slug="excluded-everywhere") is True


def test_list_all_exclusions_combines_campaign_and_global(sandboxed_root: Path) -> None:
    """Regression (Mark, 2026-09-01): compile-to-call's selection query
    must exclude a company whether it's excluded just for this campaign or
    excluded everywhere - either list applies."""
    ExclusionManager("roadmap").add_exclusion(slug="campaign-only")
    ExclusionManager("roadmap", global_scope=True).add_exclusion(slug="global-only")

    slugs = {e.company_slug for e in list_all_exclusions("roadmap") if e.company_slug}
    assert slugs == {"campaign-only", "global-only"}

    # A different campaign sees the global one but not the campaign-scoped one
    other_slugs = {e.company_slug for e in list_all_exclusions("other-campaign") if e.company_slug}
    assert other_slugs == {"global-only"}
