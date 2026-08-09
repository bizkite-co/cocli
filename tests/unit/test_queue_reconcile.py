"""reconcile_identities: generic identity-set diff between two queue-shaped
directory trees, used to answer "how much work remains" without depending
on which directory (mission pool, pending, or receipts) a given queue's
live pipeline happens to be reading from - see task-agent ticket
gm-list-queue-regressed-from-pendingcompleted-pattern-diverged-from-its-own-stations-declaration.
"""

from pathlib import Path

from cocli.core.queue.reconcile import reconcile_identities


def _write(root: Path, rel_path: str) -> None:
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("data")


def test_matches_across_different_shard_buckets(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write(left, "2/28.7/-96.9/sports-flooring-contractor.usv")
    _write(right, "9/28.7/-96.9/sports-flooring-contractor.json")

    result = reconcile_identities(left, right)

    assert result.matched == 1
    assert result.left_only == frozenset()
    assert result.right_only == frozenset()


def test_left_only_and_right_only(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write(left, "1/10.0/-80.0/phrase-a.usv")
    _write(left, "1/10.0/-80.0/phrase-b.usv")
    _write(right, "1/10.0/-80.0/phrase-a.json")
    _write(right, "1/10.0/-80.0/phrase-c.json")

    result = reconcile_identities(left, right)

    assert result.left_total == 2
    assert result.right_total == 2
    assert result.matched == 1
    assert result.left_only == frozenset({"10.0/-80.0/phrase-b"})
    assert result.right_only == frozenset({"10.0/-80.0/phrase-c"})


def test_excludes_sidecar_and_bookkeeping_files(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write(left, "1/10.0/-80.0/phrase-a.usv")
    _write(left, "datapackage.json")
    _write(left, "schema_ledger.json")
    _write(left, "1/10.0/-80.0/lease.json")
    _write(right, "1/10.0/-80.0/phrase-a.json")

    result = reconcile_identities(left, right)

    assert result.left_total == 1
    assert result.matched == 1


def test_missing_directory_treated_as_empty(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "does-not-exist"
    _write(left, "1/10.0/-80.0/phrase-a.usv")

    result = reconcile_identities(left, right)

    assert result.left_total == 1
    assert result.right_total == 0
    assert result.left_only == frozenset({"10.0/-80.0/phrase-a"})


def test_strip_leading_segments_zero_requires_exact_prefix_match(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write(left, "2/28.7/-96.9/sports-flooring-contractor.usv")
    _write(right, "9/28.7/-96.9/sports-flooring-contractor.json")

    result = reconcile_identities(left, right, strip_leading_segments=0)

    assert result.matched == 0
    assert len(result.left_only) == 1
    assert len(result.right_only) == 1
