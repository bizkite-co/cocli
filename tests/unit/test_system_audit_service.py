import json

from cocli.core.paths import paths
from cocli.application.audit_service import AuditService, parse_cli_tree, search_cli_tree


def test_get_cli_tree():
    from typer.main import get_command
    from cocli.main import app as main_app
    click_command = get_command(main_app)
    service = AuditService(campaign_name="test-campaign")
    tree = service.get_cli_tree(click_command)
    assert isinstance(tree, str)
    assert len(tree) > 0
    assert "cocli" in tree
    assert "audit" in tree


# `cocli help <phrase>` (2026-08-31): a fuzzy search over dump_cli_tree()'s
# text, added because grepping cocli --help-text requires already knowing a
# near-exact term. Reuses dump_cli_tree's output format rather than
# re-deriving the command tree - these tests exercise parse_cli_tree()
# against hand-crafted tree text so they don't depend on the real CLI's
# current command set.
_SAMPLE_TREE = """\
cocli
    --campaign/-c (text)
    --help-text/-ht (boolean)
    audit - Auditing tools for the cocli system structure and integrity.
        queue - Audit specific queues.
            purge-leases - Purge stale or expired leases from a queue directory.
                --campaign (text)
                --queue-name (text)
                --force (boolean)
    deduplicate
        deduplicate - Deduplicates company data by generating a stable hash.
            --dry-run (boolean)
    status - Displays the current status of the cocli environment.
        --campaign (text)
    admin - Administrative commands for system management.
        --force/-f (boolean)
        --s3 (boolean)
"""


def test_parse_cli_tree_builds_full_paths_for_nested_commands():
    entries = {e.path: e for e in parse_cli_tree(_SAMPLE_TREE)}

    assert "audit queue purge-leases" in entries
    leased = entries["audit queue purge-leases"]
    assert leased.description == "Purge stale or expired leases from a queue directory."
    assert leased.options == ["--campaign (text)", "--queue-name (text)", "--force (boolean)"]

    # Intermediate group nodes (audit, audit queue) are their own entries too.
    assert "audit" in entries
    assert "audit queue" in entries


def test_parse_cli_tree_handles_bare_group_header_without_description():
    """Regression: a Typer sub-app registered without help= (e.g.
    "deduplicate") prints as a bare name line with no " - description" and
    no "(type)" marker - indistinguishable from an option/arg line unless
    parse_cli_tree specifically falls back to treating it as a command."""
    entries = {e.path: e for e in parse_cli_tree(_SAMPLE_TREE)}

    assert "deduplicate" in entries
    assert entries["deduplicate"].description == ""
    # The bare group header's own children must not have been swallowed
    # into the PRECEDING entry (audit queue purge-leases) as bogus options.
    assert entries["audit queue purge-leases"].options == [
        "--campaign (text)",
        "--queue-name (text)",
        "--force (boolean)",
    ]

    assert "deduplicate deduplicate" in entries
    assert entries["deduplicate deduplicate"].description.startswith("Deduplicates")


def test_parse_cli_tree_root_line_is_not_a_spurious_path_prefix():
    """Regression: the root "cocli" line has no description and, once bare
    group headers are handled, would otherwise get pushed onto the path
    stack too - doubling every top-level command's path to "cocli status"
    instead of "status"."""
    entries = {e.path: e for e in parse_cli_tree(_SAMPLE_TREE)}

    assert "status" in entries
    assert "cocli status" not in entries
    assert "cocli" not in entries


def test_search_cli_tree_finds_command_by_partial_phrase():
    results = search_cli_tree(_SAMPLE_TREE, "lease")
    assert results
    assert results[0].path == "audit queue purge-leases"
    assert results[0].score == 100


def test_search_cli_tree_nonsense_query_returns_nothing():
    """Regression: partial_ratio scored against the bare path (rather than
    the full path+description+options haystack) gave short candidate paths
    like "tui" a 67% match against a completely unrelated nonsense query,
    purely from character-alignment coincidence on a short string."""
    results = search_cli_tree(_SAMPLE_TREE, "zzz-no-such-thing-zzz")
    assert results == []


def test_search_cli_tree_respects_limit():
    results = search_cli_tree(_SAMPLE_TREE, "campaign", limit=1, min_score=0)
    assert len(results) == 1


