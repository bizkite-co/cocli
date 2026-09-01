from pathlib import Path
from unittest.mock import patch

import pytest

from cocli.core.do_not_call_manager import DoNotCallManager, normalize_phone
from cocli.core.paths import paths


@pytest.fixture
def sandboxed_root(tmp_path: Path):
    with patch.object(paths, "root", tmp_path):
        yield tmp_path


def test_normalize_phone_matches_regardless_of_formatting() -> None:
    assert normalize_phone("(512) 234-5678") == normalize_phone("512-234-5678")
    assert normalize_phone("512-234-5678") == normalize_phone("+15122345678")


def test_add_then_is_do_not_call_matches_differently_formatted_same_number(
    sandboxed_root: Path,
) -> None:
    manager = DoNotCallManager()
    manager.add("512-234-5678", reason="asked not to be called")

    assert manager.is_do_not_call("(512) 234-5678") is True
    assert manager.is_do_not_call("+1 512 234 5678") is True
    assert manager.is_do_not_call("512-234-9999") is False
    assert manager.is_do_not_call(None) is False


def test_add_persists_across_manager_instances(sandboxed_root: Path) -> None:
    DoNotCallManager().add("512-234-5678")

    fresh_manager = DoNotCallManager()
    assert fresh_manager.is_do_not_call("512-234-5678") is True


def test_remove_clears_the_entry(sandboxed_root: Path) -> None:
    manager = DoNotCallManager()
    manager.add("512-234-5678")
    assert manager.remove("512-234-5678") is True
    assert manager.is_do_not_call("512-234-5678") is False
    assert manager.remove("512-234-5678") is False


def test_list_entries_returns_added_numbers(sandboxed_root: Path) -> None:
    manager = DoNotCallManager()
    manager.add("512-234-5678", reason="a")
    manager.add("737-234-0100", reason="b")

    entries = manager.list_entries()
    assert {e.phone for e in entries} == {normalize_phone("512-234-5678"), normalize_phone("737-234-0100")}
