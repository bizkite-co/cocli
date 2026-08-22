"""Per-content-type lease duration defaults on the FilesystemQueue subclasses.

Each queue's default should safely exceed its own task's worst-case runtime
(see comments at each subclass's __init__ in cocli/core/queue/filesystem.py)
while staying as short as possible so a dead worker's claim is reclaimed
quickly.
"""

from cocli.core.queue.filesystem import (
    FilesystemEnrichmentQueue,
    FilesystemGmDetailsQueue,
    FilesystemGmListQueue,
)


def test_gm_list_lease_exceeds_absolute_scrape_ceiling() -> None:
    queue = FilesystemGmListQueue(campaign_name="test-campaign")
    assert queue.lease_duration == 30


def test_gm_details_lease_is_short() -> None:
    queue = FilesystemGmDetailsQueue(campaign_name="test-campaign")
    assert queue.lease_duration == 3


def test_enrichment_lease_is_short() -> None:
    queue = FilesystemEnrichmentQueue(campaign_name="test-campaign")
    assert queue.lease_duration == 5


def test_lease_duration_still_overridable() -> None:
    queue = FilesystemGmDetailsQueue(campaign_name="test-campaign", lease_duration_minutes=7)
    assert queue.lease_duration == 7
