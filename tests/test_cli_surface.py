"""CLI surface safety-net tests for the consolidation epic.

Two fast, hermetic checks that run in every ``make test`` to catch
unintentional command surface changes or registration/import breakage:

1. Golden-file test -- renders the full command hierarchy to a string
   in-process (reusing the same tree walker behind ``cocli audit cli``)
   and diffs it against a committed golden snapshot. Any PR that
   intentionally changes the surface must update the golden in the same
   PR, giving us an auditable record of every surface change.

2. Help smoke test -- parameterized over every leaf node in the command
   tree, invoking each with ``--help`` via Typer's CliRunner and
   asserting exit code 0.  Catches import/registration breakage from
   file moves within seconds.
"""
import difflib
from io import StringIO
from pathlib import Path
from typing import Any, List, Tuple

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from cocli.commands.audit import dump_cli_tree
from cocli.main import app as main_app

GOLDEN_FILE = Path(__file__).parent / "goldens" / "cli_tree.txt"


def _render_cli_tree() -> str:
    click_command = get_command(main_app)
    out = StringIO()
    dump_cli_tree(click_command, out)
    return out.getvalue()


def _collect_leaves(
    command: Any, path: Tuple[str, ...] = ()
) -> List[Tuple[str, Tuple[str, ...]]]:
    path = path + (command.name,) if command.name else path
    subcommands = getattr(command, "commands", {})
    if not subcommands:
        return [(command.name or "cocli", path)]
    leaves: List[Tuple[str, Tuple[str, ...]]] = []
    for sub_name in sorted(subcommands):
        leaves.extend(_collect_leaves(subcommands[sub_name], path))
    return leaves


_click_root = get_command(main_app)
_all_leaves = _collect_leaves(_click_root)


def test_cli_tree_matches_golden() -> None:
    actual = _render_cli_tree()
    if not GOLDEN_FILE.exists():
        pytest.fail(
            f"Golden file not found: {GOLDEN_FILE}\n"
            f"Regenerate with:\n"
            f"  uv run cocli audit cli --output {GOLDEN_FILE}\n"
            f"Or run the dumper in-process and write the file."
        )
    expected = GOLDEN_FILE.read_text(encoding="utf-8")

    if actual != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=str(GOLDEN_FILE),
                tofile="<in-process render>",
            )
        )
        pytest.fail(
            "CLI tree does not match golden snapshot.\n"
            "If this change is intentional, update the golden:\n"
            f"  uv run cocli audit cli --output {GOLDEN_FILE}\n\n"
            f"{diff}"
        )


@pytest.fixture(scope="module")
def runner() -> CliRunner:
    return CliRunner()


@pytest.mark.parametrize(
    "leaf_path",
    [pytest.param(path, id="-".join(path)) for _name, path in _all_leaves],
)
def test_help_smoke(runner: CliRunner, leaf_path: Tuple[str, ...]) -> None:
    result = runner.invoke(main_app, list(leaf_path) + ["--help"])
    assert result.exit_code == 0, (
        f"`cocli {' '.join(leaf_path)} --help` exited {result.exit_code}:\n"
        f"{result.output}"
    )


ACTUAL_TREE_FILE = Path(__file__).parents[1] / "docs" / "cli" / "actual_tree.txt"


def test_golden_matches_actual_tree_doc() -> None:
    """`tests/goldens/cli_tree.txt` and `docs/cli/actual_tree.txt` are the same
    content today and are kept in sync by this test. They serve different
    purposes (golden snapshot for the surface test vs. Screaming Architecture
    comparison doc), so both are kept, but they must not silently drift.

    If you intentionally changed the CLI surface, regenerate both from the same
    walker so this test stays green:

        make cli-tree                                  # writes docs/cli/actual_tree.txt
        uv run cocli audit cli --output tests/goldens/cli_tree.txt
    """
    if not ACTUAL_TREE_FILE.exists():
        pytest.fail(
            f"{ACTUAL_TREE_FILE} not found. Regenerate with:\n"
            f"  make cli-tree"
        )
    actual = ACTUAL_TREE_FILE.read_text(encoding="utf-8")
    expected = GOLDEN_FILE.read_text(encoding="utf-8")
    if actual != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=str(GOLDEN_FILE),
                tofile=str(ACTUAL_TREE_FILE),
            )
        )
        pytest.fail(
            "CLI tree golden snapshot does not match docs/cli/actual_tree.txt.\n"
            "Both files must be regenerated together from the same walker:\n"
            "  make cli-tree\n"
            "  uv run cocli audit cli --output tests/goldens/cli_tree.txt\n\n"
            f"{diff}"
        )