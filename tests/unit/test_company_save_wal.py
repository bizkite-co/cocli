"""Company.save journals changed fields when use_wal is true."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cocli.core.paths import paths
from cocli.core.wal import read_updates
from cocli.models.companies.company import Company
from cocli.models.company_name import CompanyName


def test_save_appends_a_changed_field_and_writes_the_file(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        company = Company(name=CompanyName("Acme"), slug="acme", city="Dallas")
        company.save(rebuild_cache=False, email_sync=False)
        assert read_updates(paths.companies.path / "acme") == []

        company.city = "Austin"
        company.save(rebuild_cache=False, email_sync=False)

        records = read_updates(paths.companies.path / "acme")
        text = (paths.companies.path / "acme" / "_index.md").read_text(encoding="utf-8")

    assert [record.field for record in records] == ["city"]
    assert records[0].value == "Austin"
    assert "Austin" in text


def test_second_save_with_no_change_appends_nothing(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        company = Company(name=CompanyName("Acme"), slug="acme", city="Dallas")
        company.save(rebuild_cache=False, email_sync=False)
        company.city = "Austin"
        company.save(rebuild_cache=False, email_sync=False)
        company.save(rebuild_cache=False, email_sync=False)
        records = read_updates(paths.companies.path / "acme")
    assert len(records) == 1


def test_use_wal_false_writes_the_file_and_appends_nothing(tmp_path: Path) -> None:
    with patch.object(paths, "root", tmp_path):
        company = Company(name=CompanyName("Acme"), slug="acme", city="Dallas")
        company.save(rebuild_cache=False, email_sync=False, use_wal=False)
        company.city = "Austin"
        company.save(rebuild_cache=False, email_sync=False, use_wal=False)
        records = read_updates(paths.companies.path / "acme")
        text = (paths.companies.path / "acme" / "_index.md").read_text(encoding="utf-8")
    assert records == []
    assert "Austin" in text
