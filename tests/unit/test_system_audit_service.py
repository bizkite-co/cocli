import json
from io import StringIO

from textual.binding import Binding

from cocli.core.paths import paths
from cocli.application.audit_service import (
    AuditService,
    dump_tui_actions,
    parse_cli_tree,
    search_cli_tree,
)


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


# `cocli audit tui-actions` (2026-08-31): the TUI equivalent of
# `cocli audit cli` - Mark asked "is there any way we can export the TUI
# commands like we do with the CLI commands? That would allow us a metric
# of comparison". dump_tui_actions() takes already-imported classes rather
# than importing cocli.tui itself, mirroring how dump_cli_tree() only needs
# a Click command object handed to it - see its docstring for the full
# layering rationale.


def test_dump_tui_actions_normalizes_tuple_and_binding_forms():
    """BINDINGS entries appear as both the plain-tuple form and the
    explicit Binding(...) object form throughout cocli/tui/ - both must
    produce the same output shape."""

    class TupleForm:
        BINDINGS = [("t", "focus_template", "Focus Templates")]

    class BindingObjectForm:
        BINDINGS = [Binding("d", "delete_note", "Delete", show=True)]

    out = StringIO()
    dump_tui_actions([TupleForm, BindingObjectForm], out)
    text = out.getvalue()

    assert "t -> focus_template - Focus Templates" in text
    assert "d -> delete_note - Delete" in text


def test_dump_tui_actions_marks_hidden_bindings():
    class WithHidden:
        BINDINGS = [Binding("pagedown", "page_down", "Page Down", show=False)]

    out = StringIO()
    dump_tui_actions([WithHidden], out)
    assert "pagedown -> page_down - Page Down (hidden)" in out.getvalue()


def test_dump_tui_actions_lists_action_methods_not_covered_by_bindings():
    """Regression motivation: several real CocliApp actions (show_companies,
    show_people, escape, ...) are only reachable via the command palette or
    programmatically - not bound to any key. A bindings-only accounting
    would silently undercount the TUI's real action surface."""

    class OnlyReachableViaPalette:
        BINDINGS: list = []

        def action_show_companies(self) -> None:
            """Show the company list view."""

    out = StringIO()
    dump_tui_actions([OnlyReachableViaPalette], out)
    text = out.getvalue()
    assert "(unbound) -> show_companies - Show the company list view." in text


def test_dump_tui_actions_skips_classes_with_no_actions_at_all():
    class NothingHere:
        pass

    out = StringIO()
    dump_tui_actions([NothingHere], out)
    assert out.getvalue() == ""


def test_dump_tui_actions_tags_framework_vs_cocli_mechanically():
    """Regression motivation (Mark, 2026-08-31): "leave all those
    navigation and copy-paste types of command in the list for now so we
    can see them" - don't filter framework-inherited bindings (Input's
    cursor/copy/paste, DataTable's scrolling, ...) out, but do label them,
    since they can't correlate to any CLI command by nature. Resolved by
    walking the MRO to find which class actually defines the method - not
    a hand-maintained keyword list, which would silently miss new widgets."""
    from textual.widgets import Input

    class RealCocliInput(Input):
        """Mirrors the real cocli/tui/widgets/inputs.py::CocliInput: no
        BINDINGS override at all, so getattr(cls, "BINDINGS", []) resolves
        Input's own list via normal MRO lookup - that's what needs to be
        classified [framework], not artificially reconstructed here."""

        def action_custom_submit(self) -> None:
            """My Custom Submit."""

    out = StringIO()
    dump_tui_actions([RealCocliInput], out)
    text = out.getvalue()

    # Inherited straight from textual.widgets.Input, never overridden here.
    assert "[framework]" in text
    assert "cursor_left" in text
    # Defined on RealCocliInput itself, only reachable unbound (no key).
    assert "[cocli] (unbound) -> custom_submit - My Custom Submit" in text


def test_dump_tui_operations_includes_to_call_purge() -> None:
    """Regression (Mark, 2026-08-31): "We are supposed to have a way to
    purge and reload the to-call queue from the TUI, but I don't see it."
    It's real - op_compile_to_call, reachable via ApplicationView's
    Operations panel (pick from a list, press Enter) rather than a
    dedicated keybinding, which is exactly why dump_tui_actions() alone
    couldn't show it."""
    from cocli.application.audit_service import dump_tui_operations

    out = StringIO()
    dump_tui_operations(out)
    text = out.getvalue()
    assert "op_compile_to_call" in text
    assert "Compile To-Call List" in text


def test_get_tui_operations_via_audit_service() -> None:
    service = AuditService(campaign_name="test-campaign")
    report = service.get_tui_operations()
    assert "op_compile_to_call" in report


def test_get_tui_actions_on_the_real_tui_classes():
    """Lighter integration check, mirroring test_get_cli_tree(): confirm
    the real discovery + dump doesn't crash and finds a substantial,
    non-trivial action surface."""
    from cocli.commands.audit import _discover_tui_classes

    classes = _discover_tui_classes()
    assert len(classes) > 10

    service = AuditService(campaign_name="test-campaign")
    report = service.get_tui_actions(classes)
    assert "CocliApp" in report
    assert "show_companies" in report


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
    stations - Stations substrate tools.
        inspect - Render a campaign station root via stations inspect.
            queue (text)
            --no-leases (boolean)
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


def test_search_cli_tree_finds_command_by_substring():
    results = search_cli_tree(_SAMPLE_TREE, "lease")
    paths = [r.path for r in results]
    assert paths == ["audit queue purge-leases"]


def test_search_cli_tree_ignores_options_not_just_path_and_description():
    """Regression (Mark, 2026-08-31): an earlier version matched across
    path+description+options combined, so `cocli help lease` surfaced
    "stations inspect" purely because it has a `--no-leases` option among
    a dozen others - its own name/description have nothing to do with
    leases. Too weak a signal to be worth the noise; only path+description
    should be searched."""
    results = search_cli_tree(_SAMPLE_TREE, "lease")
    paths = [r.path for r in results]
    assert "stations inspect" not in paths
    # Still shown *in the results* (for context), just not matched against.
    match = next(r for r in results if r.path == "audit queue purge-leases")
    assert match.options == [
        "--campaign (text)",
        "--queue-name (text)",
        "--force (boolean)",
    ]


def test_search_cli_tree_nonsense_query_returns_nothing():
    results = search_cli_tree(_SAMPLE_TREE, "zzz-no-such-thing-zzz")
    assert results == []


def test_search_cli_tree_respects_limit():
    results = search_cli_tree(_SAMPLE_TREE, "campaign", limit=1)
    assert len(results) == 1


def test_search_cli_tree_multi_word_query_requires_all_words_anywhere():
    """A literal-phrase match ("campaign switch" as one adjacent substring)
    would be too strict for exploratory queries where the words don't
    appear adjacently in that exact order - each word must be found
    somewhere in path+description, in any order."""
    results = search_cli_tree(_SAMPLE_TREE, "current status")
    paths = [r.path for r in results]
    assert paths == ["status"]

    # Neither word alone should be sufficient - both must match.
    assert search_cli_tree(_SAMPLE_TREE, "current nonexistentword") == []


def test_search_cli_tree_word_supports_real_regex_syntax():
    """Each word is matched as an actual regex, not just a literal
    substring - e.g. alternation."""
    results = search_cli_tree(_SAMPLE_TREE, "purge|deduplicate")
    paths = {r.path for r in results}
    assert "audit queue purge-leases" in paths
    assert "deduplicate deduplicate" in paths


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
