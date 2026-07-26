"""Unit tests for DataSyncService frictionless data inspection methods."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from cocli.application.data_sync_service import (
    DataSyncService,
    MetricsResult,
    SampleResult,
    UnknownColumnError,
)
from cocli.core.paths import paths


def _write_datapackage(
    directory: Path,
    resource_name: str = "items",
    path_pattern: str = "*.usv",
    fields: list[dict[str, Any]] | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    fields = fields or [
        {"name": "place_id", "type": "string"},
        {"name": "slug", "type": "string"},
        {"name": "phone", "type": "string"},
        {"name": "reviews_count", "type": "integer"},
    ]
    dp = {
        "name": resource_name,
        "resources": [
            {
                "name": resource_name,
                "path": path_pattern,
                "schema": {"fields": fields},
            }
        ],
    }
    dp_path = directory / "datapackage.json"
    dp_path.write_text(json.dumps(dp))
    return dp_path


def _write_usv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join("\x1f".join(r) for r in rows) + "\n")


def test_resolve_usv_path_from_datapackage(tmp_path: Path) -> None:
    dp_path = _write_datapackage(tmp_path, path_pattern="data.usv")
    usv = tmp_path / "data.usv"
    usv.write_text("a\x1fb\n")
    resolved = DataSyncService.resolve_usv_path(tmp_path)
    assert resolved == usv
    resolved2 = DataSyncService.resolve_usv_path(dp_path)
    assert resolved2 == usv


def test_resolve_usv_path_missing_resource(tmp_path: Path) -> None:
    _write_datapackage(tmp_path, path_pattern="missing.usv")
    with pytest.raises(ValueError, match="No files found matching"):
        DataSyncService.resolve_usv_path(tmp_path)


def test_list_datapackages(tmp_path: Path) -> None:
    paths.root = tmp_path
    _write_datapackage(tmp_path / "a")
    _write_datapackage(tmp_path / "b" / "nested")
    service = DataSyncService()
    packs = service.list_datapackages()
    assert len(packs) == 2
    rels = {p.relative_path for p in packs}
    assert any("datapackage.json" in r for r in rels)


def test_describe_schema_datapackage(tmp_path: Path) -> None:
    dp = _write_datapackage(tmp_path)
    service = DataSyncService()
    result = service.describe_schema(dp)
    assert len(result.resources) == 1
    assert result.resources[0]["fields"][0]["name"] == "place_id"


def test_describe_schema_usv(tmp_path: Path) -> None:
    _write_datapackage(tmp_path, path_pattern="data.usv")
    usv = tmp_path / "data.usv"
    _write_usv(usv, [["p1", "slug-a", "555", "3"]])
    service = DataSyncService()
    with patch(
        "cocli.utils.duckdb_utils.find_datapackage", return_value=tmp_path / "datapackage.json"
    ), patch(
        "cocli.utils.duckdb_utils.match_resource_path", return_value=True
    ):
        result = service.describe_schema(usv)
    assert result.source_label == "data.usv"
    assert result.datapackage_path is not None


def test_locate_datapackage(tmp_path: Path) -> None:
    dp = _write_datapackage(tmp_path)
    service = DataSyncService()
    with patch("cocli.utils.duckdb_utils.find_datapackage", return_value=dp):
        assert service.locate_datapackage(tmp_path / "x.usv") == dp


def test_sample_rows(tmp_path: Path) -> None:
    _write_datapackage(tmp_path, path_pattern="data.usv")
    usv = tmp_path / "data.usv"
    _write_usv(
        usv,
        [
            ["p1", "alpha", "111", "1"],
            ["p2", "beta", "222", "2"],
            ["p3", "gamma", "333", "3"],
        ],
    )
    service = DataSyncService()
    # load_usv_to_duckdb needs real find_datapackage
    with patch(
        "cocli.utils.duckdb_utils.find_datapackage",
        return_value=tmp_path / "datapackage.json",
    ):
        result = service.sample_rows(usv, limit=2)
    assert isinstance(result, SampleResult)
    assert len(result.rows) == 2
    assert "place_id" in result.columns or len(result.columns) >= 1


def test_compute_metrics(tmp_path: Path) -> None:
    _write_datapackage(tmp_path, path_pattern="data.usv")
    usv = tmp_path / "data.usv"
    _write_usv(
        usv,
        [
            ["p1", "alpha", "111", "1"],
            ["p2", "beta", "", "2"],
            ["p1", "alpha-dup", "111", "1"],  # duplicate place_id (tile overlap)
        ],
    )
    out = tmp_path / "metrics.md"
    service = DataSyncService()
    with patch(
        "cocli.utils.duckdb_utils.find_datapackage",
        return_value=tmp_path / "datapackage.json",
    ):
        result = service.compute_metrics(usv, output_path=out)
    assert isinstance(result, MetricsResult)
    # Raw row total and deduplicated place count are separate metrics; no
    # per-field count may exceed Total Rows.
    assert result.metrics["Total Rows"] == 3
    assert result.metrics["Distinct Places"] == 2
    field_counts = {
        k: v
        for k, v in result.metrics.items()
        if k not in ("Total Rows", "Distinct Places")
    }
    assert all(v <= result.metrics["Total Rows"] for v in field_counts.values())
    assert result.output_path == out
    assert out.exists()
    assert "Metric" in out.read_text()


def test_compute_metrics_fallback(tmp_path: Path) -> None:
    service = DataSyncService()
    usv = tmp_path / "data.usv"
    fields = ["place_id", "slug", "phone"]
    _write_usv(
        usv,
        [
            ["p1", "a", "1"],
            ["p1", "a", "1"],  # duplicate place_id row still counts as a row
            ["p2", "b", ""],
        ],
    )
    result = service._compute_metrics_fallback(usv, fields)
    assert result.used_fallback is True
    assert result.metrics["Total Rows"] == 3
    assert result.metrics["Distinct Places"] == 2
    assert result.metrics["slug"] == 3
    assert result.metrics["phone"] == 2


def test_compute_metrics_emits_fallback_message_via_log_callback(
    tmp_path: Path,
) -> None:
    """
    Regression: the "Falling back..." message must fire through log_callback
    at the moment DuckDB fails, not only be inferable from used_fallback after
    the (potentially slow) Python scan has already completed.
    """
    _write_datapackage(tmp_path, path_pattern="data.usv")
    usv = tmp_path / "data.usv"
    _write_usv(usv, [["p1", "alpha", "111", "1"]])
    service = DataSyncService()
    messages: list[str] = []

    with (
        patch(
            "cocli.utils.duckdb_utils.find_datapackage",
            return_value=tmp_path / "datapackage.json",
        ),
        patch(
            "cocli.utils.duckdb_utils.load_usv_to_duckdb",
            side_effect=RuntimeError("boom"),
        ),
    ):
        result = service.compute_metrics(usv, log_callback=messages.append)

    assert result.used_fallback is True
    assert "Falling back to Python processing..." in messages


def test_search_usv_unknown_column(tmp_path: Path) -> None:
    dp = _write_datapackage(tmp_path)
    usv = tmp_path / "data.usv"
    _write_usv(usv, [["p1", "a", "1", "0"]])
    service = DataSyncService()
    with patch(
        "cocli.utils.duckdb_utils.find_datapackage", return_value=dp
    ), patch(
        "cocli.utils.duckdb_utils.get_schema_field_names",
        return_value=["place_id", "slug", "phone", "reviews_count"],
    ), patch(
        "cocli.utils.duckdb_utils.validate_query_columns",
        return_value=["not_a_col"],
    ):
        with pytest.raises(UnknownColumnError) as exc:
            service.search_usv(usv, query="not_a_col = 'x'")
    assert "not_a_col" in str(exc.value)
    assert "place_id" in exc.value.valid_preview


def test_inspect_row(tmp_path: Path) -> None:
    dp = _write_datapackage(tmp_path, path_pattern="data.usv")
    usv = tmp_path / "data.usv"
    _write_usv(usv, [["p1", "alpha", "555", "9"], ["p2", "beta", "666", "1"]])
    service = DataSyncService()
    with patch(
        "cocli.utils.duckdb_utils.find_datapackage", return_value=dp
    ), patch(
        "cocli.utils.duckdb_utils.match_resource_path", return_value=True
    ):
        result = service.inspect_row(usv, row_number=2)
    assert result.row_number == 2
    assert any(name == "slug" and val == "beta" for _, name, val in result.fields)


def test_inspect_row_missing(tmp_path: Path) -> None:
    dp = _write_datapackage(tmp_path, path_pattern="data.usv")
    usv = tmp_path / "data.usv"
    _write_usv(usv, [["p1", "alpha", "555", "9"]])
    service = DataSyncService()
    with patch(
        "cocli.utils.duckdb_utils.find_datapackage", return_value=dp
    ), patch(
        "cocli.utils.duckdb_utils.match_resource_path", return_value=True
    ):
        with pytest.raises(ValueError, match="Row 99 not found"):
            service.inspect_row(usv, row_number=99)


def test_compact_queue_unknown() -> None:
    service = DataSyncService(campaign_name="road")
    with pytest.raises(ValueError, match="Unknown queue"):
        service.compact_queue("not-a-queue")


def test_compact_queue_gm_list() -> None:
    service = DataSyncService(campaign_name="road")
    with patch(
        "cocli.core.transformers.gm_list_to_checkpoint.compact_gm_list_results",
        return_value=42,
    ):
        result = service.compact_queue("gm-list", campaign_name="road")
    assert result.success is True
    assert result.records_merged == 42
    assert "42" in result.message
