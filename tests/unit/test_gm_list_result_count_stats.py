"""gm-list receipt result_count distribution for `cocli audit scrape`."""

from __future__ import annotations

import json
from pathlib import Path

from cocli.commands.audit import _gm_list_result_count_stats, _percentile_nearest


def _write_receipt(root: Path, name: str, result_count: int) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"result_count": result_count, "status": "success"}))


def test_percentile_nearest_empty() -> None:
    assert _percentile_nearest([], 0.5) == 0


def test_percentile_nearest_single() -> None:
    assert _percentile_nearest([7], 0.1) == 7
    assert _percentile_nearest([7], 0.5) == 7


def test_stats_empty_dir(tmp_path: Path) -> None:
    stats = _gm_list_result_count_stats(tmp_path / "missing")
    assert stats["n"] == 0
    assert stats["zero_pct"] == 0.0
    assert stats["p10"] == 0
    assert stats["median"] == 0
    assert stats["max"] == 0


def test_stats_all_zero(tmp_path: Path) -> None:
    root = tmp_path / "results"
    _write_receipt(root, "a.json", 0)
    _write_receipt(root, "b.json", 0)
    stats = _gm_list_result_count_stats(root)
    assert stats["n"] == 2
    assert stats["zero_pct"] == 100.0
    assert stats["p10"] == 0
    assert stats["median"] == 0
    assert stats["max"] == 0


def test_stats_mixed_distribution(tmp_path: Path) -> None:
    root = tmp_path / "results"
    # 10 receipts: six zeros, then 1,2,3,10
    for i in range(6):
        _write_receipt(root, f"z{i}.json", 0)
    _write_receipt(root, "shard/1.2/-3.4/phrase.json", 1)
    _write_receipt(root, "one.json", 2)
    _write_receipt(root, "two.json", 3)
    _write_receipt(root, "ten.json", 10)
    (root / "datapackage.json").write_text("{}")
    stats = _gm_list_result_count_stats(root)
    assert stats["n"] == 10
    assert stats["zero_pct"] == 60.0
    assert stats["p10"] == 0
    assert stats["median"] == 0
    assert stats["max"] == 10
    assert "Pi sync" in stats["source"]


def test_stats_skips_invalid_json_and_missing_count(tmp_path: Path) -> None:
    root = tmp_path / "results"
    _write_receipt(root, "ok.json", 4)
    (root / "bad.json").write_text("not-json")
    (root / "no-count.json").write_text(json.dumps({"status": "success"}))
    stats = _gm_list_result_count_stats(root)
    assert stats["n"] == 1
    assert stats["median"] == 4
    assert stats["max"] == 4
