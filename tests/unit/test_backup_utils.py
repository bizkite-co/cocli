from pathlib import Path

from cocli.utils.backup_utils import timestamped_backup_path


def test_timestamped_backup_path_appends_stamp_and_bak() -> None:
    result = timestamped_backup_path(Path("/tmp/campaigns/t/prospects.usv"))
    assert result.parent == Path("/tmp/campaigns/t")
    assert result.name.startswith("prospects.usv.")
    assert result.name.endswith(".bak")
    # e.g. prospects.usv.20260804T153000Z.bak
    stamp = result.name[len("prospects.usv.") : -len(".bak")]
    assert len(stamp) == len("20260804T153000Z")
    assert stamp[8] == "T" and stamp[-1] == "Z"


def test_timestamped_backup_path_never_collides_with_plain_bak() -> None:
    result = timestamped_backup_path(Path("prospects.usv"))
    assert result.name != "prospects.usv.bak"


def test_timestamped_backup_path_two_calls_do_not_collide_on_reruns() -> None:
    """Not a guarantee of sub-second uniqueness, but proves the whole point
    of this policy: a re-run does not silently overwrite the same filename
    an earlier run used, the way the old `.bak` scheme did."""
    import time

    first = timestamped_backup_path(Path("prospects.usv"))
    time.sleep(1.1)
    second = timestamped_backup_path(Path("prospects.usv"))
    assert first != second
