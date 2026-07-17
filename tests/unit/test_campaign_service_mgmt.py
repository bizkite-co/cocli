"""Unit tests for CampaignService methods extracted from campaign/mgmt.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import toml

from cocli.application.campaign_service import CampaignEditTargets, CampaignService


def _campaign_dir(tmp_path: Path, name: str = "road") -> Path:
    camp = tmp_path / "campaigns" / name
    camp.mkdir(parents=True)
    (camp / "config.toml").write_text(
        toml.dumps(
            {
                "campaign": {"name": name, "tag": name},
                "aws": {"data_bucket_name": "my-bucket", "profile": "p"},
                "prospecting": {"queries": ["welders"]},
            }
        )
    )
    (camp / "README.md").write_text("# Road\n")
    return camp


def test_list_campaign_names(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    with patch(
        "cocli.core.config.get_all_campaign_dirs", return_value=[a, b]
    ):
        names = CampaignService.list_campaign_names()
    assert names == ["a", "b"]


def test_get_edit_targets(tmp_path: Path) -> None:
    camp = _campaign_dir(tmp_path)
    with patch(
        "cocli.application.campaign_service.get_campaign_dir", return_value=camp
    ):
        service = CampaignService("road")
        targets = service.get_edit_targets()
    assert isinstance(targets, CampaignEditTargets)
    assert targets.config_exists is True
    assert targets.readme_exists is True
    assert targets.config_path in targets.files_to_edit
    assert targets.readme_path in targets.files_to_edit


def test_get_edit_targets_missing_campaign(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with patch(
        "cocli.application.campaign_service.get_campaign_dir", return_value=missing
    ):
        service = CampaignService("nope")
        with pytest.raises(FileNotFoundError, match="not found"):
            service.get_edit_targets()


def test_get_edit_targets_no_files(tmp_path: Path) -> None:
    camp = tmp_path / "empty"
    camp.mkdir()
    with patch(
        "cocli.application.campaign_service.get_campaign_dir", return_value=camp
    ):
        service = CampaignService("empty")
        with pytest.raises(FileNotFoundError, match="No files to edit"):
            service.get_edit_targets()


def test_get_s3_campaign_uri(tmp_path: Path) -> None:
    camp = _campaign_dir(tmp_path)
    with patch(
        "cocli.application.campaign_service.get_campaign_dir", return_value=camp
    ):
        uri = CampaignService("road").get_s3_campaign_uri()
    assert uri == "s3://my-bucket/campaigns/road/"


def test_get_s3_campaign_uri_fallback_bucket(tmp_path: Path) -> None:
    camp = tmp_path / "campaigns" / "x"
    camp.mkdir(parents=True)
    (camp / "config.toml").write_text(toml.dumps({"campaign": {"name": "x"}, "aws": {}}))
    with patch(
        "cocli.application.campaign_service.get_campaign_dir", return_value=camp
    ):
        uri = CampaignService("x").get_s3_campaign_uri()
    assert uri == "s3://cocli-data-x/campaigns/x/"


def test_load_campaign_model(tmp_path: Path) -> None:
    camp = _campaign_dir(tmp_path)
    mock_model = MagicMock()
    with patch(
        "cocli.application.campaign_service.get_campaign_dir", return_value=camp
    ), patch(
        "cocli.models.campaigns.campaign.Campaign.model_validate",
        return_value=mock_model,
    ) as validate:
        result = CampaignService("road").load_campaign_model()
    assert result is mock_model
    validate.assert_called_once()
    # Flattened: campaign.name + aws + prospecting
    flat = validate.call_args[0][0]
    assert flat["name"] == "road"
    assert flat["aws"]["data_bucket_name"] == "my-bucket"


def test_clear_context() -> None:
    with patch("cocli.core.config.set_campaign") as set_camp:
        CampaignService.clear_context()
    set_camp.assert_called_once_with(None)


def test_create_campaign() -> None:
    with patch(
        "cocli.models.campaigns.campaign.Campaign.create"
    ) as create, patch(
        "cocli.core.config.get_cocli_base_dir", return_value=Path("/data")
    ), patch(
        "cocli.core.config.get_campaign_dir", return_value=Path("/data/campaigns/new")
    ):
        path = CampaignService.create_campaign("new", "Acme")
    create.assert_called_once_with("new", "Acme", Path("/data"))
    assert path == Path("/data/campaigns/new")


def test_add_query_roundtrip(tmp_path: Path) -> None:
    camp = _campaign_dir(tmp_path)
    with patch(
        "cocli.application.campaign_service.get_campaign_dir", return_value=camp
    ), patch(
        "cocli.application.campaign_service.load_campaign_config",
        return_value={
            "campaign": {"name": "road"},
            "prospecting": {"queries": ["welders"]},
        },
    ):
        service = CampaignService("road")
        with patch.object(service, "_save_config") as save:
            assert service.add_query("fabricators") is True
            save.assert_called_once()
            saved = save.call_args[0][0]
            assert "fabricators" in saved["prospecting"]["queries"]
            assert service.add_query("welders") is False