def test_search_cli_tree_default_threshold_excludes_partial_ratio_noise_floor():
    """Regression (Mark, 2026-08-31): `cocli help lease` returned a wall of
    dozens of otherwise-unrelated commands (audit fs, audit schemas, ...)
    all scored at exactly ~60% - partial_ratio finds *some* locally-aligned
    window in almost any sufficiently long haystack, regardless of true
    relevance. The default min_score must sit above that floor so a plain
    "status" (no shared keywords with "lease" at all) doesn't show up."""
    results = search_cli_tree(_SAMPLE_TREE, "lease")
    paths = [r.path for r in results]
    assert "audit queue purge-leases" in paths
    assert "status" not in paths


def test_search_cli_tree_glob_matches_wildcard_substring():
    """`lea*s*e` should find purge-leases without needing the exact word
    "lease" - the escape hatch for when fuzzy scoring isn't precise enough
    (e.g. it can't distinguish "lease" from "clears", which score ~75-80%
    via plain character similarity)."""
    results = search_cli_tree(_SAMPLE_TREE, "lea*s*e")
    paths = {r.path for r in results}
    assert "audit queue purge-leases" in paths
    assert all(r.score == 100 for r in results)


def test_search_cli_tree_glob_does_not_bridge_across_unrelated_fields():
    """Regression: matching the glob pattern against one giant concatenated
    "path + description + all options" blob let a wildcard span across
    completely unrelated option lines - "boolean" itself contains the
    literal substring "lea", so "lea*s*e" matched practically everything
    with two separate "(boolean)" options by bridging from the first
    "boolean)"'s "lea" through an unrelated option's "s" into a second
    "boolean)"'s "e". Each field (path, description, one option line) must
    be checked independently."""
    results = search_cli_tree(_SAMPLE_TREE, "lea*s*e")
    paths = {r.path for r in results}
    assert "admin" not in paths


def test_audit_filesystem_empty(tmp_path):
    # Setup isolated paths.root
    paths.root = tmp_path
    service = AuditService(campaign_name="test-campaign")
    res = service.audit_filesystem(campaign_name="test-campaign")
    assert "root_node" in res
    assert "orphans" in res
    assert len(res["orphans"]) == 0


def test_audit_schemas_detects_missing_hash(tmp_path):
    # Setup isolated paths.root
    paths.root = tmp_path

    # Create a mock campaign folder and a datapackage.json file without a schema hash
    campaign_dir = paths.campaign("test-campaign").ensure()
    dp_file = campaign_dir / "datapackage.json"
    dp_file.parent.mkdir(parents=True, exist_ok=True)
    dp_file.write_text(
        json.dumps({"name": "test-resource", "resources": []}), encoding="utf-8"
    )

    service = AuditService(campaign_name="test-campaign")
    res = service.audit_schemas(campaign="test-campaign")

    assert res["files_checked"] == 1
    assert len(res["issues_found"]) == 1
    assert res["issues_found"][0]["issue"] == "MISSING_SCHEMA_HASH"


def test_get_tile_status_counts_sharded_files_recursively(tmp_path):
    """map-tile's real writer (populate_tile_queue) shards pending/completed
    as {shard}/{lat}/{lon}/{tile_id}.usv, not a flat directory - a flat glob
    against that shape always returned 0. Regression test for that fix."""
    paths.root = tmp_path
    from cocli.core.queue.factory import get_queue_manager

    tile_queue = get_queue_manager("map-tile", queue_type="tile", campaign_name="test-campaign")

    pending_file = tile_queue.pending_dir / "2" / "28.7" / "-96.9" / "28.7_-96.9.usv"
    pending_file.parent.mkdir(parents=True, exist_ok=True)
    pending_file.write_text("row\n")

    completed_file = tile_queue.completed_dir / "3" / "33.5" / "-86.6" / "33.5_-86.6.usv"
    completed_file.parent.mkdir(parents=True, exist_ok=True)
    completed_file.write_text("row\n")

    service = AuditService(campaign_name="test-campaign")
    res = service.get_tile_status("test-campaign")

    assert res.pending_count == 1
    assert res.completed_count == 1
    assert not hasattr(res, "processing_count")
