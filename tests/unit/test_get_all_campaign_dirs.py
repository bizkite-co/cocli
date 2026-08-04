"""Campaign discovery must stay fast and avoid deep data-tree rglob."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cocli.core.config import get_all_campaign_dirs


def test_get_all_campaign_dirs_finds_top_level_and_nested(tmp_path: Path) -> None:
    root = tmp_path / "campaigns"
    top = root / "top"
    nested = root / "group" / "nested"
    top.mkdir(parents=True)
    nested.mkdir(parents=True)
    (top / "config.toml").write_text("[campaign]\nname = 'top'\n")
    (nested / "config.toml").write_text("[campaign]\nname = 'nested'\n")
    # Decoy config.toml buried under a data folder must be ignored/skipped
    decoy_parent = top / "indexes" / "deep"
    decoy_parent.mkdir(parents=True)
    (decoy_parent / "config.toml").write_text("[not]\na = 'campaign'\n")

    with patch("cocli.core.config.paths") as mock_paths:
        mock_paths.campaigns = root
        found = get_all_campaign_dirs()

    names = sorted(str(p.relative_to(root)) for p in found)
    assert names == ["group/nested", "top"]


def test_get_all_campaign_dirs_empty_root(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with patch("cocli.core.config.paths") as mock_paths:
        mock_paths.campaigns = missing
        assert get_all_campaign_dirs() == []
